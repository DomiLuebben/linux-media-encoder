# -*- coding: utf-8 -*-
"""
Interaktive Bildvorschau mit Zuschneide-Funktion für den Linux Media Encoder.
Der Benutzer zieht mit der Maus ein Rechteck über das angezeigte Bild; die
Auswahl wird in Quellbild-Pixel umgerechnet und als crop_changed gemeldet.
"""

from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QRegion
from PyQt6.QtWidgets import QLabel

from i18n import QLabel


class CropImageLabel(QLabel):
    """QLabel-Vorschau, auf der per Maus ein Zuschnitt gewählt werden kann.

    Die Pixmap wird weiterhin von außen skaliert und via setPixmap gesetzt;
    dieses Widget übernimmt nur Auswahl, Overlay und Koordinaten-Mapping.
    """

    # dict {"x","y","w","h"} in Quellpixeln oder None (Auswahl aufgehoben)
    crop_changed = pyqtSignal(object)

    MIN_CROP_PX = 8   # Mindestgröße des Zuschnitts in Quellpixeln
    MIN_DRAG_PX = 5   # kleinere Mausbewegungen gelten als Klick, nicht als Auswahl

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self._source_size = QSize()
        self._crop = None
        self._interactive = False
        self._mode = None            # None | "draw" | "move"
        self._drag_start = QPoint()
        self._drag_current = QPoint()
        self._move_start_crop = None  # Zuschnitt beim Start des Verschiebens

    # --- Öffentliche API ---
    def set_source_size(self, width, height):
        """Pixelmaße des Original-Quellbilds (Basis für das Koordinaten-Mapping)."""
        self._source_size = QSize(int(width or 0), int(height or 0))
        self.update()

    def set_interactive(self, enabled):
        """Schaltet die Maus-Auswahl frei (nur für Bild-Jobs sinnvoll)."""
        self._interactive = bool(enabled)
        self.setCursor(
            Qt.CursorShape.CrossCursor if self._interactive else Qt.CursorShape.ArrowCursor
        )

    def set_crop(self, crop):
        """Setzt den angezeigten Zuschnitt (Quellpixel-dict oder None) ohne Signal."""
        self._crop = dict(crop) if crop else None
        self.update()

    def crop(self):
        return dict(self._crop) if self._crop else None

    # --- Koordinaten-Mapping ---
    def _display_rect(self):
        """Rechteck der dargestellten (skalierten) Pixmap in Widget-Koordinaten."""
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return QRect()
        area = self.contentsRect()
        x = area.x() + (area.width() - pm.width()) // 2
        y = area.y() + (area.height() - pm.height()) // 2
        return QRect(x, y, pm.width(), pm.height())

    def _mapping_ready(self):
        return (
            not self._display_rect().isEmpty()
            and self._source_size.width() > 0
            and self._source_size.height() > 0
        )

    def _selection_to_source(self, sel, display):
        """Widget-Auswahlrechteck → geclampter Quellpixel-Zuschnitt (oder None)."""
        sx = self._source_size.width() / display.width()
        sy = self._source_size.height() / display.height()
        x1 = (sel.left() - display.x()) * sx
        y1 = (sel.top() - display.y()) * sy
        x2 = (sel.right() + 1 - display.x()) * sx
        y2 = (sel.bottom() + 1 - display.y()) * sy

        x = max(0, min(self._source_size.width(), round(x1)))
        y = max(0, min(self._source_size.height(), round(y1)))
        w = max(0, min(self._source_size.width(), round(x2)) - x)
        h = max(0, min(self._source_size.height(), round(y2)) - y)
        if w < self.MIN_CROP_PX or h < self.MIN_CROP_PX:
            return None
        return {"x": x, "y": y, "w": w, "h": h}

    def _source_to_widget_rect(self, crop, display):
        sx = display.width() / self._source_size.width()
        sy = display.height() / self._source_size.height()
        return QRect(
            round(display.x() + crop["x"] * sx),
            round(display.y() + crop["y"] * sy),
            max(1, round(crop["w"] * sx)),
            max(1, round(crop["h"] * sy)),
        )

    def _clamp_to_display(self, point, display):
        return QPoint(
            max(display.left(), min(display.right(), point.x())),
            max(display.top(), min(display.bottom(), point.y())),
        )

    def _crop_widget_rect(self, display):
        """Widget-Rechteck des aktuellen Zuschnitts oder leeres QRect."""
        if not self._crop or not self._mapping_ready():
            return QRect()
        return self._source_to_widget_rect(self._crop, display).intersected(display)

    def _apply_move(self, pos):
        """Verschiebt den Zuschnitt gemäß Mausposition, geclampt auf das Quellbild."""
        display = self._display_rect()
        sx = self._source_size.width() / display.width()
        sy = self._source_size.height() / display.height()
        dx = round((pos.x() - self._drag_start.x()) * sx)
        dy = round((pos.y() - self._drag_start.y()) * sy)
        base = self._move_start_crop
        x = max(0, min(self._source_size.width() - base["w"], base["x"] + dx))
        y = max(0, min(self._source_size.height() - base["h"], base["y"] + dy))
        self._crop = {"x": x, "y": y, "w": base["w"], "h": base["h"]}

    def _update_hover_cursor(self, pos):
        if not self._interactive:
            return
        if self._crop_widget_rect(self._display_rect()).contains(pos):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    # --- Maus-Interaktion ---
    def mousePressEvent(self, event):
        display = self._display_rect()
        pos = event.position().toPoint()
        if (
            self._interactive
            and event.button() == Qt.MouseButton.LeftButton
            and self._mapping_ready()
            and display.contains(pos)
        ):
            self._drag_start = pos
            self._drag_current = pos
            if self._crop_widget_rect(display).contains(pos):
                self._mode = "move"
                self._move_start_crop = dict(self._crop)
            else:
                self._mode = "draw"
            self.update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._mode == "draw":
            self._drag_current = self._clamp_to_display(pos, self._display_rect())
            self.update()
            return
        if self._mode == "move":
            self._drag_current = pos
            self._apply_move(pos)
            self.update()
            return
        self._update_hover_cursor(pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mode and event.button() == Qt.MouseButton.LeftButton:
            mode = self._mode
            self._mode = None
            display = self._display_rect()
            end = self._clamp_to_display(event.position().toPoint(), display)
            if mode == "draw":
                moved = (end - self._drag_start).manhattanLength()
                if moved >= self.MIN_DRAG_PX and self._mapping_ready():
                    sel = QRect(self._drag_start, end).normalized()
                    crop = self._selection_to_source(sel, display)
                    if crop:
                        self._crop = crop
                        self.crop_changed.emit(dict(crop))
            elif mode == "move":
                if self._crop and self._crop != self._move_start_crop:
                    self.crop_changed.emit(dict(self._crop))
                self._move_start_crop = None
            self._update_hover_cursor(end)
            self.update()
            return
        super().mouseReleaseEvent(event)

    # --- Darstellung ---
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._mapping_ready():
            return
        display = self._display_rect()

        if self._mode == "draw":
            sel = QRect(self._drag_start, self._drag_current).normalized().intersected(display)
        elif self._crop:
            sel = self._source_to_widget_rect(self._crop, display).intersected(display)
        else:
            return
        if sel.isEmpty():
            return

        painter = QPainter(self)
        # Außenbereich abdunkeln, Auswahl bleibt klar sichtbar
        painter.setClipRegion(QRegion(display).subtracted(QRegion(sel)))
        painter.fillRect(display, QColor(0, 0, 0, 140))
        painter.setClipping(False)
        painter.setPen(QPen(QColor("#3daee9"), 1))
        painter.drawRect(sel.adjusted(0, 0, -1, -1))

        # Live-Anzeige in Quellpixeln während des Aufziehens bzw. Verschiebens
        text = None
        if self._mode == "draw":
            crop = self._selection_to_source(sel, display)
            if crop:
                text = f"{crop['w']}×{crop['h']} px"
        elif self._mode == "move" and self._crop:
            text = f"({self._crop['x']}, {self._crop['y']})"
        if text:
            text_pos = QPoint(sel.x() + 4, max(display.top() + 12, sel.y() - 6))
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(text_pos, text)
        painter.end()
