# -*- coding: utf-8 -*-
"""
Export-Einstellungen (Export Settings) Dialog für den Linux Media Encoder.
Bietet ein modales Dialogfenster im exakten Stil des Adobe Media Encoders
mit Video-Vorschau, Timeline, Container/Preset-Auswahl und erweiterten Tabs.
"""

import os
import re
import presets
import styles
from PyQt6.QtCore import Qt, QSize, QProcess, QTimer
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QLineEdit, QPushButton, QCheckBox, QTabWidget, QSlider,
    QFileDialog, QGroupBox, QSpinBox, QDoubleSpinBox, QDialogButtonBox,
    QFrame, QStyle
)
from PyQt6.QtGui import QPixmap, QFont, QPainter, QColor


class SeekSlider(QSlider):
    """Timeline-Slider, bei dem ein Klick direkt zur Position springt
    (statt Qt-Standard: ein PageStep in Richtung des Klicks)."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.maximum() > self.minimum():
            value = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(),
                round(event.position().x()), max(1, self.width()),
            )
            self.setValue(value)
        super().mousePressEvent(event)


class TrimRangeBar(QWidget):
    """Schmale Leiste unter der Timeline, die den Export-Bereich (In/Out)
    farbig markiert — ohne Schnitt bleibt die ganze Leiste gedimmt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._start_frac = 0.0
        self._end_frac = 1.0
        self._active = False

    def set_trim(self, start_frac, end_frac, active):
        self._start_frac = min(max(start_frac, 0.0), 1.0)
        self._end_frac = min(max(end_frac, 0.0), 1.0)
        self._active = bool(active)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        radius = h / 2
        painter.setBrush(QColor(styles.BORDER))
        painter.drawRoundedRect(0, 0, w, h, radius, radius)
        if self._active and self._end_frac > self._start_frac:
            x0 = int(self._start_frac * w)
            x1 = max(int(self._end_frac * w), x0 + 2)
            painter.setBrush(QColor(styles.ACCENT))
            painter.drawRoundedRect(x0, 0, x1 - x0, h, radius, radius)
        painter.end()


