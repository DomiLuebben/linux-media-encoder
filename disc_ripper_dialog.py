# -*- coding: utf-8 -*-
"""
CD/DVD/BD Ripper Dialog für den Linux Media Encoder (LME).
Ermöglicht das Einlesen, Auswählen von Titeln/Spuren, direktes Remuxen/Rippen,
1:1 ISO-Abbilderstellung und Übergabe in die LME-Warteschlange.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from PyQt6.QtCore import Qt, QSize, QProcess, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QLineEdit, QPushButton, QProgressBar, QTextEdit, QFileDialog,
    QMessageBox, QHeaderView, QGroupBox, QRadioButton, QTableWidget,
    QTableWidgetItem, QSplitter, QStyle, QApplication,
)

from i18n import (
    QAction, QCheckBox, QComboBox, QDialog, QFileDialog, QGroupBox, QLabel,
    QLineEdit, QMenu, QMessageBox, QProgressBar, QPushButton, QRadioButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QWidget, LocalizedString, tr,
)

import optical_media
import dependency_installer
from optical_media import (
    DiscType,
    OpticalDriveInfo,
    AudioTrackInfo,
    VideoTitleInfo,
    DiscInspectionResult,
    scan_optical_drives,
    detect_disc_type,
    inspect_source,
    eject_drive,
    build_dvd_rip_args,
    build_bluray_rip_args,
    check_dvd_encryption_support,
    check_bluray_encryption_support,
    get_optical_media_size,
)
from disc_rip_worker import AudioCdRipWorker, IsoDumpWorker
from ffmpeg_worker import FFmpegWorker


class DiscRipperDialog(QDialog):
    """
    Hauptdialog für das Einlesen und Rippen von optischen Medien (CD/DVD/BD/ISO).
    """
    jobs_queued = pyqtSignal(list)  # Signal an MainWindow mit Liste von Job-Dicts

    def __init__(self, initial_source: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(tr("CD / DVD / BD Ripper"))
        self.setMinimumSize(QSize(960, 680))
        self.setModal(True)

        self.current_source: Optional[str] = initial_source
        self.inspection_result: Optional[DiscInspectionResult] = None
        self.drives: List[OpticalDriveInfo] = []

        # Aktive Worker für Direkt-Rip
        self.active_worker: Optional[Any] = None
        self.pending_video_jobs: List[tuple[list[str], str, str]] = []
        self.current_video_job_idx: int = -1

        self._init_ui()
        self._update_environment_notice()
        self._refresh_drives()

        if initial_source:
            self._inspect_and_display_source(initial_source)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # --- 1. QUELLENAUSWAHL & LAUFWERKE ---
        source_group = QGroupBox(tr("Optische Quelle / Laufwerk"))
        source_layout = QGridLayout(source_group)
        source_layout.setSpacing(8)

        source_layout.addWidget(QLabel(tr("Laufwerk / Medium:")), 0, 0)
        self.combo_drives = QComboBox()
        self.combo_drives.currentIndexChanged.connect(self._on_drive_selection_changed)
        source_layout.addWidget(self.combo_drives, 0, 1)

        btn_refresh = QPushButton(tr("Neu laden"))
        btn_refresh.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        btn_refresh.clicked.connect(self._refresh_drives)
        source_layout.addWidget(btn_refresh, 0, 2)

        self.btn_eject = QPushButton(tr("Auswerfen"))
        self.btn_eject.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveCDIcon))
        self.btn_eject.clicked.connect(self._on_eject_clicked)
        source_layout.addWidget(self.btn_eject, 0, 3)

        btn_open_iso = QPushButton(tr("ISO-Datei öffnen..."))
        btn_open_iso.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        btn_open_iso.clicked.connect(self._on_open_iso_clicked)
        source_layout.addWidget(btn_open_iso, 1, 1)

        btn_open_folder = QPushButton(tr("DVD/BD-Ordner öffnen..."))
        btn_open_folder.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        btn_open_folder.clicked.connect(self._on_open_folder_clicked)
        source_layout.addWidget(btn_open_folder, 1, 2, 1, 2)

        main_layout.addWidget(source_group)

        # --- 2. DISC-INFORMATIONEN & STATUS ---
        self.info_banner = QWidget()
        info_layout = QHBoxLayout(self.info_banner)
        info_layout.setContentsMargins(4, 2, 4, 2)

        self.lbl_disc_badge = QLabel(tr("[Kein Medium]"))
        self.lbl_disc_badge.setStyleSheet(
            "background-color: #2b3a4a; color: #4da6ff; font-weight: bold; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        info_layout.addWidget(self.lbl_disc_badge)

        self.lbl_disc_info = QLabel(tr("Kein optisches Medium geladen."))
        self.lbl_disc_info.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(self.lbl_disc_info, 1)

        main_layout.addWidget(self.info_banner)

        # Dauerhafte Systemprüfung: sichtbar, sobald der Dialog aufgeht, also
        # auch ohne eingelegtes Medium. Der Tooltip führt jede Komponente
        # einzeln mit Zweck und Zustand auf.
        env_row = QHBoxLayout()
        env_row.setSpacing(8)

        self.lbl_env_notice = QLabel("")
        self.lbl_env_notice.setStyleSheet("color: #ffaa00; font-style: italic;")
        self.lbl_env_notice.setVisible(False)
        self.lbl_env_notice.setWordWrap(True)
        env_row.addWidget(self.lbl_env_notice, 1)

        self.btn_install_deps = QPushButton(tr("Fehlende Komponenten installieren..."))
        self.btn_install_deps.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.btn_install_deps.clicked.connect(self._on_install_dependencies_clicked)
        self.btn_install_deps.setVisible(False)
        env_row.addWidget(self.btn_install_deps, 0)

        main_layout.addLayout(env_row)

        self.lbl_warn_encryption = QLabel("")
        self.lbl_warn_encryption.setStyleSheet("color: #ffaa00; font-style: italic;")
        self.lbl_warn_encryption.setVisible(False)
        self.lbl_warn_encryption.setWordWrap(True)
        main_layout.addWidget(self.lbl_warn_encryption)

        # --- 3. TITEL- & TRACK-TABELLE ---
        table_group = QGroupBox(tr("Titel- & Spurauswahl"))
        table_layout = QVBoxLayout(table_group)
        table_layout.setSpacing(6)

        self.table_titles = QTableWidget()
        self.table_titles.setColumnCount(8)
        self.table_titles.setHorizontalHeaderLabels([
            tr("Rippen"), tr("Nr."), tr("Titel / Name"), tr("Dauer"),
            tr("Kapitel"), tr("Video-Format"), tr("Audiospur"), tr("Untertitel")
        ])
        h_header = self.table_titles.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        table_layout.addWidget(self.table_titles)

        # Schnell-Auswahl-Knöpfe
        sel_btn_layout = QHBoxLayout()
        self.btn_select_all = QPushButton(tr("Alle auswählen"))
        self.btn_select_all.clicked.connect(self._select_all_titles)
        sel_btn_layout.addWidget(self.btn_select_all)

        self.btn_select_none = QPushButton(tr("Keine"))
        self.btn_select_none.clicked.connect(self._select_no_titles)
        sel_btn_layout.addWidget(self.btn_select_none)

        self.btn_select_main = QPushButton(tr("Hauptfilm"))
        self.btn_select_main.clicked.connect(self._select_main_feature)
        sel_btn_layout.addWidget(self.btn_select_main)
        sel_btn_layout.addStretch(1)

        table_layout.addLayout(sel_btn_layout)
        main_layout.addWidget(table_group, 1)

        # --- 4. RIP-MODUS & ZIELEINSTELLUNGEN ---
        settings_group = QGroupBox(tr("Ausgabe & Rip-Einstellungen"))
        set_layout = QGridLayout(settings_group)
        set_layout.setSpacing(8)

        set_layout.addWidget(QLabel(tr("Rip-Modus:")), 0, 0)
        mode_layout = QHBoxLayout()
        self.radio_mode_queue = QRadioButton(tr("In Warteschlange einreihen (Queue)"))
        self.radio_mode_queue.setToolTip(tr("Fügt die Titel als Konvertierungs-Jobs in die LME-Hauptwarteschlange ein."))
        self.radio_mode_queue.setChecked(True)
        mode_layout.addWidget(self.radio_mode_queue)

        self.radio_mode_direct = QRadioButton(tr("Direkt rippen (Verlustfrei / Remux)"))
        self.radio_mode_direct.setToolTip(tr("Remuxt Video verlustfrei nach MKV bzw. extrahiert Audio-Tracks."))
        mode_layout.addWidget(self.radio_mode_direct)

        self.radio_mode_iso = QRadioButton(tr("1:1 ISO-Abbild erstellen"))
        self.radio_mode_iso.setToolTip(tr("Erstellt ein vollständiges ISO-Abbild des optischen Datenträgers."))
        mode_layout.addWidget(self.radio_mode_iso)
        set_layout.addLayout(mode_layout, 0, 1, 1, 2)

        # Audio-CD Codec Auswahl
        self.lbl_cd_codec = QLabel(tr("Audio-CD Format:"))
        set_layout.addWidget(self.lbl_cd_codec, 1, 0)
        self.combo_cd_codec = QComboBox()
        self.combo_cd_codec.addItems(["FLAC (Verlustfrei)", "WAV (Unkomprimiert)", "MP3 (320 kbps)", "AAC (256 kbps)", "Opus (160 kbps)", "ALAC"])
        set_layout.addWidget(self.combo_cd_codec, 1, 1)

        # Zielordner
        set_layout.addWidget(QLabel(tr("Zielordner:")), 2, 0)
        self.edit_output_dir = QLineEdit()
        default_dir = os.path.expanduser("~/Videos")
        self.edit_output_dir.setText(default_dir)
        set_layout.addWidget(self.edit_output_dir, 2, 1)

        btn_browse_dir = QPushButton(tr("Durchsuchen..."))
        btn_browse_dir.clicked.connect(self._on_browse_output_dir)
        set_layout.addWidget(btn_browse_dir, 2, 2)

        main_layout.addWidget(settings_group)

        # --- 5. FORTSCHRITT & LOG (FÜR DIREKT-RIP) ---
        self.progress_group = QWidget()
        prog_layout = QVBoxLayout(self.progress_group)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(4)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        prog_layout.addWidget(self.prog_bar)

        self.lbl_status = QLabel(tr("Bereit"))
        prog_layout.addWidget(self.lbl_status)

        self.txt_log = QTextEdit()
        self.txt_log.setMaximumHeight(90)
        self.txt_log.setReadOnly(True)
        self.txt_log.setVisible(False)
        prog_layout.addWidget(self.txt_log)

        main_layout.addWidget(self.progress_group)

        # --- 6. BUTTON-LEISTE ---
        btn_box = QHBoxLayout()
        self.btn_toggle_log = QPushButton(tr("Log anzeigen"))
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.toggled.connect(lambda checked: self.txt_log.setVisible(checked))
        btn_box.addWidget(self.btn_toggle_log)

        btn_box.addStretch(1)

        self.btn_stop = QPushButton(tr("Abbrechen"))
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_stop.setVisible(False)
        btn_box.addWidget(self.btn_stop)

        self.btn_action = QPushButton(tr("In Warteschlange einreihen"))
        self.btn_action.setObjectName("btn_primary")
        self.btn_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOkButton))
        self.btn_action.clicked.connect(self._on_action_clicked)
        btn_box.addWidget(self.btn_action)

        btn_close = QPushButton(tr("Schließen"))
        btn_close.clicked.connect(self.close)
        btn_box.addWidget(btn_close)

        main_layout.addLayout(btn_box)

        # Radio button changes update action button text
        self.radio_mode_queue.toggled.connect(self._update_action_button_text)
        self.radio_mode_direct.toggled.connect(self._update_action_button_text)
        self.radio_mode_iso.toggled.connect(self._update_action_button_text)

    def _refresh_drives(self):
        """Aktualisiert die Liste aller physischen optischen Laufwerke."""
        self.combo_drives.blockSignals(True)
        self.combo_drives.clear()

        self.drives = optical_media.scan_optical_drives()
        if not self.drives:
            self.combo_drives.addItem(tr("Kein physisches Laufwerk erkannt"), None)
            self.btn_eject.setEnabled(False)
            self.btn_action.setEnabled(False)
        else:
            self.btn_eject.setEnabled(True)
            for d in self.drives:
                icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DriveCDIcon)
                label_txt = f"{d.device_path} ({d.vendor} {d.model})".strip()
                if d.disc_present:
                    label_txt += f" [{d.media_type or 'Medium'}]"
                    if d.volume_label:
                        label_txt += f" · {d.volume_label}"
                else:
                    label_txt += tr(" · [Kein Medium]")
                self.combo_drives.addItem(icon, label_txt, d.device_path)

        self.combo_drives.blockSignals(False)

        # Falls ein Laufwerk mit Medium existiert, direkt untersuchen
        if self.drives:
            for d in self.drives:
                if d.disc_present:
                    self._inspect_and_display_source(d.device_path)
                    return

    def _on_drive_selection_changed(self, index: int):
        dev_path = self.combo_drives.currentData()
        if dev_path:
            self._inspect_and_display_source(dev_path)

    def _on_eject_clicked(self):
        dev_path = self.combo_drives.currentData()
        if dev_path and dev_path.startswith("/dev/"):
            ok, msg = optical_media.eject_drive(dev_path)
            if ok:
                self._refresh_drives()
                self.lbl_disc_info.setText(tr("Laufwerk ausgeworfen."))
            else:
                QMessageBox.warning(self, tr("Auswerfen fehlgeschlagen"), msg)

    def _on_open_iso_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("ISO-Image öffnen"),
            os.path.expanduser("~"),
            tr("Disc-Images (*.iso *.img *.nrg);;Alle Dateien (*.*)")
        )
        if path:
            self._inspect_and_display_source(path)

    def _on_open_folder_clicked(self):
        path = QFileDialog.getExistingDirectory(
            self,
            tr("DVD/BD-Ordner öffnen (VIDEO_TS oder BDMV)"),
            os.path.expanduser("~")
        )
        if path:
            self._inspect_and_display_source(path)

    def _on_browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self,
            tr("Zielordner wählen"),
            self.edit_output_dir.text() or os.path.expanduser("~")
        )
        if path:
            self.edit_output_dir.setText(path)

    def _inspect_and_display_source(self, source_path: str):
        """Untersucht die angegebene Quelle und befüllt die Benutzeroberfläche."""
        self.current_source = source_path
        self.lbl_status.setText(tr("Lese Medium ein..."))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.inspection_result = optical_media.inspect_source(source_path)
        finally:
            QApplication.restoreOverrideCursor()

        res = self.inspection_result
        if not res or res.error:
            err_msg = res.error if res else tr("Medium konnte nicht gelesen werden.")
            self.lbl_disc_badge.setText(tr("[Fehler]"))
            self.lbl_disc_info.setText(err_msg)
            self.table_titles.setRowCount(0)
            self.btn_action.setEnabled(False)
            return

        # Header Badge & Info
        if res.disc_type == DiscType.AUDIO_CD:
            self.lbl_disc_badge.setText(tr("[Audio-CD]"))
            self.lbl_disc_info.setText(tr(
                "Audio-CD: {tracks} Tracks · Gesamtdauer: {duration}",
                tracks=len(res.audio_tracks),
                duration=self._format_duration(res.total_duration_sec)
            ))
            self.edit_output_dir.setText(os.path.expanduser("~/Musik"))
            self.lbl_cd_codec.setVisible(True)
            self.combo_cd_codec.setVisible(True)
            self.radio_mode_iso.setEnabled(False)
            self.radio_mode_iso.setToolTip(tr("1:1 ISO-Abbild ist für reine Audio-CDs nicht möglich."))
            if self.radio_mode_iso.isChecked():
                self.radio_mode_queue.setChecked(True)
            self.lbl_warn_encryption.setVisible(False)
            self._populate_audio_cd_table(res.audio_tracks)

        elif res.disc_type == DiscType.DVD_VIDEO:
            self.lbl_disc_badge.setText(tr("[DVD-Video]"))
            title_text = res.disc_label or os.path.basename(source_path)
            self.lbl_disc_info.setText(tr(
                "DVD-Video: {label} · {count} Titel · Gesamtdauer: {duration}",
                label=title_text,
                count=len(res.video_titles),
                duration=self._format_duration(res.total_duration_sec)
            ))
            self.edit_output_dir.setText(os.path.expanduser("~/Videos"))
            self.lbl_cd_codec.setVisible(False)
            self.combo_cd_codec.setVisible(False)
            self.radio_mode_iso.setEnabled(source_path.startswith("/dev/"))

            # CSS Verschlüsselungsprüfung
            has_dvdcss, css_msg = check_dvd_encryption_support()
            if not has_dvdcss:
                self.lbl_warn_encryption.setText(tr("Hinweis: {msg}", msg=css_msg))
                self.lbl_warn_encryption.setVisible(True)
            else:
                self.lbl_warn_encryption.setVisible(False)

            self._populate_video_titles_table(res.video_titles)

        elif res.disc_type == DiscType.BLURAY:
            self.lbl_disc_badge.setText(tr("[Blu-ray Disc]"))
            label_text = res.disc_label or os.path.basename(source_path)
            self.lbl_disc_info.setText(tr(
                "Blu-ray: {label} · {count} Playlists · Gesamtdauer: {duration}",
                label=label_text,
                count=len(res.video_titles),
                duration=self._format_duration(res.total_duration_sec)
            ))
            self.edit_output_dir.setText(os.path.expanduser("~/Videos"))
            self.lbl_cd_codec.setVisible(False)
            self.combo_cd_codec.setVisible(False)
            self.radio_mode_iso.setEnabled(source_path.startswith("/dev/"))

            # AACS Verschlüsselungsprüfung
            has_aacs, aacs_msg = check_bluray_encryption_support()
            if not has_aacs:
                self.lbl_warn_encryption.setText(tr("Hinweis: {msg}", msg=aacs_msg))
                self.lbl_warn_encryption.setVisible(True)
            else:
                self.lbl_warn_encryption.setVisible(False)

            self._populate_video_titles_table(res.video_titles)

        else:
            self.lbl_disc_badge.setText(tr("[Daten-Disc]"))
            self.lbl_disc_info.setText(tr("Daten-Disc oder unbekannte Struktur."))
            self.table_titles.setRowCount(0)

        # Zwingend benötigte Komponenten für genau diese Quellart: fehlt eine,
        # wird die Aktion gesperrt statt erst beim Rippen zu scheitern.
        blocking = optical_media.missing_optical_components(res.disc_type, blocking_only=True)
        if blocking:
            self.lbl_warn_encryption.setText(tr(
                "Für diese Quelle fehlt eine zwingend benötigte Komponente: {names}",
                names=", ".join(component.name for component in blocking),
            ))
            self.lbl_warn_encryption.setVisible(True)
            self.btn_action.setEnabled(False)
        else:
            self.btn_action.setEnabled(self.table_titles.rowCount() > 0 or self.radio_mode_iso.isChecked())
        self.lbl_status.setText(tr("Bereit"))

    def _populate_audio_cd_table(self, tracks: List[AudioTrackInfo]):
        """Befüllt die Tabelle für Audio-CDs."""
        self.table_titles.setRowCount(0)
        self.row_checkboxes = []
        for t in tracks:
            row = self.table_titles.rowCount()
            self.table_titles.insertRow(row)

            # Checkbox
            chk = QCheckBox()
            chk.setChecked(True)
            self.row_checkboxes.append(chk)
            chk_wrap = QWidget()
            l = QHBoxLayout(chk_wrap)
            l.setContentsMargins(6, 0, 6, 0)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.addWidget(chk)
            self.table_titles.setCellWidget(row, 0, chk_wrap)

            # Nr.
            num_item = QTableWidgetItem(f"{t.track_num:02d}")
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 1, num_item)

            # Titel
            title_item = QTableWidgetItem(t.title or f"Track {t.track_num:02d}")
            self.table_titles.setItem(row, 2, title_item)

            # Dauer
            dur_item = QTableWidgetItem(t.formatted_duration())
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 3, dur_item)

            # Kapitel
            dash1 = QTableWidgetItem("-")
            dash1.setFlags(dash1.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 4, dash1)

            # Format
            fmt_item = QTableWidgetItem(tr("CDDA (PCM 44.1 kHz / 16-Bit)"))
            fmt_item.setFlags(fmt_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 5, fmt_item)

            # Audiospur
            audio_item = QTableWidgetItem(tr("Stereo"))
            audio_item.setFlags(audio_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 6, audio_item)

            # Untertitel
            dash2 = QTableWidgetItem("-")
            dash2.setFlags(dash2.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 7, dash2)

    def _populate_video_titles_table(self, titles: List[VideoTitleInfo]):
        """Befüllt die Tabelle für DVD- und Blu-ray-Titel."""
        self.table_titles.setRowCount(0)
        self.row_checkboxes = []
        for t in titles:
            row = self.table_titles.rowCount()
            self.table_titles.insertRow(row)

            # Checkbox: Standardmäßig Hauptfilm ausgewählt, sonst nur wenn einziger Titel
            chk = QCheckBox()
            chk.setChecked(t.is_main_feature or len(titles) == 1)
            self.row_checkboxes.append(chk)
            chk_wrap = QWidget()
            l = QHBoxLayout(chk_wrap)
            l.setContentsMargins(6, 0, 6, 0)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.addWidget(chk)
            self.table_titles.setCellWidget(row, 0, chk_wrap)

            # Nr.
            num_item = QTableWidgetItem(f"{t.title_num:02d}")
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 1, num_item)

            # Name (editierbar)
            display_name = t.name
            if t.is_main_feature:
                display_name += tr(" [Hauptfilm]")
            name_item = QTableWidgetItem(display_name)
            self.table_titles.setItem(row, 2, name_item)

            # Dauer
            dur_item = QTableWidgetItem(t.formatted_duration())
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 3, dur_item)

            # Kapitel
            chap_str = str(t.chapter_count) if t.chapter_count > 0 else "1"
            chap_item = QTableWidgetItem(chap_str)
            chap_item.setFlags(chap_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 4, chap_item)

            # Video Format
            v_text = f"{t.video_codec.upper()} {t.width}x{t.height} ({t.aspect_ratio})"
            v_item = QTableWidgetItem(v_text)
            v_item.setFlags(v_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table_titles.setItem(row, 5, v_item)

            # Audiospuren Dropdown
            combo_audio = QComboBox()
            if t.audio_streams:
                for a in t.audio_streams:
                    combo_audio.addItem(a.display_text(), a.stream_idx)
                combo_audio.addItem(tr("Alle Audiospuren"), -1)
            else:
                combo_audio.addItem(tr("Standard-Spur"), None)
            self.table_titles.setCellWidget(row, 6, combo_audio)

            # Untertitel Dropdown
            combo_sub = QComboBox()
            combo_sub.addItem(tr("Keine Untertitel"), None)
            if t.subtitle_streams:
                for s in t.subtitle_streams:
                    combo_sub.addItem(s.display_text(), s.stream_idx)
                combo_sub.addItem(tr("Alle Untertitel"), -1)
            self.table_titles.setCellWidget(row, 7, combo_sub)

    def _select_all_titles(self):
        for chk in getattr(self, "row_checkboxes", []):
            chk.setChecked(True)

    def _select_no_titles(self):
        for chk in getattr(self, "row_checkboxes", []):
            chk.setChecked(False)

    def _select_main_feature(self):
        if not self.inspection_result or not self.inspection_result.video_titles:
            return
        main_idx = self.inspection_result.main_title_idx
        for idx, chk in enumerate(getattr(self, "row_checkboxes", [])):
            chk.setChecked(idx == main_idx)

    def _update_action_button_text(self):
        if self.radio_mode_queue.isChecked():
            self.btn_action.setText(tr("In Warteschlange einreihen"))
            self.btn_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOkButton))
        elif self.radio_mode_direct.isChecked():
            self.btn_action.setText(tr("Jetzt rippen"))
            self.btn_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        elif self.radio_mode_iso.isChecked():
            self.btn_action.setText(tr("1:1 ISO erstellen"))
            self.btn_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon))

    def _format_duration(self, seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def _get_selected_rows(self) -> List[int]:
        rows = []
        for idx, chk in enumerate(getattr(self, "row_checkboxes", [])):
            if chk.isChecked():
                rows.append(idx)
        return rows

    # --- AKTIONEN & VERARBEITUNG ---

    def _on_action_clicked(self):
        if not self.current_source:
            QMessageBox.warning(self, tr("Keine Quelle"), tr("Bitte wähle zuerst eine optische Quelle oder Datei aus."))
            return

        out_dir = self.edit_output_dir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, tr("Ungültiger Zielordner"), tr("Bitte gib einen gültigen Zielordner an."))
            return
        os.makedirs(out_dir, exist_ok=True)

        if self.radio_mode_iso.isChecked():
            self._start_iso_dump(out_dir)
            return

        selected_rows = self._get_selected_rows()
        if not selected_rows:
            QMessageBox.warning(self, tr("Keine Auswahl"), tr("Bitte wähle mindestens einen Titel oder Track aus."))
            return

        if self.radio_mode_queue.isChecked():
            self._queue_selected_jobs(selected_rows, out_dir)
        elif self.radio_mode_direct.isChecked():
            self._start_direct_rip(selected_rows, out_dir)

    def _queue_selected_jobs(self, selected_rows: List[int], out_dir: str):
        """Übergibt ausgewählte Video-Titel oder CD-Tracks an die Hauptwarteschlange."""
        res = self.inspection_result
        if not res:
            return

        jobs_to_queue = []
        disc_label = res.disc_label or "Disc"

        if res.disc_type == DiscType.AUDIO_CD:
            codec_choice = self.combo_cd_codec.currentText().lower()
            codec_key = "flac" if "flac" in codec_choice else ("mp3" if "mp3" in codec_choice else "wav")
            for row in selected_rows:
                track = res.audio_tracks[row]
                custom_name = self.table_titles.item(row, 2).text().strip() if self.table_titles.item(row, 2) else track.title
                safe_name = "".join(c for c in custom_name if c.isalnum() or c in " -_.").strip()
                out_name = f"{track.track_num:02d} - {safe_name}.{codec_key}"
                out_path = os.path.join(out_dir, out_name)

                job = {
                    "input_file": self.current_source,
                    "output_dir": out_dir,
                    "output_file": out_path,
                    "settings": {
                        "container": codec_key,
                        "audio_codec": codec_key,
                        "disc_type": "audio_cd",
                        "track_num": track.track_num,
                        "track_title": custom_name,
                        "track_artist": track.artist,
                        "track_album": track.album or disc_label,
                    },
                    "status": "Bereit",
                    "progress": 0.0,
                    "speed": "0.0x",
                    "time_remaining": "Bereit",
                }
                jobs_to_queue.append(job)

        elif res.disc_type in (DiscType.DVD_VIDEO, DiscType.BLURAY):
            for row in selected_rows:
                title = res.video_titles[row]
                custom_name = self.table_titles.item(row, 2).text().strip() if self.table_titles.item(row, 2) else title.name
                safe_name = "".join(c for c in custom_name if c.isalnum() or c in " -_.").strip()

                # Audio & Subtitle Auswahl
                audio_combo = self.table_titles.cellWidget(row, 6)
                audio_idx = audio_combo.currentData() if isinstance(audio_combo, QComboBox) else None

                sub_combo = self.table_titles.cellWidget(row, 7)
                sub_idx = sub_combo.currentData() if isinstance(sub_combo, QComboBox) else None

                # Falls Untertitel gewählt -> MKV erzwingen
                out_ext = "mkv" if sub_idx is not None else "mp4"
                out_name = f"{disc_label} - {safe_name}.{out_ext}"
                out_path = os.path.join(out_dir, out_name)

                input_args = []
                if res.disc_type == DiscType.DVD_VIDEO:
                    input_args = ["-f", "dvdvideo", "-title", str(title.title_num), "-chapter_start", "1", "-chapter_end", "0"]
                elif res.disc_type == DiscType.BLURAY:
                    input_args = ["-playlist", str(title.title_num)]

                job = {
                    "input_file": self.current_source,
                    "output_dir": out_dir,
                    "output_file": out_path,
                    "settings": {
                        "container": out_ext,
                        "video_codec": "libx264",
                        "video_bitrate": "8M",
                        "crf": "",
                        "audio_codec": "aac",
                        "audio_bitrate": "192k",
                        "input_args": input_args,
                        "disc_type": res.disc_type.value,
                        "title_num": title.title_num,
                        "audio_stream_idx": audio_idx,
                        "subtitle_stream_idx": sub_idx,
                        "source_width": title.width,
                        "source_height": title.height,
                        "source_duration": title.duration_sec,
                    },
                    "status": "Bereit",
                    "progress": 0.0,
                    "speed": "0.0x",
                    "time_remaining": "Bereit",
                }
                jobs_to_queue.append(job)

        if jobs_to_queue:
            self.jobs_queued.emit(jobs_to_queue)
            QMessageBox.information(
                self,
                tr("Warteschlange aktualisiert"),
                tr("{count} Job(s) erfolgreich zur Warteschlange hinzugefügt.", count=len(jobs_to_queue))
            )
            self.accept()

    def _start_direct_rip(self, selected_rows: List[int], out_dir: str):
        """Startet den direkten Ripping-Vorgang im Dialog."""
        res = self.inspection_result
        if not res:
            return

        self._set_ui_ripping_state(True)
        self.txt_log.clear()

        if res.disc_type == DiscType.AUDIO_CD:
            selected_tracks = [res.audio_tracks[r] for r in selected_rows]
            codec_choice = self.combo_cd_codec.currentText().lower()
            codec_key = "flac" if "flac" in codec_choice else (
                "mp3" if "mp3" in codec_choice else (
                    "opus" if "opus" in codec_choice else (
                        "aac" if "aac" in codec_choice else "wav"
                    )
                )
            )
            self.active_worker = AudioCdRipWorker(
                device_path=self.current_source or "/dev/sr0",
                tracks=selected_tracks,
                output_dir=out_dir,
                codec=codec_key,
                parent=self,
            )
            self.active_worker.progress_updated.connect(self._on_worker_progress)
            self.active_worker.log_received.connect(self._on_worker_log)
            self.active_worker.status_changed.connect(self._on_worker_status)
            self.active_worker.finished.connect(self._on_direct_rip_finished)
            self.active_worker.start()

        elif res.disc_type in (DiscType.DVD_VIDEO, DiscType.BLURAY):
            disc_label = res.disc_label or "Disc"
            self.pending_video_jobs = []
            for row in selected_rows:
                title = res.video_titles[row]
                custom_name = self.table_titles.item(row, 2).text().strip() if self.table_titles.item(row, 2) else title.name
                safe_name = "".join(c for c in custom_name if c.isalnum() or c in " -_.").strip()

                audio_combo = self.table_titles.cellWidget(row, 6)
                audio_idx = audio_combo.currentData() if isinstance(audio_combo, QComboBox) else None
                sub_combo = self.table_titles.cellWidget(row, 7)
                sub_idx = sub_combo.currentData() if isinstance(sub_combo, QComboBox) else None

                out_path = os.path.join(out_dir, f"{disc_label} - {safe_name}.mkv")

                if res.disc_type == DiscType.DVD_VIDEO:
                    args, final_out = build_dvd_rip_args(
                        source_path=self.current_source or "",
                        title_num=title.title_num,
                        audio_stream_idx=audio_idx,
                        subtitle_stream_idx=sub_idx,
                        output_file=out_path,
                        remux_mkv=True,
                    )
                else:
                    args, final_out = build_bluray_rip_args(
                        source_path=self.current_source or "",
                        playlist_num=title.title_num,
                        audio_stream_idx=audio_idx,
                        subtitle_stream_idx=sub_idx,
                        output_file=out_path,
                        remux_mkv=True,
                    )
                self.pending_video_jobs.append((args, final_out, safe_name))

            self.current_video_job_idx = 0
            self._run_next_video_job()

    def _run_next_video_job(self):
        if self.current_video_job_idx >= len(self.pending_video_jobs):
            self._on_direct_rip_finished(True, tr("Alle ausgewählten Titel erfolgreich verlustfrei gerippt."))
            return

        args, out_file, title_name = self.pending_video_jobs[self.current_video_job_idx]
        total_jobs = len(self.pending_video_jobs)
        self.lbl_status.setText(tr("Rippe {name} ({cur}/{total})...", name=title_name, cur=self.current_video_job_idx + 1, total=total_jobs))

        self.active_worker = FFmpegWorker(
            input_file=self.current_source or "",
            output_file=out_file,
            ffmpeg_args=args,
        )
        self.active_worker.progress_updated.connect(self._on_worker_progress)
        self.active_worker.log_received.connect(self._on_worker_log)
        self.active_worker.status_changed.connect(self._on_worker_status)
        self.active_worker.finished.connect(self._on_video_job_finished)
        self.active_worker.start()

    def _on_video_job_finished(self, success: bool, msg: str):
        if not success:
            self._on_direct_rip_finished(False, msg)
            return
        self.current_video_job_idx += 1
        self._run_next_video_job()

    def _start_iso_dump(self, out_dir: str):
        """Startet den 1:1 ISO-Abbild-Dump via dd."""
        if not self.current_source or not self.current_source.startswith("/dev/"):
            QMessageBox.warning(self, tr("Ungültiges Laufwerk"), tr("Ein 1:1 ISO-Abbild kann nur von einem physischen optischen Laufwerk erstellt werden."))
            return

        label = (self.inspection_result.disc_label if self.inspection_result else "") or "disc_backup"
        safe_label = "".join(c for c in label if c.isalnum() or c in " -_.").strip()
        out_iso = os.path.join(out_dir, f"{safe_label}.iso")

        self._set_ui_ripping_state(True)
        self.txt_log.clear()

        # Ohne Gesamtgröße liest dd bis EOF (Lesefehler am Discende) und der
        # Fortschrittsbalken hätte keine Bezugsgröße.
        total_size = get_optical_media_size(self.current_source)

        self.active_worker = IsoDumpWorker(
            device_path=self.current_source,
            output_iso_path=out_iso,
            total_size_bytes=total_size,
            parent=self,
        )
        self.active_worker.progress_updated.connect(self._on_worker_progress)
        self.active_worker.log_received.connect(self._on_worker_log)
        self.active_worker.status_changed.connect(self._on_worker_status)
        self.active_worker.finished.connect(self._on_direct_rip_finished)
        self.active_worker.start()

    def _update_environment_notice(self):
        """Meldet dauerhaft, welche externen Komponenten auf dem System fehlen.

        Läuft beim Öffnen des Dialogs — also auch ohne eingelegtes Medium, denn
        genau dann will man wissen, dass z. B. cdparanoia fehlt.
        """
        components = optical_media.check_optical_environment()

        tooltip_lines = [tr("Systemprüfung optischer Medien")]
        for component in components:
            mark = "✓" if component.available else "✗"
            tooltip_lines.append(f"{mark}  {component.name} — {tr(component.purpose)}")
            # 'detail' enthält Pfade und Laufzeitangaben und wird bewusst nicht
            # durch tr() geschickt.
            if not component.available and component.detail:
                tooltip_lines.append(f"      {component.detail}")
        # Der Tooltip ist aus bereits übersetzten Teilen zusammengesetzt; als
        # LocalizedString markiert, damit i18n ihn nicht ein zweites Mal
        # nachschlägt und als fehlenden Schlüssel meldet.
        tooltip = "\n".join(tooltip_lines)
        self.lbl_env_notice.setToolTip(LocalizedString(tooltip, tooltip))

        missing = [component for component in components if not component.available]
        if not missing:
            self.lbl_env_notice.setVisible(False)
            self.btn_install_deps.setVisible(False)
            return

        # Der Knopf erscheint nur, wenn wirklich etwas automatisch zu holen ist.
        plan = dependency_installer.plan_installation([c.key for c in missing])
        self._install_plan = plan
        # Auch dann anbieten, wenn es nur etwas zu erklaeren gibt (Fedora ohne
        # RPM Fusion) — sonst bekaeme der Anwender den Hinweis nie zu sehen.
        actionable = plan.has_work or plan.needs_extra_repo
        self.btn_install_deps.setVisible(actionable)
        self.btn_install_deps.setEnabled(
            actionable
            and (dependency_installer.graphical_sudo_available() or not plan.has_work)
        )

        names = ", ".join(component.name for component in missing)
        if any(component.is_blocking for component in missing):
            text = tr(
                "Es fehlen Komponenten, ohne die einzelne Medienarten gar nicht gelesen "
                "werden können: {names}. Einzelheiten im Tooltip.",
                names=names,
            )
        else:
            text = tr(
                "Optionale Komponenten fehlen: {names}. Einzelheiten im Tooltip.",
                names=names,
            )
        self.lbl_env_notice.setText(text)
        self.lbl_env_notice.setVisible(True)

    def _on_install_dependencies_clicked(self):
        """Installiert die fehlenden Komponenten mit grafischer Kennwortabfrage."""
        plan = getattr(self, "_install_plan", None)
        if plan is None:
            return

        # Fedora ohne RPM Fusion: eigener Hinweis, bevor irgendetwas läuft.
        # LME schaltet keine Fremdquellen frei — das bleibt eine bewusste
        # Entscheidung des Anwenders.
        if plan.needs_extra_repo == "rpmfusion":
            QMessageBox.information(
                self,
                tr("RPM Fusion wird benötigt"),
                tr(
                    "Zum Lesen kopiergeschützter DVDs wird libdvdcss benötigt. Unter Fedora "
                    "und verwandten Systemen liegt dieses Paket nicht in den Standardquellen, "
                    "sondern im Repository RPM Fusion (free), das auf diesem System nicht "
                    "eingerichtet ist.\n\n"
                    "Bitte RPM Fusion (free) einrichten und aktivieren, danach diesen Dialog "
                    "erneut öffnen. Die Anleitung steht auf rpmfusion.org.\n\n"
                    "Alle übrigen Komponenten lassen sich unabhängig davon installieren."
                ),
            )
        elif plan.needs_extra_repo == "packman":
            QMessageBox.information(
                self,
                tr("Packman wird benötigt"),
                tr(
                    "Zum Lesen kopiergeschützter DVDs wird libdvdcss benötigt. Unter openSUSE "
                    "liegt dieses Paket nicht in den Standardquellen, sondern im Repository "
                    "Packman, das auf diesem System nicht eingebunden ist.\n\n"
                    "Bitte Packman einbinden und aktivieren, danach diesen Dialog erneut "
                    "öffnen. Die Anleitung steht auf packman.links2linux.de.\n\n"
                    "Alle übrigen Komponenten lassen sich unabhängig davon installieren."
                ),
            )

        if not plan.has_work:
            return

        if not dependency_installer.graphical_sudo_available():
            QMessageBox.warning(
                self,
                tr("Grafische Rechteabfrage nicht verfügbar"),
                tr(
                    "Für die Installation wird pkexec (polkit) benötigt, es ist auf diesem "
                    "System nicht vorhanden. Bitte den folgenden Befehl im Terminal ausführen:"
                    "\n\n{command}",
                    command=dependency_installer.command_for_display(plan.command[1:]),
                ),
            )
            return

        details = tr(
            "Erkanntes System: {distro}\n\nFolgende Pakete werden installiert:\n{packages}"
            "\n\nAusgeführter Befehl:\n{command}\n\nDie Rechteabfrage erscheint gleich in "
            "einem eigenen Fenster.",
            distro=plan.distro_name or "-",
            packages="  " + "\n  ".join(
                f"{name} ({plan.repositories[name]})" if name in plan.repositories else name
                for name in plan.packages
            ),
            command=dependency_installer.command_for_display(plan.command),
        )
        if plan.info_notes:
            details += "\n\n" + tr("Bitte beachten:") + "\n- " + "\n- ".join(
                tr(note) for note in plan.info_notes
            )

        notes = [tr(note) for note in plan.manual_notes]
        if plan.unresolved:
            notes.append(tr(
                "Für diese Komponenten ist auf diesem System kein passendes Paket "
                "auffindbar: {names}",
                names=", ".join(plan.unresolved),
            ))
            if plan.family == dependency_installer.DistroFamily.ARCH:
                aur_names = " ".join(
                    dependency_installer.COMPONENT_PACKAGES[plan.family].get(key, (key,))[0]
                    for key in plan.unresolved
                )
                if plan.aur_helper:
                    notes.append(tr(
                        "Von Hand ginge das mit dem vorhandenen AUR-Helfer: {helper} -S {names}",
                        helper=plan.aur_helper,
                        names=aur_names,
                    ))
                else:
                    notes.append(tr(
                        "Auf diesem System ist kein AUR-Helfer installiert (etwa paru oder yay)."
                    ))
        if notes:
            details += "\n\n" + tr("Nicht automatisch erledigt:") + "\n- " + "\n- ".join(notes)
        if plan.needs_reboot:
            details += "\n\n" + tr(
                "Dieses System ist unveränderlich (rpm-ostree). Sollte die Änderung nicht "
                "sofort greifen, ist ein Neustart nötig."
            )

        answer = QMessageBox.question(
            self,
            tr("Fehlende Komponenten installieren"),
            details,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.btn_install_deps.setEnabled(False)
        self.txt_log.append(tr("Starte Installation: {command}",
                                command=dependency_installer.command_for_display(plan.command)))
        self.lbl_status.setText(tr("Installiere fehlende Komponenten..."))

        self._install_process = QProcess(self)
        self._install_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._install_process.readyReadStandardOutput.connect(self._on_install_output)
        self._install_process.finished.connect(self._on_install_finished)
        self._install_process.start(plan.command[0], plan.command[1:])

    def _on_install_output(self):
        data = self._install_process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.strip():
                self.txt_log.append(line.rstrip())

    def _on_install_finished(self, exit_code: int, exit_status):
        self._install_process = None
        # Zustand neu erheben, statt vom Erfolg auszugehen: das ist die einzige
        # Aussage, die wirklich zählt.
        self._update_environment_notice()
        still_missing = optical_media.missing_optical_components()

        if exit_code == 0 and not still_missing:
            self.lbl_status.setText(tr("Bereit"))
            QMessageBox.information(
                self,
                tr("Installation abgeschlossen"),
                tr("Alle Komponenten für optische Medien sind jetzt vorhanden."),
            )
        elif exit_code == 0:
            self.lbl_status.setText(tr("Bereit"))
            QMessageBox.information(
                self,
                tr("Installation abgeschlossen"),
                tr(
                    "Die Installation lief durch. Es fehlen weiterhin: {names}\n\n"
                    "Einzelheiten stehen im Tooltip des Hinweises.",
                    names=", ".join(component.name for component in still_missing),
                ),
            )
        else:
            self.lbl_status.setText(tr("Bereit"))
            QMessageBox.warning(
                self,
                tr("Installation fehlgeschlagen"),
                tr(
                    "Die Installation wurde abgebrochen oder ist fehlgeschlagen "
                    "(Rückgabewert {code}). Einzelheiten stehen im Protokoll.",
                    code=exit_code,
                ),
            )
        self.btn_install_deps.setEnabled(
            bool(getattr(self, "_install_plan", None) and self._install_plan.has_work)
        )

    def _on_worker_progress(self, pct: float, speed: str, eta: str):
        self.prog_bar.setValue(int(pct))
        info_parts = []
        if speed:
            info_parts.append(speed)
        if eta:
            info_parts.append(eta)
        if info_parts:
            self.lbl_status.setText(" · ".join(info_parts))

    def _on_worker_log(self, line: str):
        self.txt_log.append(line)

    def _on_worker_status(self, status: str):
        self.lbl_status.setText(status)

    def _on_direct_rip_finished(self, success: bool, message: str):
        self._set_ui_ripping_state(False)
        if success:
            self.prog_bar.setValue(100)
            self.lbl_status.setText(tr("Fertig: {msg}", msg=message))
            QMessageBox.information(self, tr("Ripping abgeschlossen"), message)
        else:
            self.lbl_status.setText(tr("Fehlgeschlagen: {msg}", msg=message))
            QMessageBox.critical(self, tr("Ripping fehlgeschlagen"), message)

    def _on_stop_clicked(self):
        if self.active_worker:
            self.active_worker.stop()

    def _set_ui_ripping_state(self, is_ripping: bool):
        self.btn_action.setEnabled(not is_ripping)
        self.btn_stop.setVisible(is_ripping)
        self.table_titles.setEnabled(not is_ripping)
        self.combo_drives.setEnabled(not is_ripping)