class ExportSettingsDialog(QDialog):
    # Feine Timeline-Auflösung: 10000 Schritte statt 100, sonst wäre bei einem
    # einstündigen Video ein Slider-Schritt 36 Sekunden grob.
    SLIDER_MAX = 10000
    def __init__(self, input_file, output_file, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exporteinstellungen")
        self.setMinimumSize(QSize(1000, 650))
        self.setModal(True)
        
        # Eingabedaten
        self.input_file = input_file
        self.output_file = output_file
        self.settings = dict(settings)  # Kopie anfertigen
        self._loading_settings = False
        self._preview_temp_files = set()  # erzeugte Vorschau-JPGs für Cleanup

        # Quell-Metadaten werden asynchron ermittelt (ffprobe blockierte den
        # Dialog sonst bei langsamen Quellen bis zu 5 Sekunden), ebenso das
        # Vorschaubild. Bis dahin gelten leere Defaults.
        self.source_info = self._empty_source_info()
        self.preview_frame_path = None
        self._preview_proc = None
        self._probe_proc = None

        # UI initialisieren
        self._init_layout()
        self._load_settings_to_ui()
        self._update_summary()
        self._start_probe()
        self._trigger_preview_update()
        
    def _init_layout(self):
        """Erstellt das zweispaltige AME-Layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)
        
        # ================= LINKE SEITE: VORSCHAU =================
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        
        # Video-Vorschau Bild
        self.preview_label = QLabel()
        self.preview_label.setObjectName("preview_frame")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Zunächst Fallback anzeigen; das echte Vorschaubild kommt asynchron
        # aus _trigger_preview_update, sobald ffmpeg den Frame extrahiert hat.
        self._set_preview_image(None)

        left_layout.addWidget(self.preview_label)
        
        # Timeline-Steuerung (Scrubbing für Vorschau + Trim-Punkte)
        self.timeline_widget = QWidget()
        timeline_layout = QVBoxLayout(self.timeline_widget)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_layout.setSpacing(2)

        self.time_slider = SeekSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, self.SLIDER_MAX)
        self.time_slider.setValue(int(0.18 * self.SLIDER_MAX))
        self.time_slider.setToolTip(
            "Klicken oder ziehen zum Springen — ←/→ = 1 s, Bild↑/↓ = 10 s.\n"
            "I = In-Punkt setzen, O = Out-Punkt setzen."
        )
        self.time_slider.sliderReleased.connect(self._trigger_preview_update)
        self.time_slider.valueChanged.connect(self._on_slider_value_changed)
        timeline_layout.addWidget(self.time_slider)

        # Markiert den Export-Bereich (In/Out) direkt unter der Timeline
        self.trim_range_bar = TrimRangeBar()
        timeline_layout.addWidget(self.trim_range_bar)

        left_layout.addWidget(self.timeline_widget)

        # Live-Vorschau beim Ziehen: debounced, damit nicht jede Zwischen-
        # position einen eigenen ffmpeg-Aufruf auslöst.
        self._preview_debounce = QTimer(self)
        self._preview_debounce.setSingleShot(True)
        self._preview_debounce.setInterval(200)
        self._preview_debounce.timeout.connect(self._trigger_preview_update)

        # Timecode-Anzeige (echte Dauer aus der Quelle)
        total_dur = self.source_info.get("duration", 0.0) if self.source_info else 0.0
        self.timecode_widget = QWidget()
        timecode_layout = QHBoxLayout(self.timecode_widget)
        timecode_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_current_time = QLabel(self._format_timecode(total_dur * 0.18))
        self.lbl_current_time.setObjectName("time_current")
        self.lbl_total_time = QLabel(self._format_timecode(total_dur))
        self.lbl_total_time.setObjectName("time_total")
        timecode_layout.addWidget(self.lbl_current_time)
        timecode_layout.addStretch()
        timecode_layout.addWidget(self.lbl_total_time)
        left_layout.addWidget(self.timecode_widget)

        # Trim-Steuerung: In-/Out-Punkt an der aktuellen Slider-Position setzen oder per Texteingabe
        self.trim_widget = QWidget()
        trim_layout = QGridLayout(self.trim_widget)
        trim_layout.setContentsMargins(0, 0, 0, 0)
        trim_layout.setSpacing(6)
        
        # Reihe 0: Startzeit (In-Punkt)
        lbl_in = QLabel("Start (In):")
        trim_layout.addWidget(lbl_in, 0, 0)
        
        self.edit_trim_in = QLineEdit()
        self.edit_trim_in.setPlaceholderText("00:00:00.000")
        self.edit_trim_in.setMaximumWidth(120)
        self.edit_trim_in.setToolTip("Genaue Startzeit eingeben (z. B. HH:MM:SS.mmm, MM:SS oder Sekunden)")
        self.edit_trim_in.editingFinished.connect(self._on_trim_in_edited)
        trim_layout.addWidget(self.edit_trim_in, 0, 1)
        
        self.btn_set_in = QPushButton()
        self.btn_set_in.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.btn_set_in.setFixedWidth(32)
        self.btn_set_in.setAutoDefault(False)
        self.btn_set_in.setToolTip("Aktuelle Timeline-Position als Startzeit übernehmen (Taste I).")
        self.btn_set_in.clicked.connect(self._on_set_trim_in)
        trim_layout.addWidget(self.btn_set_in, 0, 2)
        
        # Reihe 1: Endzeit (Out-Punkt)
        lbl_out = QLabel("Ende (Out):")
        trim_layout.addWidget(lbl_out, 1, 0)
        
        self.edit_trim_out = QLineEdit()
        self.edit_trim_out.setPlaceholderText("00:00:00.000")
        self.edit_trim_out.setMaximumWidth(120)
        self.edit_trim_out.setToolTip("Genaue Endzeit eingeben (z. B. HH:MM:SS.mmm, MM:SS oder Sekunden)")
        self.edit_trim_out.editingFinished.connect(self._on_trim_out_edited)
        trim_layout.addWidget(self.edit_trim_out, 1, 1)
        
        self.btn_set_out = QPushButton()
        self.btn_set_out.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.btn_set_out.setFixedWidth(32)
        self.btn_set_out.setAutoDefault(False)
        self.btn_set_out.setToolTip("Aktuelle Timeline-Position als Endzeit übernehmen (Taste O).")
        self.btn_set_out.clicked.connect(self._on_set_trim_out)
        trim_layout.addWidget(self.btn_set_out, 1, 2)
        
        # Reihe 2: Steuerung & Statusinfo
        self.btn_clear_trim = QPushButton("Schnitt aufheben")
        self.btn_clear_trim.setAutoDefault(False)
        self.btn_clear_trim.clicked.connect(self._on_clear_trim)
        trim_layout.addWidget(self.btn_clear_trim, 2, 0, 1, 2)
        
        self.lbl_trim_info = QLabel("")
        self.lbl_trim_info.setWordWrap(True)
        trim_layout.addWidget(self.lbl_trim_info, 2, 2)
        
        left_layout.addWidget(self.trim_widget)
        self._update_trim_ui()

        left_layout.addStretch()
        main_layout.addWidget(left_widget, stretch=6)
        
        # ================= RECHTE SEITE: EINSTELLUNGEN =================
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        # Exporteinstellungen Gruppe
        self.export_group = QGroupBox("Exporteinstellungen")
        export_layout = QGridLayout(self.export_group)
        export_layout.setSpacing(6)
        export_layout.setContentsMargins(8, 8, 8, 8)
        
        # 1. Format — bewusst NICHT editierbar: currentTextChanged würde sonst
        # bei jedem Tastendruck das Settings-Dict umbauen und die Dateiendung
        # auf Tippfragmente setzen.
        export_layout.addWidget(QLabel("Format:"), 0, 0)
        self.combo_format = QComboBox()
        # Bildformate nur für Bild-Quellen anbieten, Video-Formate nur für
        # Video-/Audio-Quellen (Quelle steht im Dialog fest).
        source_is_image = presets.is_image_input(self.input_file)
        self.combo_format.addItems(presets.get_format_options(source_is_image))
        self.combo_format.currentTextChanged.connect(self._on_format_changed)
        export_layout.addWidget(self.combo_format, 0, 1)

        # 2. Preset (ebenfalls nicht editierbar, gleiche Begründung)
        export_layout.addWidget(QLabel("Vorgabe:"), 1, 0)
        self.combo_preset = QComboBox()
        self.combo_preset.addItems(presets.get_preset_dropdown_options(source_is_image))
        self.combo_preset.currentTextChanged.connect(self._on_preset_changed)
        export_layout.addWidget(self.combo_preset, 1, 1)
        
        # 3. Output Name (Als blauer Link exakt wie in AME)
        export_layout.addWidget(QLabel("Ausgabename:"), 2, 0)
        self.lbl_output_link = QLabel(os.path.basename(self.output_file))
        self.lbl_output_link.setObjectName("link_label")
        self.lbl_output_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_output_link.setToolTip(self.output_file)
        self.lbl_output_link.mousePressEvent = self._on_output_link_clicked
        export_layout.addWidget(self.lbl_output_link, 2, 1)
        
        # 4. Checkboxes Video / Audio exportieren
        chk_layout = QHBoxLayout()
        self.chk_export_video = QCheckBox("Video exportieren")
        self.chk_export_video.setChecked(True)
        self.chk_export_video.stateChanged.connect(self._on_export_video_toggled)
        self.chk_export_audio = QCheckBox("Audio exportieren")
        self.chk_export_audio.setChecked(True)
        self.chk_export_audio.stateChanged.connect(self._on_export_audio_toggled)
        chk_layout.addWidget(self.chk_export_video)
        chk_layout.addWidget(self.chk_export_audio)
        export_layout.addLayout(chk_layout, 3, 0, 1, 2)
        
        right_layout.addWidget(self.export_group)
        
        # Zusammenfassung (Summary)
        self.summary_box = QLabel()
        self.summary_box.setObjectName("summary_box")
        self.summary_box.setWordWrap(True)
        right_layout.addWidget(self.summary_box)
        
        # Tabs für Video/Audio-Parameter
        self.settings_tabs = QTabWidget()
        
        # --- VIDEO TAB ---
        video_tab = QWidget()
        v_tab_layout = QVBoxLayout(video_tab)
        v_tab_layout.setContentsMargins(8, 8, 8, 8)
        v_tab_layout.setSpacing(6)
        
        v_grid = QGridLayout()
        v_grid.setSpacing(6)
        
        # Video Codec
        self.lbl_video_codec = QLabel("Video-Codec:")
        v_grid.addWidget(self.lbl_video_codec, 0, 0)
        self.combo_vcodec = QComboBox()
        self.combo_vcodec.setEditable(True)
        self.combo_vcodec.addItems(["libx264", "libx265", "libvpx-vp9", "libsvtav1", "copy", "none"])
        self.combo_vcodec.currentTextChanged.connect(self._on_vcodec_changed)
        v_grid.addWidget(self.combo_vcodec, 0, 1)
        
        # Skalierung (Quelle beibehalten / einpassen / verzerren)
        self.lbl_scale_mode = QLabel("Skalierung:")
        v_grid.addWidget(self.lbl_scale_mode, 1, 0)
        self.combo_scale_mode = QComboBox()
        self.combo_scale_mode.addItems(presets.scale_mode_options())
        self.combo_scale_mode.currentTextChanged.connect(self._on_scale_mode_changed)
        v_grid.addWidget(self.combo_scale_mode, 1, 1)

        # Breite / Höhe
        self.lbl_video_width = QLabel("Breite:")
        v_grid.addWidget(self.lbl_video_width, 2, 0)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(16, 7680)
        self.spin_width.setValue(1920)
        self.spin_width.valueChanged.connect(lambda _v: self._on_size_spin_changed("width"))
        v_grid.addWidget(self.spin_width, 2, 1)

        self.lbl_video_height = QLabel("Höhe:")
        v_grid.addWidget(self.lbl_video_height, 3, 0)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(16, 4320)
        self.spin_height.setValue(1080)
        self.spin_height.valueChanged.connect(lambda _v: self._on_size_spin_changed("height"))
        v_grid.addWidget(self.spin_height, 3, 1)

        # Frame Rate ("Wie Quelle" = kein -r; unabhängig von der Skalierung)
        self.lbl_video_fps = QLabel("Framerate:")
        v_grid.addWidget(self.lbl_video_fps, 4, 0)
        self.combo_fps = QComboBox()
        self.combo_fps.setEditable(True)
        self.combo_fps.addItems([presets.FPS_SOURCE_LABEL, "23.976", "24", "25", "29.97", "30", "50", "60"])
        self.combo_fps.setCurrentText("25")
        v_grid.addWidget(self.combo_fps, 4, 1)

        # Profile / Level
        self.lbl_video_profile = QLabel("Profil:")
        v_grid.addWidget(self.lbl_video_profile, 5, 0)
        self.combo_profile = QComboBox()
        self.combo_profile.setEditable(True)
        self.combo_profile.addItems(["Main", "High", "Baseline"])
        self.combo_profile.setCurrentText("High")
        v_grid.addWidget(self.combo_profile, 5, 1)

        # Bitrate-Codierung
        self.lbl_video_encoding = QLabel("Bitrate-Codierung:")
        v_grid.addWidget(self.lbl_video_encoding, 6, 0)
        self.combo_encoding = QComboBox()
        self.combo_encoding.addItems(["VBR, 1 Durchgang", "CBR", "CRF (Qualitätsbasiert)"])
        self.combo_encoding.currentTextChanged.connect(self._on_encoding_method_changed)
        v_grid.addWidget(self.combo_encoding, 6, 1)

        # Target Bitrate / CRF (Synchronisierter Schieberegler + SpinBox)
        self.lbl_bitrate_val = QLabel("Zielbitrate (Mbps):")
        v_grid.addWidget(self.lbl_bitrate_val, 7, 0)
        
        bitrate_layout = QHBoxLayout()
        bitrate_layout.setSpacing(6)
        
        self.slider_bitrate = QSlider(Qt.Orientation.Horizontal)
        # Gleiche Grenzen wie im Hauptfenster (0.1–200 Mbps), sonst würde ein
        # dort gesetzter Wert beim Öffnen des Dialogs still geclampt.
        self.slider_bitrate.setRange(1, 2000)
        self.slider_bitrate.setValue(80)       # Standard 8.0 Mbps
        self.slider_bitrate.valueChanged.connect(self._on_slider_bitrate_changed)
        bitrate_layout.addWidget(self.slider_bitrate)

        self.spin_bitrate_val = QDoubleSpinBox()
        self.spin_bitrate_val.setRange(0.1, 200.0)
        self.spin_bitrate_val.setValue(8.0)
        self.spin_bitrate_val.setSingleStep(0.5)
        self.spin_bitrate_val.setDecimals(1)
        self.spin_bitrate_val.setFixedWidth(80)
        self.spin_bitrate_val.valueChanged.connect(self._on_spin_bitrate_changed)
        bitrate_layout.addWidget(self.spin_bitrate_val)
        
        v_grid.addLayout(bitrate_layout, 7, 1)

        # Intelligenter Modus Button
        self.btn_intelligent_mode = QPushButton("Intelligenter Modus...")
        self.btn_intelligent_mode.clicked.connect(self._on_intelligent_mode_clicked)
        v_grid.addWidget(self.btn_intelligent_mode, 8, 0, 1, 2)
        
        v_tab_layout.addLayout(v_grid)
        v_tab_layout.addStretch()
        self.settings_tabs.addTab(video_tab, "Video")
        
        # --- AUDIO TAB ---
        audio_tab = QWidget()
        a_tab_layout = QVBoxLayout(audio_tab)
        a_tab_layout.setContentsMargins(8, 8, 8, 8)
        a_tab_layout.setSpacing(6)
        
        a_grid = QGridLayout()
        a_grid.setSpacing(6)
        
        # Audio Codec
        a_grid.addWidget(QLabel("Audio-Format / Codec:"), 0, 0)
        self.combo_audiocodec = QComboBox()
        self.combo_audiocodec.setEditable(True)
        self.combo_audiocodec.addItems(["AAC", "MP3", "Opus", "FLAC", "Kopieren (Copy)"])
        self.combo_audiocodec.currentTextChanged.connect(self._on_audio_codec_changed)
        a_grid.addWidget(self.combo_audiocodec, 0, 1)
        
        # Audio Bitrate
        a_grid.addWidget(QLabel("Audio-Bitrate:"), 1, 0)
        self.combo_audiobitrate = QComboBox()
        self.combo_audiobitrate.setEditable(True)
        self.combo_audiobitrate.addItems(["128k", "192k", "256k", "320k"])
        self.combo_audiobitrate.setCurrentText("192k")
        a_grid.addWidget(self.combo_audiobitrate, 1, 1)
        
        a_tab_layout.addLayout(a_grid)
        a_tab_layout.addStretch()
        self.settings_tabs.addTab(audio_tab, "Audio")
        
        # --- UNTERTITEL TAB ---
        subtitle_tab = QWidget()
        sub_tab_layout = QVBoxLayout(subtitle_tab)
        sub_tab_layout.setContentsMargins(8, 8, 8, 8)
        sub_tab_layout.setSpacing(6)
        
        sub_grid = QGridLayout()
        sub_grid.setSpacing(6)
        
        # 1. Audio transkribieren & prüfen
        self.btn_transcribe = QPushButton("Untertitel jetzt per KI erzeugen...")
        self.btn_transcribe.setObjectName("btn_ai_subtitles")
        self.btn_transcribe.setToolTip("Erzeugt sofort eine SRT-Datei aus der Audiospur und öffnet sie zur Prüfung.")
        self.btn_transcribe.clicked.connect(self._on_transcribe_clicked)
        sub_grid.addWidget(self.btn_transcribe, 0, 0, 1, 2)
        
        # 2. Audiosprache
        sub_grid.addWidget(QLabel("Audiosprache:"), 1, 0)
        source_layout = QHBoxLayout()
        self.combo_sub_source = QComboBox()
        self.combo_sub_source.addItems([
            "Automatisch erkennen",
            "Deutsch (DE)",
            "English (US)",
            "Francais (F)",
            "Spanisch",
            "Chinesisch",
            "Japanisch",
            "Italienisch",
            "Andere..."
        ])
        self.combo_sub_source.currentTextChanged.connect(self._on_sub_source_changed)
        source_layout.addWidget(self.combo_sub_source)
        
        self.edit_sub_source_custom = QLineEdit()
        self.edit_sub_source_custom.setPlaceholderText("Sprache eingeben...")
        self.edit_sub_source_custom.setVisible(False)
        source_layout.addWidget(self.edit_sub_source_custom)
        sub_grid.addLayout(source_layout, 1, 1)
        
        # 3. Übersetzung
        sub_grid.addWidget(QLabel("Übersetzung:"), 2, 0)
        translate_layout = QHBoxLayout()
        self.combo_sub_translate = QComboBox()
        self.combo_sub_translate.addItems([
            "Keine (Originalsprache)",
            "Deutsch (DE)",
            "English (US)",
            "Francais (F)",
            "Spanisch",
            "Chinesisch",
            "Japanisch",
            "Italienisch",
            "Andere..."
        ])
        self.combo_sub_translate.currentTextChanged.connect(self._on_sub_translate_changed)
        translate_layout.addWidget(self.combo_sub_translate)
        
        self.edit_sub_translate_custom = QLineEdit()
        self.edit_sub_translate_custom.setPlaceholderText("Sprache eingeben...")
        self.edit_sub_translate_custom.setVisible(False)
        translate_layout.addWidget(self.edit_sub_translate_custom)
        sub_grid.addLayout(translate_layout, 2, 1)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sub_grid.addWidget(sep, 3, 0, 1, 2)
        
        # 4. Checkbox: KI-Untertitel hinzufügen
        self.chk_subtitles = QCheckBox("KI-Untertitel automatisch erzeugen und hinzufügen")
        self.chk_subtitles.setToolTip("Beim Export wird automatisch eine SRT aus der Audiospur erzeugt und optional übersetzt.")
        self.chk_subtitles.stateChanged.connect(self._on_subtitles_toggled)
        sub_grid.addWidget(self.chk_subtitles, 4, 0, 1, 2)
        
        # 5. Optionaler Untertiteldatei-Pfad
        sub_grid.addWidget(QLabel("Optionale .srt-Datei:"), 5, 0)
        path_layout = QHBoxLayout()
        self.edit_sub_file_path = QLineEdit()
        self.edit_sub_file_path.setPlaceholderText("Automatisch beim Export")
        self.edit_sub_file_path.setToolTip("Optional: vorhandene .srt verwenden. Leer lassen, damit die KI sie beim Export erzeugt.")
        path_layout.addWidget(self.edit_sub_file_path)
        
        self.btn_browse_sub_file = QPushButton("Durchsuchen...")
        self.btn_browse_sub_file.clicked.connect(self._on_browse_sub_file_clicked)
        path_layout.addWidget(self.btn_browse_sub_file)
        sub_grid.addLayout(path_layout, 5, 1)
        
        # 6. Methode
        sub_grid.addWidget(QLabel("Methode:"), 6, 0)
        self.combo_sub_mode = QComboBox()
        self.combo_sub_mode.addItems([
            "Soft-Untertitel (in Container einbetten)",
            "Hard-Untertitel (in Video einbrennen)",
            "Nur externe .srt-Datei erzeugen"
        ])
        sub_grid.addWidget(self.combo_sub_mode, 6, 1)
        
        sub_tab_layout.addLayout(sub_grid)
        sub_tab_layout.addStretch()
        self.settings_tabs.addTab(subtitle_tab, "Untertitel")
        
        right_layout.addWidget(self.settings_tabs)
        
        # OK / Cancel Buttons unten rechts
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        # Style für OK/Abbrechen Buttons anpassen
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("OK")
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Abbrechen")
        # Kein Default-Button: Enter in den Timecode-Feldern soll den Wert
        # übernehmen und NICHT den Dialog schließen bzw. Buttons auslösen.
        for btn in (btn_ok, btn_cancel):
            btn.setAutoDefault(False)
            btn.setDefault(False)
        
        right_layout.addWidget(buttons)
        
        main_layout.addWidget(right_widget, stretch=4)

    # --- DATENLADE-LOGIK ---
    def _load_settings_to_ui(self):
        """Setzt die anfänglichen Formularinhalte basierend auf self.settings."""
        self._loading_settings = True
        try:
            container = self.settings.get("container", "mp4").lower()
            vcodec = self.settings.get("video_codec", "libx264").lower()
            acodec = self.settings.get("audio_codec", "aac").lower()
            preset_name_for_settings = presets.get_preset_for_settings(self.settings)
            stored_label = str(self.settings.get("preset_label") or "").strip()
            custom_mode = bool(self.settings.get("custom_mode"))
            if (not custom_mode and not stored_label
                    and preset_name_for_settings == "Benutzerdefiniert"
                    and not (vcodec == "copy" and acodec == "copy")):
                custom_mode = True
            self.settings["custom_mode"] = custom_mode

            # Format auswählen. Stream-Copy darf dabei niemals einen Format-Handler
            # ausloesen, der den Video-Codec wieder auf libx264 zuruecksetzt.
            self.combo_format.blockSignals(True)
            self.combo_format.setCurrentText(presets.format_option_for_settings(self.settings))
            self.combo_format.blockSignals(False)

            self.chk_export_video.blockSignals(True)
            self.chk_export_audio.blockSignals(True)
            self.chk_export_video.setChecked(vcodec != "none")
            self.chk_export_audio.setChecked(acodec != "none")
            self.chk_export_video.blockSignals(False)
            self.chk_export_audio.blockSignals(False)
            self.settings_tabs.setTabEnabled(0, vcodec != "none")
            self.settings_tabs.setTabEnabled(1, acodec != "none")

            # Video Codec Tab befüllen
            self._sync_video_codec_combobox(container, custom_mode)
            self.combo_vcodec.blockSignals(True)
            self.combo_vcodec.setCurrentText(vcodec)
            self.combo_vcodec.blockSignals(False)

            # Skalierungsmodus / Breite / Höhe / Framerate / Profil laden
            self.combo_scale_mode.blockSignals(True)
            self.spin_width.blockSignals(True)
            self.spin_height.blockSignals(True)
            self.combo_fps.blockSignals(True)
            self.combo_profile.blockSignals(True)
            self.combo_scale_mode.setCurrentText(
                presets.scale_mode_to_label(presets.get_scale_mode(self.settings))
            )
            # Ohne gespeicherte Zielgröße die Quellauflösung vorbelegen
            src = self.source_info or {}
            default_w = int(src["width"]) if src.get("width") else 1920
            default_h = int(src["height"]) if src.get("height") else 1080
            self.spin_width.setValue(int(self.settings.get("width") or default_w))
            self.spin_height.setValue(int(self.settings.get("height") or default_h))
            fps_setting = str(self.settings.get("fps", "") or "").strip()
            self.combo_fps.setCurrentText(fps_setting if fps_setting else presets.FPS_SOURCE_LABEL)
            self.combo_profile.setCurrentText(str(self.settings.get("profile", "High")))
            self.combo_scale_mode.blockSignals(False)
            self.spin_width.blockSignals(False)
            self.spin_height.blockSignals(False)
            self.combo_fps.blockSignals(False)
            self.combo_profile.blockSignals(False)

            self.combo_preset.blockSignals(True)
            if custom_mode:
                self.combo_preset.setCurrentText("Benutzerdefiniert")
            elif stored_label and self.combo_preset.findText(stored_label) != -1:
                self.combo_preset.setCurrentText(stored_label)
            elif preset_name_for_settings != "Benutzerdefiniert":
                self.combo_preset.setCurrentText(preset_name_for_settings)
            elif vcodec == "copy" and acodec == "copy":
                self.combo_preset.setCurrentText("Stream-Kopie (Verlustfrei)")
            else:
                self.combo_preset.setCurrentText("Benutzerdefiniert")
            self.combo_preset.blockSignals(False)

            # Bitrate / CRF auslesen und Slider/Spinbox synchron belegen
            crf = self.settings.get("crf", "")
            vbitrate = self.settings.get("video_bitrate", "")

            self.combo_encoding.blockSignals(True)
            self.slider_bitrate.blockSignals(True)
            self.spin_bitrate_val.blockSignals(True)

            mode = self.settings.get("encoding_mode", "")
            if container in presets.IMAGE_CONTAINERS:
                quality = int(self.settings.get("image_quality", 90) or 90)
                self.lbl_bitrate_val.setText("Qualität (%):")
                self.spin_bitrate_val.setDecimals(0)
                self.spin_bitrate_val.setRange(1, 100)
                self.spin_bitrate_val.setSingleStep(5)
                self.spin_bitrate_val.setValue(quality)
                self.slider_bitrate.setRange(1, 100)
                self.slider_bitrate.setValue(quality)
            elif crf and (mode in ("crf", "")):
                self.combo_encoding.setCurrentText("CRF (Qualitätsbasiert)")
                self.lbl_bitrate_val.setText("Qualitätsfaktor (CRF):")
                try:
                    val = float(crf)
                except (TypeError, ValueError):
                    val = 23.0
                self.spin_bitrate_val.setDecimals(1)
                self.spin_bitrate_val.setRange(0, 51)
                self.spin_bitrate_val.setSingleStep(1)
                self.spin_bitrate_val.setValue(val)
                self.slider_bitrate.setRange(0, 51)
                self.slider_bitrate.setValue(int(round(val)))
            else:
                self.combo_encoding.setCurrentText("CBR" if mode == "cbr" else "VBR, 1 Durchgang")
                self.lbl_bitrate_val.setText("Zielbitrate (Mbps):")
                self.spin_bitrate_val.setDecimals(1)
                self.spin_bitrate_val.setRange(0.1, 200.0)
                self.spin_bitrate_val.setSingleStep(0.5)
                self.slider_bitrate.setRange(1, 2000)

                if vbitrate:
                    try:
                        num_val = float(vbitrate.replace("M", "").replace("k", ""))
                        self.spin_bitrate_val.setValue(num_val)
                        self.slider_bitrate.setValue(int(num_val * 10))
                    except ValueError:
                        self.spin_bitrate_val.setValue(8.0)
                        self.slider_bitrate.setValue(80)
                else:
                    self.spin_bitrate_val.setValue(8.0)
                    self.slider_bitrate.setValue(80)

            self.combo_encoding.blockSignals(False)
            self.slider_bitrate.blockSignals(False)
            self.spin_bitrate_val.blockSignals(False)

            # Audio Tab
            self._sync_audio_codec_combobox()
            self.combo_audiocodec.setCurrentText(presets.audio_codec_to_label(acodec))

            abitrate = self.settings.get("audio_bitrate", "192k")
            self.combo_audiobitrate.setCurrentText(abitrate)

            # Subtitle Tab befüllen
            self.chk_subtitles.blockSignals(True)
            self.combo_sub_source.blockSignals(True)
            self.combo_sub_translate.blockSignals(True)
            self.combo_sub_mode.blockSignals(True)
            self.combo_sub_source.setCurrentText(self.settings.get("subtitles_source", "Automatisch erkennen"))
            self.edit_sub_source_custom.setText(self.settings.get("subtitles_source_custom", ""))
            self.combo_sub_translate.setCurrentText(self.settings.get("subtitles_translate", "Keine (Originalsprache)"))
            self.edit_sub_translate_custom.setText(self.settings.get("subtitles_translate_custom", ""))
            self.chk_subtitles.setChecked(bool(self.settings.get("subtitles_enabled", False)))
            self.edit_sub_file_path.setText(self.settings.get("subtitles_file_path", ""))
            self.combo_sub_mode.setCurrentText(self.settings.get("subtitles_mode", "Soft-Untertitel (in Container einbetten)"))
            
            # Visibility toggles manually call
            self._on_sub_source_changed(self.combo_sub_source.currentText())
            self._on_sub_translate_changed(self.combo_sub_translate.currentText())
            
            self.chk_subtitles.blockSignals(False)
            self.combo_sub_source.blockSignals(False)
            self.combo_sub_translate.blockSignals(False)
            self.combo_sub_mode.blockSignals(False)
        finally:
            self._loading_settings = False

        self._update_widget_visibilities()

    def _update_summary(self):
        """Aktualisiert das Summary-Feld wie bei Adobe Media Encoder."""
        in_file = os.path.basename(self.input_file)
        out_ext = self.settings.get("container", "mp4")
        
        vcodec = self.settings.get("video_codec", "libx264")
        acodec = self.settings.get("audio_codec", "aac")
        
        v_bitrate = self.settings.get("video_bitrate", "")
        crf = self.settings.get("crf", "")
        a_bitrate = self.settings.get("audio_bitrate", "")
        scale_mode = presets.get_scale_mode(self.settings)
        keep_source_size = scale_mode == presets.SCALE_MODE_SOURCE
        scale_note = " (verzerrt)" if scale_mode == presets.SCALE_MODE_STRETCH else ""

        rate_mode = "CBR" if self.settings.get("encoding_mode") == "cbr" else "VBR"

        # Video Summary String
        is_image = self._is_image_container()
        if is_image:
            size_info = "Quelle beibehalten" if keep_source_size else f"{self.spin_width.value()}x{self.spin_height.value()}{scale_note}"
            crop = presets.get_crop(self.settings)
            if crop:
                size_info = f"Zuschnitt {crop['w']}x{crop['h']}, {size_info}"
            quality = self.settings.get("image_quality", 90)
            quality_info = "verlustfrei" if vcodec == "png" else f"Qualität {quality} %"
            v_sum = f"Bild: {presets.format_label(self.settings)}, {size_info}, {quality_info}"
        elif vcodec == "none":
            v_sum = "Kein Videoexport"
        elif vcodec == "copy":
            v_sum = "Video: Kopieren (Stream Copy)"
        elif keep_source_size:
            v_encoding = "CRF " + crf if crf else f"{rate_mode} {v_bitrate}"
            v_sum = f"Video: {vcodec}, Quelle beibehalten, {v_encoding}"
        else:
            v_encoding = "CRF " + crf if crf else f"{rate_mode} {v_bitrate}"
            v_sum = f"Video: {vcodec}, {self.spin_width.value()}x{self.spin_height.value()}{scale_note} ({self.combo_fps.currentText()} fps), {v_encoding}"
            
        # Audio Summary String
        if acodec == "none":
            a_sum = "Kein Audioexport"
        elif acodec == "copy":
            a_sum = "Audio: Kopieren (Stream Copy)"
        else:
            a_sum = f"Audio: {acodec}, {a_bitrate}"
            
        # Echte Quell-Infozeilen aus ffprobe aufbauen (mit robusten Fallbacks)
        info = self.source_info or {}
        src_lines = []
        if info.get("width") and info.get("height"):
            v_line = f"{info['width']}x{info['height']}"
            if info.get("fps"):
                v_line += f", {info['fps']:.2f} fps"
            if info.get("duration"):
                v_line += f", {self._format_timecode(info['duration'])}"
            if info.get("v_codec"):
                v_line += f" ({info['v_codec']})"
            src_lines.append(v_line)
        if info.get("a_codec"):
            a_line = info["a_codec"].upper()
            if info.get("a_bitrate"):
                a_line += f", {info['a_bitrate']} kbps"
            if info.get("a_rate"):
                try:
                    a_line += f", {int(info['a_rate']) // 1000} kHz"
                except (TypeError, ValueError):
                    pass
            if info.get("a_channels"):
                ch = {1: "Mono", 2: "Stereo"}.get(info["a_channels"], f"{info['a_channels']} ch")
                a_line += f", {ch}"
            src_lines.append(a_line)
        if not src_lines:
            src_lines.append("Keine Medieninformationen verfügbar")
        src_block = "<br>".join(src_lines)

        summary_text = (
            f"<b>Quelle:</b> {in_file}<br>"
            f"{src_block}<br><br>"
            f"<b>Ausgabe:</b> {os.path.basename(self.output_file)}<br>"
            f"{v_sum}"
        )
        if not is_image:
            summary_text += f"<br>{a_sum}"
            size_est = self._estimate_output_size()
            if size_est:
                summary_text += f"<br><b>Geschätzte Größe:</b> {size_est}"
        self.summary_box.setText(summary_text)
        # Trim-Anzeige (Keyframe-Hinweis, Bereichsleiste) folgt der Codec-Wahl
        if hasattr(self, "lbl_trim_info"):
            self._update_trim_ui()

    def _estimate_output_size(self):
        """Schätzt die Ausgabegröße aus Bitraten bzw. anteiliger Quellgröße
        (bei Stream-Copy). CRF-Encodes sind inhaltsabhängig — keine Schätzung."""
        info = self.source_info or {}
        duration = info.get("duration", 0.0) or 0.0
        if duration <= 0:
            return None

        trim_start = presets.parse_seconds(self.settings.get("trim_start")) or 0.0
        trim_end = presets.parse_seconds(self.settings.get("trim_end"))
        end = min(trim_end, duration) if (trim_end and trim_end > trim_start) else duration
        eff_duration = max(0.0, end - min(trim_start, duration))
        if eff_duration <= 0:
            return None

        try:
            src_size = os.path.getsize(self.input_file)
        except OSError:
            src_size = 0
        src_total_bps = (src_size * 8 / duration) if src_size else 0
        src_audio_bps = (info.get("a_bitrate") or 0) * 1000  # a_bitrate ist kbps
        src_video_bps = max(0, src_total_bps - src_audio_bps)

        v_codec = str(self.settings.get("video_codec", "libx264")).strip().lower()
        if v_codec == "none":
            v_bps = 0.0
        elif v_codec == "copy":
            if not src_total_bps:
                return None
            v_bps = src_video_bps
        elif self.settings.get("encoding_mode") == "crf" or (
            self.settings.get("crf") and not self.settings.get("video_bitrate")
        ):
            return None
        else:
            v_bps = self._bitrate_to_bps(self.settings.get("video_bitrate"))
            if v_bps is None:
                return None

        a_codec = presets._resolve_audio_codec(self.settings).lower()
        if a_codec == "none" or not info.get("a_codec"):
            a_bps = 0.0
        elif a_codec == "copy":
            a_bps = src_audio_bps
        else:
            a_bps = self._bitrate_to_bps(self.settings.get("audio_bitrate"))
            if a_bps is None:
                return None  # z. B. FLAC ohne Bitrate: nicht seriös schätzbar

        total_bytes = (v_bps + a_bps) / 8.0 * eff_duration * 1.02  # +2 % Mux-Overhead
        if total_bytes <= 0:
            return None
        return "≈ " + self._format_size(total_bytes)

    @staticmethod
    def _bitrate_to_bps(value):
        """'8M' / '192k' / '800000' → Bits pro Sekunde, sonst None."""
        m = re.match(r"^\s*([\d.]+)\s*([kKmMgG]?)", str(value or ""))
        if not m:
            return None
        try:
            val = float(m.group(1))
        except ValueError:
            return None
        return val * {"k": 1e3, "m": 1e6, "g": 1e9}.get(m.group(2).lower(), 1.0)

    @staticmethod
    def _format_size(num_bytes):
        if num_bytes >= 1e9:
            return f"{num_bytes / 1e9:.2f} GB"
        if num_bytes >= 1e6:
            return f"{num_bytes / 1e6:.1f} MB"
        return f"{num_bytes / 1e3:.0f} kB"

    # --- UI INTERACTIONS ---
    def _get_container_from_format_text(self, text):
        return presets.container_from_format_text(text)

    def _is_custom_mode(self):
        return (
            self.combo_preset.currentText() == "Benutzerdefiniert"
            or bool(self.settings.get("custom_mode"))
        )

    def _is_image_container(self):
        """True, wenn die aktuellen Einstellungen ein Bildformat beschreiben."""
        return str(self.settings.get("container", "")).lower() in presets.IMAGE_CONTAINERS

    def _set_settings_tab_visible(self, index, visible):
        """Qt-Versionen ohne setTabVisible fallen auf deaktivierte Tabs zurück."""
        if hasattr(self.settings_tabs, "setTabVisible"):
            self.settings_tabs.setTabVisible(index, visible)
        self.settings_tabs.setTabEnabled(index, visible and self.settings_tabs.isTabEnabled(index))

    def _apply_media_ui_mode(self, is_image):
        """Schaltet sichtbare Begriffe und Bedienelemente zwischen Video und Bild."""
        self.setWindowTitle("Bildeinstellungen" if is_image else "Exporteinstellungen")
        self.export_group.setTitle("Bildeinstellungen" if is_image else "Exporteinstellungen")

        if is_image:
            self.chk_export_video.setText("Bild exportieren")
            self.lbl_video_codec.setText("Bild-Codec:")
            self.settings_tabs.setTabText(0, "Bild")
        else:
            self.chk_export_video.setText("Video exportieren")
            self.lbl_video_codec.setText("Video-Codec:")
            self.settings_tabs.setTabText(0, "Video")

        self.chk_export_audio.setVisible(not is_image)
        self.timeline_widget.setVisible(not is_image)
        self.timecode_widget.setVisible(not is_image)
        self.trim_widget.setVisible(not is_image)
        self._set_settings_tab_visible(1, not is_image)
        self._set_settings_tab_visible(2, not is_image)
        if is_image:
            self.settings_tabs.setCurrentIndex(0)

        for widget in (
            self.lbl_video_fps,
            self.combo_fps,
            self.lbl_video_profile,
            self.combo_profile,
            self.lbl_video_encoding,
            self.combo_encoding,
            self.btn_intelligent_mode,
        ):
            widget.setVisible(not is_image)

    def _sync_video_codec_combobox(self, container=None, custom=None):
        container = container or self.settings.get("container", "mp4")
        custom = self._is_custom_mode() if custom is None else custom
        current_codec = self.combo_vcodec.currentText()
        self.combo_vcodec.blockSignals(True)
        self.combo_vcodec.clear()
        self.combo_vcodec.addItems(presets.get_video_codec_options(container, custom))
        if current_codec:
            self.combo_vcodec.setCurrentText(current_codec)
        self.combo_vcodec.blockSignals(False)

    def _set_output_extension(self, container):
        base_dir = os.path.dirname(self.output_file)
        base_name = os.path.basename(self.output_file)
        root_name, _ = os.path.splitext(base_name)
        self.output_file = os.path.join(base_dir, f"{root_name}.{container}")
        self.lbl_output_link.setText(os.path.basename(self.output_file))
        self.lbl_output_link.setToolTip(self.output_file)

    def _on_format_changed(self, text):
        """Passt Container und Codecs an das gewählte AME-Format an."""
        if getattr(self, "_loading_settings", False):
            return

        self.chk_export_video.setEnabled(True)
        self.chk_export_audio.setEnabled(True)
        custom_mode = self._is_custom_mode()
        defaults = presets.default_settings_for_format(text)

        if custom_mode:
            self.settings["container"] = presets.container_from_format_text(text)
            self.settings["custom_mode"] = True
            self.settings.setdefault("video_codec", "libx264")
            self.settings.setdefault("audio_codec", "aac")
        elif text in ("JPEG (Bild)", "PNG (Bild)", "WebP (Bild)", "AVIF (Bild)"):
            keep_crop = presets.get_crop(self.settings)
            self.settings = defaults
            if keep_crop:
                self.settings["crop"] = keep_crop
            self.chk_export_video.setChecked(True)
            self.chk_export_video.setEnabled(False)
            self.chk_export_audio.setChecked(False)
            self.chk_export_audio.setEnabled(False)
            self.settings["custom_mode"] = False
            self._set_output_extension(self.settings["container"])
            # Komplett neu laden, damit der Qualitätsregler (statt Bitrate) erscheint
            self._load_settings_to_ui()
            self._update_summary()
            return
        elif defaults is not None:
            # Im Dialog nur Container/Codecs übernehmen — Auflösung, FPS und
            # Bitraten des Benutzers bleiben beim Format-Wechsel erhalten.
            self.settings["container"] = defaults["container"]
            self.settings["video_codec"] = defaults["video_codec"]
            self.settings["audio_codec"] = defaults["audio_codec"]
            self.settings["custom_mode"] = False
            if defaults["video_codec"] == "none":
                # Reines Audio-Format: Checkboxen fest verdrahten
                self.chk_export_video.setChecked(False)
                self.chk_export_video.setEnabled(False)
                self.chk_export_audio.setChecked(True)
                self.chk_export_audio.setEnabled(False)
                self.settings["audio_bitrate"] = defaults["audio_bitrate"]
        else:
            container = presets.container_from_format_text(text)
            self.settings["container"] = container
            if "video_codec" not in self.settings:
                self.settings["video_codec"] = "libx264"
            if "audio_codec" not in self.settings:
                self.settings["audio_codec"] = "aac"
            self.settings["custom_mode"] = False

        if not custom_mode:
            self.settings["custom_mode"] = False

        # Checkboxen an die neuen Codecs angleichen (z. B. Rückwechsel von
        # "MP3 (Nur Audio)" zu H.264: Video-Export muss wieder aktiv werden).
        self.chk_export_video.blockSignals(True)
        self.chk_export_audio.blockSignals(True)
        self.chk_export_video.setChecked(self.settings.get("video_codec", "none") != "none")
        self.chk_export_audio.setChecked(self.settings.get("audio_codec", "none") != "none")
        self.chk_export_video.blockSignals(False)
        self.chk_export_audio.blockSignals(False)

        # Video Codecs passend zum Container füllen
        self._sync_video_codec_combobox(self.settings["container"], custom_mode)
        self.combo_vcodec.blockSignals(True)
        self.combo_vcodec.setCurrentText(self.settings["video_codec"])
        self.combo_vcodec.blockSignals(False)

        # Dateipfad-Endung aktualisieren
        self._set_output_extension(self.settings["container"])
        
        # Audio-Auswahlboxen filtern
        self._sync_audio_codec_combobox()
        self._update_widget_visibilities()
        self._update_summary()

    def _sync_audio_codec_combobox(self):
        """Aktualisiert die Audio-Codec-Auswahlliste."""
        container = self.settings["container"]
        custom = self._is_custom_mode()
        current_codec = presets.audio_label_to_codec(self.combo_audiocodec.currentText())
        self.combo_audiocodec.blockSignals(True)
        self.combo_audiocodec.clear()
        self.combo_audiocodec.addItems(presets.get_audio_codec_labels(container, custom))
            
        # Standardwert setzen
        acodec = self.settings.get("audio_codec", current_codec or "aac")
        self.combo_audiocodec.setCurrentText(presets.audio_codec_to_label(acodec))
            
        self.combo_audiocodec.blockSignals(False)

    def _default_audio_codec_for_current_container(self):
        """Erster sinnvoller Audio-Codec fuer den aktuellen Container."""
        options = presets.get_audio_codec_options(self.settings.get("container", "mp4"), self._is_custom_mode())
        for codec in options:
            if codec != "none":
                return codec
        return "none"

    def _on_preset_changed(self, text):
        """Aktualisiert Parameter bei Preset-Auswahl."""
        if getattr(self, "_loading_settings", False):
            return

        # Gewähltes Preset-Label merken, damit es nach dem Neuladen der UI
        # nicht als "Benutzerdefiniert" erscheint (Quick-Presets sind keine
        # exakten PRESETS-Treffer).
        if text == "Benutzerdefiniert":
            self.settings.pop("preset_label", None)
        else:
            self.settings["preset_label"] = text

        if text == "Benutzerdefiniert":
            self.settings["custom_mode"] = True
            mode = presets.scale_mode_from_label(self.combo_scale_mode.currentText())
            self.settings["scale_mode"] = mode
            self.settings["match_source"] = (mode == presets.SCALE_MODE_SOURCE)
            current_vcodec = self.combo_vcodec.currentText() or self.settings.get("video_codec", "libx264")
            current_acodec = presets.audio_label_to_codec(
                self.combo_audiocodec.currentText() or self.settings.get("audio_codec", "aac")
            )
            self._sync_video_codec_combobox(self.settings.get("container", "mp4"), custom=True)
            self.combo_vcodec.setCurrentText(current_vcodec)
            self._sync_audio_codec_combobox()
            self.combo_audiocodec.setCurrentText(presets.audio_codec_to_label(current_acodec))
            self._update_widget_visibilities()
            self._update_summary()
            return

        if text in presets.PRESETS:
            keep_crop = presets.get_crop(self.settings)
            # Untertitel- und Schnitt-Konfiguration überleben den Preset-Wechsel —
            # das Dict wird gleich komplett ersetzt und die UI daraus neu geladen.
            keep_subs = {k: self.settings[k] for k in presets.SUBTITLE_SETTING_KEYS if k in self.settings}
            keep_trim = {k: self.settings[k] for k in ("trim_start", "trim_end") if k in self.settings}
            self.settings = dict(presets.PRESETS[text])
            self.settings["custom_mode"] = False
            self.settings["preset_label"] = text
            if keep_crop and self.settings.get("container") in presets.IMAGE_CONTAINERS:
                self.settings["crop"] = keep_crop
            if self.settings.get("container") not in presets.IMAGE_CONTAINERS:
                if keep_subs:
                    self.settings.update(keep_subs)
                if keep_trim:
                    self.settings.update(keep_trim)
            self._set_output_extension(self.settings["container"])
            self._load_settings_to_ui()
            self._update_summary()
            return

        self.settings["custom_mode"] = False
        self.settings["match_source"] = False
        if self.settings.get("scale_mode") == presets.SCALE_MODE_SOURCE:
            self.settings["scale_mode"] = presets.SCALE_MODE_FIT
            self.combo_scale_mode.blockSignals(True)
            self.combo_scale_mode.setCurrentText(presets.scale_mode_to_label(presets.SCALE_MODE_FIT))
            self.combo_scale_mode.blockSignals(False)

        if text == "YouTube 1080p HD":
            self.spin_width.setValue(1920)
            self.spin_height.setValue(1080)
            self.combo_encoding.setCurrentText("VBR, 1 Durchgang")
            self.spin_bitrate_val.setValue(16.0)
            self.settings["encoding_mode"] = "vbr"
            self.settings["video_bitrate"] = "16M"
            self.settings["crf"] = ""
        elif text == "YouTube 720p HD":
            self.spin_width.setValue(1280)
            self.spin_height.setValue(720)
            self.combo_encoding.setCurrentText("VBR, 1 Durchgang")
            self.spin_bitrate_val.setValue(8.0)
            self.settings["encoding_mode"] = "vbr"
            self.settings["video_bitrate"] = "8M"
            self.settings["crf"] = ""
        elif text == "Hocheffizient (CRF 23)":
            self.combo_encoding.setCurrentText("CRF (Qualitätsbasiert)")
            self.spin_bitrate_val.setValue(23.0)
            self.settings["encoding_mode"] = "crf"
            self.settings["video_bitrate"] = ""
            self.settings["crf"] = "23"
        elif text == "Stream-Kopie (Verlustfrei)":
            self.settings["video_codec"] = "copy"
            self.settings["audio_codec"] = "copy"
            self.combo_vcodec.setCurrentText("copy")
            self.combo_audiocodec.setCurrentText("Kopieren (Copy)")

        self._update_widget_visibilities()
        self._update_summary()

    def _on_encoding_method_changed(self, text):
        """Schaltet zwischen Bitrate (Mbps) und CRF (Qualität) um und passt den Slider an."""
        if getattr(self, "_loading_settings", False):
            return

        self.slider_bitrate.blockSignals(True)
        self.spin_bitrate_val.blockSignals(True)
        
        if text == "CRF (Qualitätsbasiert)":
            self.lbl_bitrate_val.setText("Qualitätsfaktor (CRF):")
            self.spin_bitrate_val.setDecimals(1)
            self.spin_bitrate_val.setRange(0, 51)
            self.spin_bitrate_val.setSingleStep(1)
            self.spin_bitrate_val.setValue(23)

            self.slider_bitrate.setRange(0, 51)
            self.slider_bitrate.setValue(23)

            self.settings["encoding_mode"] = "crf"
            self.settings["video_bitrate"] = ""
            self.settings["crf"] = "23"
        else:
            self.lbl_bitrate_val.setText("Zielbitrate (Mbps):")
            self.spin_bitrate_val.setDecimals(1)
            self.spin_bitrate_val.setRange(0.1, 200.0)
            self.spin_bitrate_val.setSingleStep(0.5)
            self.spin_bitrate_val.setValue(8.0)

            self.slider_bitrate.setRange(1, 2000)
            self.slider_bitrate.setValue(80)

            self.settings["encoding_mode"] = "cbr" if text == "CBR" else "vbr"
            self.settings["video_bitrate"] = "8M"
            self.settings["crf"] = ""
            
        self.slider_bitrate.blockSignals(False)
        self.spin_bitrate_val.blockSignals(False)
        self._update_summary()

    def _on_audio_codec_changed(self, text):
        """Speichert den gewählten Audio-Codec in settings."""
        if getattr(self, "_loading_settings", False):
            return

        self.settings["audio_codec"] = presets.audio_label_to_codec(text)
        self._update_widget_visibilities()
        self._update_summary()

    def _on_export_video_toggled(self, state):
        """Aktiviert/Deaktiviert den Video-Export."""
        if getattr(self, "_loading_settings", False):
            return

        is_checked = state == 2
        if not is_checked:
            self.settings["video_codec"] = "none"
        else:
            # Fallback auf Standard-Codec für das Format
            fmt = self.combo_format.currentText()
            if "265" in fmt:
                self.settings["video_codec"] = "libx265"
            elif "VP9" in fmt:
                self.settings["video_codec"] = "libvpx-vp9"
            elif "AV1" in fmt:
                self.settings["video_codec"] = "libsvtav1"
            else:
                self.settings["video_codec"] = "libx264"
        self._update_tab_enables()
        self._update_summary()

    def _on_export_audio_toggled(self, state):
        """Aktiviert/Deaktiviert den Audio-Export."""
        if getattr(self, "_loading_settings", False):
            return

        is_checked = state == 2
        if not is_checked:
            self.settings["audio_codec"] = "none"
        else:
            self.settings["audio_codec"] = self._default_audio_codec_for_current_container()
            self._sync_audio_codec_combobox()
        self._update_tab_enables()
        self._update_summary()

    def _on_subtitles_toggled(self, state):
        self._update_widget_visibilities()
        self._update_summary()
        self._trigger_preview_update()

    def _on_sub_source_changed(self, text):
        show_custom = (text == "Andere...")
        self.edit_sub_source_custom.setVisible(show_custom)
        if show_custom:
            self.edit_sub_source_custom.setFocus()
        self._update_summary()

    def _on_sub_translate_changed(self, text):
        show_custom = (text == "Andere...")
        self.edit_sub_translate_custom.setVisible(show_custom)
        if show_custom:
            self.edit_sub_translate_custom.setFocus()
        self._update_summary()

    def _on_browse_sub_file_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Untertiteldatei auswählen", "", "SubRip Untertitel (*.srt)"
        )
        if file_path:
            self.edit_sub_file_path.setText(file_path)
            self._update_summary()
            self._trigger_preview_update()

    def _on_transcribe_clicked(self):
        src_lang = self.combo_sub_source.currentText()
        if src_lang == "Andere...":
            src_lang = self.edit_sub_source_custom.text().strip()
            if not src_lang:
                src_lang = "Andere"
                
        tr_lang = self.combo_sub_translate.currentText()
        if tr_lang == "Andere...":
            tr_lang = self.edit_sub_translate_custom.text().strip()
            if not tr_lang:
                tr_lang = "Andere"
                
        from subtitle_editor_dialog import SubtitleEditorDialog
        dialog = SubtitleEditorDialog(self.input_file, self.output_file, src_lang, tr_lang, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            saved_path = dialog.get_saved_srt_path()
            if saved_path:
                self.edit_sub_file_path.setText(saved_path)
                self.chk_subtitles.setChecked(True)
                self._update_summary()
                self._trigger_preview_update()

    def _on_slider_value_changed(self, value):
        duration = self.source_info.get("duration", 0.0) if self.source_info else 0.0
        if hasattr(self, "lbl_current_time"):
            seek = duration * (value / self.SLIDER_MAX)
            self.lbl_current_time.setText(self._format_timecode(seek))
        # Live-Vorschau beim Scrubben/Tastatur-Steppen (debounced)
        if duration > 0 and hasattr(self, "_preview_debounce"):
            self._preview_debounce.start()

    def _set_preview_image(self, image_path):
        """Zeigt das übergebene Vorschaubild oder den passenden Fallback an."""
        if not image_path or not os.path.exists(image_path):
            fallback = os.path.join(os.path.dirname(__file__), "sample_video_frame.png")
            image_path = fallback if os.path.exists(fallback) else None

        if image_path:
            pixmap = QPixmap(image_path).scaled(600, 340, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setPixmap(pixmap)
        else:
            # Reine Audio-Quelle o. Ä. -> kein Bild verfügbar
            is_audio = bool(self.source_info) and self.source_info.get("width") is None
            self.preview_label.setText("[ Nur Audio – keine Bildvorschau ]" if is_audio else "[ Video-Vorschau ]")

    def _trigger_preview_update(self, seek_seconds=None):
        """Extrahiert das Vorschaubild asynchron via QProcess.
        Die frühere synchrone Variante blockierte die UI bis zu 8 Sekunden
        (Dialog-Öffnen und jede Slider-Bewegung)."""
        if not self.input_file or not os.path.exists(self.input_file):
            self._set_preview_image(None)
            return
        # Reine Audio-Datei -> kein Frame
        if self.source_info and self.source_info.get("width") is None:
            self._set_preview_image(None)
            return

        # Nur die aktuellste Anforderung zählt: laufende Extraktion verwerfen
        if self._preview_proc and self._preview_proc.state() != QProcess.ProcessState.NotRunning:
            self._preview_proc.kill()

        import tempfile
        try:
            fd, out_path = tempfile.mkstemp(prefix="lme_preview_", suffix=".jpg")
            os.close(fd)
        except OSError:
            return
        self._preview_temp_files.add(out_path)

        duration = self.source_info.get("duration", 0.0) if self.source_info else 0.0
        if seek_seconds is not None:
            seek = seek_seconds
        else:
            slider_val = (
                self.time_slider.value() if hasattr(self, "time_slider")
                else int(0.18 * self.SLIDER_MAX)
            )
            seek = duration * (slider_val / self.SLIDER_MAX)

        filters = ["scale=600:-2"]
        # Untertitel einbrennen, falls aktiviert (Vorschau des Endergebnisses)
        sub_active = self.chk_subtitles.isChecked() if hasattr(self, "chk_subtitles") else bool(self.settings.get("subtitles_enabled"))
        srt_path = (self.edit_sub_file_path.text().strip() if hasattr(self, "edit_sub_file_path")
                    else str(self.settings.get("subtitles_file_path", "") or "").strip())
        if sub_active and srt_path and os.path.exists(srt_path):
            filters.append(presets.build_subtitles_filter(srt_path))

        args = [
            "-y", "-ss", f"{seek:.2f}", "-i", self.input_file,
            "-frames:v", "1", "-vf", ",".join(filters), "-q:v", "3", out_path,
        ]
        proc = QProcess(self)
        self._preview_proc = proc
        proc.finished.connect(
            lambda code, _status, pr=proc, p=out_path: self._on_preview_extracted(pr, p, code)
        )
        proc.errorOccurred.connect(
            lambda error, pr=proc: self._on_preview_failed_to_start(pr, error)
        )
        proc.start("ffmpeg", args)

    def _on_preview_extracted(self, proc, out_path, exit_code):
        if proc is not self._preview_proc:
            return  # veraltete Extraktion, wurde inzwischen ersetzt/verworfen
        self._preview_proc = None
        if exit_code == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            self.preview_frame_path = out_path
            self._set_preview_image(out_path)

    def _on_preview_failed_to_start(self, proc, error):
        """ffmpeg fehlt: 'finished' feuert nie — Fallback-Bild anzeigen."""
        if error != QProcess.ProcessError.FailedToStart or proc is not self._preview_proc:
            return
        self._preview_proc = None
        self._set_preview_image(None)

    def _update_tab_enables(self):
        """Fix für fehlende Funktion in der Original-Implementierung."""
        self._update_widget_visibilities()

    def _update_widget_visibilities(self):
        """Sperrt oder aktiviert Detail-Widgets basierend auf Codec-Auswahl."""
        is_image = self._is_image_container()
        is_audio_only = str(self.settings.get("container", "")).lower() in presets.AUDIO_ONLY_CONTAINERS

        if is_image:
            self.chk_export_video.blockSignals(True)
            self.chk_export_audio.blockSignals(True)
            self.chk_export_video.setChecked(True)
            self.chk_export_audio.setChecked(False)
            self.chk_export_video.blockSignals(False)
            self.chk_export_audio.blockSignals(False)

        self._apply_media_ui_mode(is_image)

        vcodec = self.combo_vcodec.currentText().lower()
        acodec = presets.audio_label_to_codec(self.combo_audiocodec.currentText()).lower()
        
        # Video-Export Checkbox-Status
        video_active = self.chk_export_video.isChecked()
        audio_active = self.chk_export_audio.isChecked()
        self.settings_tabs.setTabEnabled(0, video_active)
        self.settings_tabs.setTabEnabled(1, audio_active and not is_image)

        # Detail-Sperren bei Video-Kopie oder Deaktivierung
        video_editable = video_active and vcodec != "copy" and vcodec != "none"
        scale_mode = presets.scale_mode_from_label(self.combo_scale_mode.currentText())
        size_editable = video_editable and scale_mode != presets.SCALE_MODE_SOURCE
        self.combo_scale_mode.setEnabled(video_editable)
        self.spin_width.setEnabled(size_editable)
        self.spin_height.setEnabled(size_editable)
        # Framerate ist von der Skalierung unabhängig ("Wie Quelle" = kein -r)
        self.combo_fps.setEnabled(video_editable and not is_image)
        self.combo_profile.setEnabled(video_editable and not is_image)
        self.combo_encoding.setEnabled(video_editable and not is_image)
        # Bild: Qualitätsregler statt Bitrate — bei PNG (verlustfrei) gesperrt
        quality_editable = video_editable and not (is_image and vcodec == "png")
        self.slider_bitrate.setEnabled(quality_editable)
        self.spin_bitrate_val.setEnabled(quality_editable)
        self.btn_intelligent_mode.setEnabled(video_editable and not is_image)

        # Detail-Sperren bei Audio-Kopie oder Deaktivierung
        self.chk_export_video.setEnabled(not is_image and not is_audio_only)
        self.chk_export_audio.setEnabled(not is_image and not is_audio_only)
        audio_editable = audio_active and acodec not in ("copy", "none")
        lossless_audio = acodec in ("flac", "alac", "pcm_s16le", "pcm_s24le", "wavpack")
        self.combo_audiobitrate.setEnabled(audio_editable and not lossless_audio)

        # Detail-Sperren bei Untertiteln (für Bilder komplett gesperrt)
        self.settings_tabs.setTabEnabled(2, not is_image)
        self.chk_subtitles.setEnabled(not is_image)
        sub_active = self.chk_subtitles.isChecked() and not is_image
        self.edit_sub_file_path.setEnabled(sub_active)
        self.btn_browse_sub_file.setEnabled(sub_active)
        self.combo_sub_mode.setEnabled(sub_active)

    def _on_output_link_clicked(self, event):
        """Wird ausgelöst, wenn der Benutzer auf den blauen Pfad klickt (exakt AME-Verhalten)."""
        ext = self.settings.get("container", "mp4")
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Ausgabedatei festlegen", self.output_file, f"Format (*.{ext});;Alle Dateien (*)"
        )
        if file_path:
            self.output_file = file_path
            self.lbl_output_link.setText(os.path.basename(file_path))
            self.lbl_output_link.setToolTip(file_path)
            self._update_summary()

    def get_results(self):
        """Gibt die final konfigurierten Daten zurück."""
        # Codecs und Container aus den editierbaren Feldern auslesen.
        # Die Export-Checkboxen haben Vorrang: abgewähltes Video/Audio wird
        # als "none" gespeichert, egal was in den Codec-Feldern steht.
        if self.chk_export_video.isChecked():
            self.settings["video_codec"] = self.combo_vcodec.currentText()
        else:
            self.settings["video_codec"] = "none"

        if self.chk_export_audio.isChecked():
            self.settings["audio_codec"] = presets.audio_label_to_codec(self.combo_audiocodec.currentText())
        else:
            self.settings["audio_codec"] = "none"
        self.settings["custom_mode"] = self.combo_preset.currentText() == "Benutzerdefiniert"

        scale_mode = presets.scale_mode_from_label(self.combo_scale_mode.currentText())
        self.settings["scale_mode"] = scale_mode
        self.settings["match_source"] = (scale_mode == presets.SCALE_MODE_SOURCE)

        vcodec = str(self.settings["video_codec"]).lower()
        if self._is_image_container():
            # Bild-Export: Qualitätsregler statt Bitrate/CRF
            self.settings["width"] = self.spin_width.value()
            self.settings["height"] = self.spin_height.value()
            self.settings["image_quality"] = int(self.spin_bitrate_val.value())
            self.settings["encoding_mode"] = "image"
            self.settings["crf"] = ""
            self.settings["video_bitrate"] = ""
        elif vcodec in ("copy", "none"):
            self.settings["encoding_mode"] = vcodec
            self.settings["crf"] = ""
            self.settings["video_bitrate"] = ""
        else:
            # Breite / Höhe / Framerate / Profil abspeichern
            self.settings["width"] = self.spin_width.value()
            self.settings["height"] = self.spin_height.value()
            fps_text = self.combo_fps.currentText().strip()
            self.settings["fps"] = "" if fps_text.casefold() == presets.FPS_SOURCE_LABEL.casefold() else fps_text
            self.settings["profile"] = self.combo_profile.currentText()

            # Bitrate abspeichern vor Rückgabe
            enc = self.combo_encoding.currentText()
            if enc == "CRF (Qualitätsbasiert)":
                self.settings["encoding_mode"] = "crf"
                # %g erhält halbe CRF-Stufen (23.5), ohne "23.0" zu erzeugen
                self.settings["crf"] = f"{self.spin_bitrate_val.value():g}"
                self.settings["video_bitrate"] = ""
            else:
                self.settings["encoding_mode"] = "cbr" if enc == "CBR" else "vbr"
                self.settings["crf"] = ""
                self.settings["video_bitrate"] = presets.format_mbps(self.spin_bitrate_val.value())
            
        self.settings["audio_bitrate"] = self.combo_audiobitrate.currentText()
        
        # Subtitles Settings
        self.settings["subtitles_source"] = self.combo_sub_source.currentText()
        self.settings["subtitles_source_custom"] = self.edit_sub_source_custom.text()
        self.settings["subtitles_translate"] = self.combo_sub_translate.currentText()
        self.settings["subtitles_translate_custom"] = self.edit_sub_translate_custom.text()
        self.settings["subtitles_enabled"] = self.chk_subtitles.isChecked()
        self.settings["subtitles_file_path"] = self.edit_sub_file_path.text()
        self.settings["subtitles_mode"] = self.combo_sub_mode.currentText()
        
        return self.output_file, self.settings

    def _on_vcodec_changed(self, text):
        """Reagiert auf manuelle Eingabe des Video-Codecs (z. B. copy)."""
        if getattr(self, "_loading_settings", False):
            return

        self.settings["video_codec"] = text
        self._update_widget_visibilities()
        self._update_summary()

    def _on_scale_mode_changed(self, text):
        """Skalierungsmodus umgeschaltet: Größenfelder freigeben und Settings pflegen."""
        if getattr(self, "_loading_settings", False):
            return

        mode = presets.scale_mode_from_label(text)
        self.settings["scale_mode"] = mode
        self.settings["match_source"] = (mode == presets.SCALE_MODE_SOURCE)
        # Beim ersten Aktivieren der Skalierung die Quellauflösung vorbelegen
        if mode != presets.SCALE_MODE_SOURCE and not self.settings.get("width"):
            info = self.source_info or {}
            if info.get("width") and info.get("height"):
                self.spin_width.setValue(int(info["width"]))
                self.spin_height.setValue(int(info["height"]))
        # Bei AR-Erhalt die Höhe passend zur Breite ausrechnen
        self._sync_size_spins_to_aspect("width")
        self._update_widget_visibilities()
        self._update_summary()

    def _effective_aspect_source(self):
        """Maßgebliche Quellmaße für die Seitenverhältnis-Kopplung.
        Ein gesetzter Zuschnitt bestimmt das Seitenverhältnis, sonst die Quelle."""
        crop = presets.get_crop(self.settings)
        if crop:
            return crop["w"], crop["h"]
        info = self.source_info or {}
        if info.get("width") and info.get("height"):
            return int(info["width"]), int(info["height"])
        return None

    def _sync_size_spins_to_aspect(self, changed):
        """Hält Breite/Höhe im Modus 'Seitenverhältnis beibehalten' gekoppelt."""
        mode = presets.scale_mode_from_label(self.combo_scale_mode.currentText())
        if mode != presets.SCALE_MODE_FIT:
            return
        dims = self._effective_aspect_source()
        if not dims:
            return
        src_w, src_h = dims
        if changed == "width":
            self.spin_height.blockSignals(True)
            self.spin_height.setValue(round(self.spin_width.value() * src_h / src_w))
            self.spin_height.blockSignals(False)
        else:
            self.spin_width.blockSignals(True)
            self.spin_width.setValue(round(self.spin_height.value() * src_w / src_h))
            self.spin_width.blockSignals(False)

    def _on_size_spin_changed(self, changed):
        """Breite/Höhe manuell geändert: Gegenstück ggf. mitziehen."""
        if getattr(self, "_loading_settings", False):
            return
        self._sync_size_spins_to_aspect(changed)
        self._update_summary()

    def _on_slider_bitrate_changed(self, value):
        """Vom Slider zur Spinbox synchronisieren."""
        if getattr(self, "_loading_settings", False):
            return

        self.spin_bitrate_val.blockSignals(True)
        if self._is_image_container() or self.combo_encoding.currentText() == "CRF (Qualitätsbasiert)":
            self.spin_bitrate_val.setValue(value)
        else:
            self.spin_bitrate_val.setValue(value / 10.0)
        self.spin_bitrate_val.blockSignals(False)
        self._update_summary()

    def _on_spin_bitrate_changed(self, value):
        """Von der Spinbox zum Slider synchronisieren."""
        if getattr(self, "_loading_settings", False):
            return

        self.slider_bitrate.blockSignals(True)
        if self._is_image_container() or self.combo_encoding.currentText() == "CRF (Qualitätsbasiert)":
            self.slider_bitrate.setValue(int(value))
        else:
            self.slider_bitrate.setValue(int(value * 10))
        self.slider_bitrate.blockSignals(False)
        self._update_summary()

    def _get_current_video_duration(self, input_file):
        """Ermittelt die Dauer eines Videos mittels ffprobe."""
        info = getattr(self, "source_info", None)
        if info and info.get("duration"):
            return info["duration"]
        if not input_file or not os.path.exists(input_file):
            return 0.0
        try:
            import subprocess
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", input_file
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            print("Error getting duration via ffprobe:", e)
        return 0.0

    @staticmethod
    def _empty_source_info():
        return {
            "width": None, "height": None, "fps": None, "duration": 0.0,
            "v_codec": None, "a_codec": None, "a_rate": None,
            "a_channels": None, "a_bitrate": None,
        }

    def _start_probe(self):
        """Startet ffprobe asynchron; die frühere synchrone Variante konnte den
        Dialog beim Öffnen bis zu 5 Sekunden blockieren (z. B. Netzlaufwerke).

        Daemon-Thread + subprocess statt QProcess (ein laufender QProcess
        bricht in Qt 6 beim Zerstören des Dialogs die Anwendung ab). Der Thread
        schreibt nur ein Python-Attribut; ein QTimer des Dialogs holt das
        Ergebnis ab — der Timer stirbt mit dem Dialog, es gibt also keine
        Qt-Aufrufe auf einem zerstörten Objekt."""
        if not self.input_file or not os.path.exists(self.input_file):
            return
        self._probe_result = None
        input_file = self.input_file
        holder = self

        def work():
            import subprocess
            try:
                r = subprocess.run(
                    ["ffprobe", "-v", "error", "-print_format", "json",
                     "-show_format", "-show_streams", input_file],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
                )
                holder._probe_result = r.stdout if r.returncode == 0 else ""
            except (OSError, subprocess.SubprocessError):
                holder._probe_result = ""

        import threading
        threading.Thread(target=work, daemon=True, name="lme-dialog-ffprobe").start()

        from PyQt6.QtCore import QTimer
        self._probe_timer = QTimer(self)
        self._probe_timer.setInterval(100)
        self._probe_timer.timeout.connect(self._poll_probe_result)
        self._probe_timer.start()

    def _poll_probe_result(self):
        if self._probe_result is None:
            return
        self._probe_timer.stop()
        stdout = self._probe_result
        self._probe_result = None
        if not stdout:
            return
        self.source_info = self._parse_probe_json(stdout)
        self._apply_probe_result()

    def _parse_probe_json(self, stdout):
        """Parst ffprobe-JSON in das source_info-Dict (mit robusten Fallbacks)."""
        info = self._empty_source_info()
        try:
            import json
            data = json.loads(stdout)
            try:
                info["duration"] = float(data.get("format", {}).get("duration", 0.0))
            except (TypeError, ValueError):
                info["duration"] = 0.0
            for s in data.get("streams", []):
                stype = s.get("codec_type")
                if stype == "video" and info["width"] is None:
                    info["width"] = s.get("width")
                    info["height"] = s.get("height")
                    info["v_codec"] = s.get("codec_name")
                    rate = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/0"
                    try:
                        num, den = rate.split("/")
                        info["fps"] = round(float(num) / float(den), 3) if float(den) else None
                    except (ValueError, ZeroDivisionError):
                        info["fps"] = None
                elif stype == "audio" and info["a_codec"] is None:
                    info["a_codec"] = s.get("codec_name")
                    info["a_rate"] = s.get("sample_rate")
                    info["a_channels"] = s.get("channels")
                    if s.get("bit_rate"):
                        try:
                            info["a_bitrate"] = int(round(int(s["bit_rate"]) / 1000))
                        except (TypeError, ValueError):
                            pass
        except Exception as e:
            print("Error probing source info:", e)
        return info

    def _apply_probe_result(self):
        """Trägt asynchron eingetroffene Quell-Metadaten in die UI nach."""
        info = self.source_info or {}
        duration = info.get("duration", 0.0)
        self.lbl_total_time.setText(self._format_timecode(duration))
        if duration > 0:
            # Pfeiltasten auf dem Slider = 1 Sekunde, Bild-auf/-ab = 10 Sekunden
            one_second = max(1, int(round(self.SLIDER_MAX / duration)))
            self.time_slider.setSingleStep(one_second)
            self.time_slider.setPageStep(one_second * 10)
        self._on_slider_value_changed(self.time_slider.value())
        # Ohne gespeicherte Zielgröße die Quellauflösung vorbelegen
        if not self.settings.get("width") and info.get("width") and info.get("height"):
            self.spin_width.blockSignals(True)
            self.spin_height.blockSignals(True)
            self.spin_width.setValue(int(info["width"]))
            self.spin_height.setValue(int(info["height"]))
            self.spin_width.blockSignals(False)
            self.spin_height.blockSignals(False)
        self._update_trim_ui()
        self._update_summary()
        self._trigger_preview_update()

    def _sync_slider_to_seconds(self, seconds, duration):
        """Bewegt den Timeline-Slider signalfrei auf die angegebene Zeit."""
        value = int(round((seconds / duration) * self.SLIDER_MAX))
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(max(0, min(self.SLIDER_MAX, value)))
        self.time_slider.blockSignals(False)
        self.lbl_current_time.setText(self._format_timecode(seconds))

    def _seek_relative(self, delta_seconds):
        """Springt auf der Timeline um delta_seconds vor/zurück (Tastatur)."""
        duration = self.source_info.get("duration", 0.0) if self.source_info else 0.0
        if duration <= 0:
            return
        target = max(0.0, min(duration, self._slider_seconds() + delta_seconds))
        # setValue mit Signalen: aktualisiert Timecode-Label und debounced Vorschau
        self.time_slider.setValue(int(round((target / duration) * self.SLIDER_MAX)))

    def keyPressEvent(self, event):
        """Editor-Shortcuts: I/O = In-/Out-Punkt, ←/→ = ±1 s (Shift: ±10 s).
        Greift nur, wenn der Fokus nicht in einem Eingabefeld liegt — dort
        behalten die Tasten ihre normale Bedeutung."""
        focus = self.focusWidget()
        typing = isinstance(focus, (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox))
        if not typing:
            key = event.key()
            if key == Qt.Key.Key_I:
                self._on_set_trim_in()
                return
            if key == Qt.Key.Key_O:
                self._on_set_trim_out()
                return
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and not isinstance(focus, QSlider):
                step = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
                self._seek_relative(step if key == Qt.Key.Key_Right else -step)
                return
        super().keyPressEvent(event)

    # --- TRIM (In-/Out-Punkte) ---
    def _slider_seconds(self):
        duration = self.source_info.get("duration", 0.0) if self.source_info else 0.0
        return duration * (self.time_slider.value() / self.SLIDER_MAX)

    def _on_set_trim_in(self):
        seconds = round(self._slider_seconds(), 3)
        trim_end = presets.parse_seconds(self.settings.get("trim_end"))
        if trim_end is not None and seconds >= trim_end:
            self.settings.pop("trim_end", None)
        self.settings["trim_start"] = seconds
        self._update_trim_ui()
        self._update_summary()

    def _on_set_trim_out(self):
        seconds = round(self._slider_seconds(), 3)
        if seconds <= 0:
            return
        trim_start = presets.parse_seconds(self.settings.get("trim_start"))
        if trim_start is not None and seconds <= trim_start:
            self.settings.pop("trim_start", None)
        self.settings["trim_end"] = seconds
        self._update_trim_ui()
        self._update_summary()

    def _on_clear_trim(self):
        self.settings.pop("trim_start", None)
        self.settings.pop("trim_end", None)
        self._update_trim_ui()
        self._update_summary()

    def _on_trim_in_edited(self):
        text = self.edit_trim_in.text().strip()
        duration = self.source_info.get("duration", 0.0) if self.source_info else 0.0
        if not text:
            self.settings.pop("trim_start", None)
            self._update_trim_ui()
            self._update_summary()
            return
        
        seconds = self._parse_timecode(text)
        if seconds is None or seconds < 0:
            self._update_trim_ui()
            return

        # Nur klammern, wenn die Dauer bekannt ist — sonst würde eine gültige
        # Eingabe auf 0 zusammenfallen (z. B. solange ffprobe noch läuft).
        if duration > 0 and seconds > duration:
            seconds = duration

        trim_end = presets.parse_seconds(self.settings.get("trim_end"))
        if trim_end is not None and seconds >= trim_end:
            self.settings.pop("trim_end", None)
            
        self.settings["trim_start"] = round(seconds, 3)
        self._update_trim_ui()
        self._update_summary()
        
        if duration > 0:
            self._sync_slider_to_seconds(seconds, duration)
            self._trigger_preview_update(seek_seconds=seconds)

    def _on_trim_out_edited(self):
        text = self.edit_trim_out.text().strip()
        duration = self.source_info.get("duration", 0.0) if self.source_info else 0.0
        if not text:
            self.settings.pop("trim_end", None)
            self._update_trim_ui()
            self._update_summary()
            return
            
        seconds = self._parse_timecode(text)
        if seconds is None or seconds <= 0:
            self._update_trim_ui()
            return

        if duration > 0 and seconds > duration:
            seconds = duration

        trim_start = presets.parse_seconds(self.settings.get("trim_start"))
        if trim_start is not None and seconds <= trim_start:
            self.settings.pop("trim_start", None)
            
        self.settings["trim_end"] = round(seconds, 3)
        self._update_trim_ui()
        self._update_summary()
        
        if duration > 0:
            self._sync_slider_to_seconds(seconds, duration)
            self._trigger_preview_update(seek_seconds=seconds)

    def _update_trim_ui(self):
        trim_start = presets.parse_seconds(self.settings.get("trim_start"))
        trim_end = presets.parse_seconds(self.settings.get("trim_end"))
        
        if hasattr(self, "edit_trim_in"):
            self.edit_trim_in.blockSignals(True)
            self.edit_trim_in.setText(self._format_timecode(trim_start) if trim_start is not None else "")
            self.edit_trim_in.blockSignals(False)
            
        if hasattr(self, "edit_trim_out"):
            self.edit_trim_out.blockSignals(True)
            self.edit_trim_out.setText(self._format_timecode(trim_end) if trim_end is not None else "")
            self.edit_trim_out.blockSignals(False)
            
        has_trim = trim_start is not None or trim_end is not None
        self.btn_clear_trim.setEnabled(has_trim)
        duration = self.source_info.get("duration", 0.0) if self.source_info else 0.0

        # Export-Bereich auf der Timeline markieren
        if hasattr(self, "trim_range_bar"):
            if has_trim and duration > 0:
                start_frac = (trim_start or 0.0) / duration
                end_frac = (trim_end / duration) if trim_end is not None else 1.0
                self.trim_range_bar.set_trim(start_frac, end_frac, True)
            else:
                self.trim_range_bar.set_trim(0.0, 1.0, False)

        if not has_trim:
            self.lbl_trim_info.setText("Kein Schnitt — es wird die komplette Quelle exportiert.")
            return
        start = trim_start or 0.0
        end = trim_end if trim_end is not None else duration
        parts = [
            f"Schnitt: {self._format_timecode(start)} – "
            f"{self._format_timecode(end) if end else 'Ende'}"
        ]
        if end and end > start:
            parts.append(f"(Dauer {self._format_timecode(end - start)})")
        # Stream-Kopie schneidet nur an Keyframes — dem User sagen, warum der
        # Clip ggf. etwas früher beginnt als eingegeben.
        if start > 0 and str(self.settings.get("video_codec", "")).strip().lower() == "copy":
            parts.append("— verlustfrei: beginnt am Keyframe vor dem In-Punkt")
        self.lbl_trim_info.setText(" ".join(parts))

    def done(self, result):
        """Räumt Vorschau-/Probe-Prozesse und Temp-Dateien beim Schließen auf."""
        if self._probe_proc and self._probe_proc.state() != QProcess.ProcessState.NotRunning:
            self._probe_proc.kill()
            self._probe_proc.waitForFinished(500)
        self._probe_proc = None
        if self._preview_proc and self._preview_proc.state() != QProcess.ProcessState.NotRunning:
            self._preview_proc.kill()
            self._preview_proc.waitForFinished(500)
        self._preview_proc = None
        for path in self._preview_temp_files:
            try:
                os.remove(path)
            except OSError:
                pass
        self._preview_temp_files.clear()
        super().done(result)

    @staticmethod
    def _format_timecode(seconds):
        """Formatiert Sekunden als HH:MM:SS.ms (mit Millisekunden-Genauigkeit)."""
        if not seconds or seconds <= 0:
            return "00:00:00.000"
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        if ms >= 1000:
            s += 1
            ms -= 1000
            if s >= 60:
                s -= 60
                m += 1
                if m >= 60:
                    m -= 60
                    h += 1
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    @staticmethod
    def _parse_timecode(text):
        """Parst einen Timecode-String (HH:MM:SS.mmm, MM:SS.mmm, oder Sekunden) in Sekunden."""
        text = text.strip()
        if not text or "-" in text:
            return None
        try:
            if ":" in text:
                parts = text.split(":")
                if len(parts) == 3:
                    h = int(parts[0])
                    m = int(parts[1])
                    s = float(parts[2])
                    return h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    m = int(parts[0])
                    s = float(parts[1])
                    return m * 60 + s
                return None
            return float(text)
        except ValueError:
            return None

    def _on_intelligent_mode_clicked(self):
        """Öffnet den Intelligenten Bitraten-Rechner Dialog."""
        codec = self.combo_vcodec.currentText()
        duration = self._get_current_video_duration(self.input_file)
        
        from PyQt6.QtWidgets import QDialog
        from intelligent_dialog import IntelligentBitrateDialog
        dialog = IntelligentBitrateDialog(duration, codec, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            v_bitrate_mbps, a_bitrate_kbps = dialog.get_calculated_bitrates()
            
            # Werte in die GUI eintragen
            self.combo_encoding.setCurrentText("VBR, 1 Durchgang")
            self.spin_bitrate_val.setValue(v_bitrate_mbps)
            self.combo_audiobitrate.setCurrentText(a_bitrate_kbps)

            self._update_summary()
