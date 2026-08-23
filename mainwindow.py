# -*- coding: utf-8 -*-
"""
Hauptfenster des Linux Media Encoders.
Implementiert das exakte AME-Split-Layout (Warteschlange links, Videoeinstellungen rechts)
mit bidirektional synchronisierten Bitraten-Schiebereglern.
"""

import json
import os
import uuid
from PyQt6.QtCore import Qt, QSize, QSettings, QProcess, QTimer, QUrl, pyqtSlot
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QProgressBar, QTextEdit, QFileDialog, QMessageBox,
    QHeaderView, QToolBar, QStyle, QGroupBox, QSpinBox, QDoubleSpinBox,
    QTabWidget, QSplitter, QCheckBox, QSlider, QApplication, QFrame, QDialog,
    QStackedWidget, QMenu
)
from PyQt6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QFont, QIcon, QPixmap, QTransform

from i18n import (
    QAction, QCheckBox, QComboBox, QDialog, QFileDialog, QGroupBox, QLabel,
    LocalizedString, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QWidget, tr,
)

import presets
import styles
import subtitle_utils
from crop_label import CropImageLabel
from ffmpeg_worker import FFmpegWorker
from version import __version__


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Linux Media Encoder")
        self.setMinimumSize(QSize(1150, 750))

        # Anwendungs-Icon setzen (liegt neben dem Skript bzw. im Installationsverzeichnis)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linux-media-encoder.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Persistente Einstellungen (z. B. Theme-Auswahl)
        self.settings_store = QSettings("LinuxMediaEncoder", "LinuxMediaEncoder")

        # Interner State
        self.jobs = []            # Liste aller Konvertierungs-Jobs
        self.current_job_idx = -1 # Index des aktuell laufenden Jobs
        self.active_worker = None # Aktive FFmpegWorker-Instanz
        self.is_running = False   # Warteschlangen-Status
        self._image_preview_pixmap = QPixmap()
        self._image_preview_rotation = 0  # Drehwinkel (0/90/180/270) des angezeigten Jobs
        self._single_job_idx = None   # Kontextmenü "nur diesen Job starten"
        self._run_total = 0           # Jobs im aktuellen Lauf (Gesamtfortschritt)
        self._run_done = 0

        # UI initialisieren
        self._init_menu_and_toolbar()

        # UI-Komponenten erstellen
        self._create_queue_table()
        self._create_console_view()
        self._create_settings_view()

        # Zusammenbau des AME-Split-Layouts (Queue links, Einstellungen rechts)
        self._assemble_split_layout()

        # Signalverbindungen für Tabellenselektion
        self.queue_table.itemSelectionChanged.connect(self._on_job_selection_changed)

        # Drag & Drop aktivieren
        self.setAcceptDrops(True)

        # Statusleiste + Gesamtfortschritt der Warteschlange
        self.statusBar().showMessage(tr(
            "Bereit — Dateien per Drag & Drop oder über „Hinzufügen“ laden."
        ))
        self.queue_progress = QProgressBar()
        self.queue_progress.setMaximumWidth(220)
        self.queue_progress.setFormat("Warteschlange %p %")
        self.queue_progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.queue_progress)

        # Gespeichertes Theme anwenden (Standard: Breeze Dark im AME-Stil).
        saved_theme = self.settings_store.value("theme", "dark")
        self._set_theme(saved_theme if saved_theme in ("dark", "native") else "dark", persist=False)

        # UI-Zustand anpassen
        self._update_ui_state()

        # Startzustand: ohne geladene/ausgewählte Datei ist das Einstellungs-Panel
        # gesperrt, damit Format/Vorgabe nicht ohne Job verstellt werden können.
        self.settings_widget.setEnabled(False)

        # Sitzungs-Persistenz ist opt-in (main.py aktiviert sie) — Tests und
        # eingebettete Nutzung sollen die Benutzer-Config nicht anfassen.
        self._session_persistence = False

    # --- DRAG AND DROP ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if not file_path:
                continue

            lower_path = file_path.lower()
            is_optical = False
            if os.path.isfile(file_path) and (lower_path.endswith(".iso") or lower_path.endswith(".img") or lower_path.endswith(".nrg")):
                is_optical = True
            elif os.path.isdir(file_path):
                subdirs = [d.upper() for d in os.listdir(file_path)] if os.path.exists(file_path) else []
                if "VIDEO_TS" in subdirs or "BDMV" in subdirs or "AUDIO_TS" in subdirs:
                    is_optical = True

            if is_optical:
                self._on_rip_disc_clicked(initial_source=file_path)
            elif os.path.isfile(file_path):
                self._add_file_to_queue(file_path)

    # --- UI INIT METHODS ---
    def _init_menu_and_toolbar(self):
        """Erstellt Menüleiste und Haupt-Toolbar."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu(tr("Datei"))
        add_action = QAction("Datei(en) hinzufügen...", self)
        add_action.triggered.connect(self._on_add_files_clicked)
        file_menu.addAction(add_action)

        rip_action = QAction("CD/DVD/BD rippen...", self)
        rip_action.setShortcut("Ctrl+D")
        rip_action.triggered.connect(lambda: self._on_rip_disc_clicked())
        file_menu.addAction(rip_action)

        file_menu.addSeparator()
        exit_action = QAction("Beenden", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menubar.addMenu(tr("Bearbeiten"))
        trim_menu_action = QAction("Video verkürzen (Schnitt)...", self)
        trim_menu_action.triggered.connect(self._on_trim_video_clicked)
        edit_menu.addAction(trim_menu_action)
        
        theme_menu = menubar.addMenu(tr("Design"))
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self.dark_action = QAction("Breeze Dark (LME)", self)
        self.dark_action.setCheckable(True)
        self.dark_action.triggered.connect(lambda: self._set_theme("dark"))
        theme_group.addAction(self.dark_action)
        theme_menu.addAction(self.dark_action)
        self.native_action = QAction("System-Standard (Native)", self)
        self.native_action.setCheckable(True)
        self.native_action.triggered.connect(lambda: self._set_theme("native"))
        theme_group.addAction(self.native_action)
        theme_menu.addAction(self.native_action)

        view_menu = menubar.addMenu(tr("Ansicht"))
        self.action_toggle_ffmpeg_view = QAction("FFmpeg-Ausgabe && Befehl anzeigen", self)
        self.action_toggle_ffmpeg_view.setCheckable(True)
        self.action_toggle_ffmpeg_view.setChecked(False)
        self.action_toggle_ffmpeg_view.toggled.connect(self._on_toggle_ffmpeg_view)
        view_menu.addAction(self.action_toggle_ffmpeg_view)

        # Nach Abschluss der Warteschlange: optional Energie-Aktion ausführen.
        # Bewusst NICHT persistent — ein vergessenes "Herunterfahren" wäre fatal.
        queue_menu = menubar.addMenu(tr("Warteschlange"))
        power_group = QActionGroup(self)
        power_group.setExclusive(True)
        self.power_actions = {}
        for key, label in (
            ("none", "Nach Abschluss: nichts tun"),
            ("suspend", "Nach Abschluss: Ruhezustand"),
            ("poweroff", "Nach Abschluss: herunterfahren"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            power_group.addAction(action)
            queue_menu.addAction(action)
            self.power_actions[key] = action
        self.power_actions["none"].setChecked(True)

        help_menu = menubar.addMenu(tr("Hilfe"))
        about_action = QAction("Über Linux Media Encoder", self)
        about_action.triggered.connect(self._on_about_clicked)
        help_menu.addAction(about_action)

        # Toolbar
        self.toolbar = QToolBar(tr("Hauptsteuerung"), self)
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        
        # Start-Button (Grün)
        btn_start = QPushButton(" Start")
        btn_start.setObjectName("btn_start")
        btn_start.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        btn_start.setToolTip("Warteschlange starten")
        btn_start.clicked.connect(self._on_start_queue)
        self.toolbar.addWidget(btn_start)
        
        # Stop-Button (Rot)
        btn_stop = QPushButton(" Stopp")
        btn_stop.setObjectName("btn_stop")
        btn_stop.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        btn_stop.setToolTip("Aktuelle Verarbeitung stoppen")
        btn_stop.clicked.connect(self._on_stop_queue)
        self.toolbar.addWidget(btn_stop)
        
        self.toolbar.addSeparator()
        
        # Add-Button
        self.action_add = QAction("Hinzufügen", self)
        self.action_add.triggered.connect(self._on_add_files_clicked)
        self.action_add.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.action_add.setToolTip("Dateien zur Warteschlange hinzufügen")
        self.toolbar.addAction(self.action_add)

        # Rip-Button
        self.action_rip = QAction("CD/DVD/BD rippen...", self)
        self.action_rip.triggered.connect(lambda: self._on_rip_disc_clicked())
        self.action_rip.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveCDIcon))
        self.action_rip.setToolTip("CD, DVD oder Blu-ray einlesen und rippen (Strg+D)")
        self.toolbar.addAction(self.action_rip)

        # Trim-Button
        self.action_trim = QAction("Video verkürzen", self)
        self.action_trim.triggered.connect(self._on_trim_video_clicked)
        self.action_trim.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward))
        self.action_trim.setToolTip("Video verkürzen (Start-/Endpunkt setzen & Codec wählen)")
        self.toolbar.addAction(self.action_trim)
        
        # Remove-Button
        self.action_remove = QAction("Löschen", self)
        self.action_remove.triggered.connect(self._on_remove_selected_clicked)
        self.action_remove.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.action_remove.setToolTip("Ausgewählten Job löschen")
        self.toolbar.addAction(self.action_remove)

        # Clear-Button
        self.action_clear = QAction("Leeren", self)
        self.action_clear.triggered.connect(self._on_clear_queue_clicked)
        self.action_clear.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        self.action_clear.setToolTip("Warteschlange leeren")
        self.toolbar.addAction(self.action_clear)

    def _create_queue_table(self):
        """Erstellt die Warteschlangentabelle."""
        self.queue_table = QTableWidget(self)
        self.queue_table.setColumnCount(8)
        # AME-Spaltenlayout: Format und Vorgabe (Preset) als blaue Links öffnen
        # die Exporteinstellungen, die Ausgabedatei den Speichern-Dialog.
        self.queue_table.setHorizontalHeaderLabels([
            "Datei", "Format", "Vorgabe", "Ausgabedatei",
            "Status", "Fortschritt", "Speed", "Verbleibend"
        ])

        # Headers anpassen
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.verticalHeader().setDefaultSectionSize(28)
        self.queue_table.setShowGrid(False)
        
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Mehrfachauswahl erlaubt Löschen mehrerer Jobs auf einmal
        self.queue_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.queue_table.setAlternatingRowColors(True)

        # Double Click und Cell Click Events für den Export Settings Dialog
        self.queue_table.cellDoubleClicked.connect(self._on_table_cell_double_clicked)
        self.queue_table.cellClicked.connect(self._on_table_cell_clicked)

        # Kontextmenü (Job starten, duplizieren, verschieben, Zieldatei zeigen …)
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_table.customContextMenuRequested.connect(self._on_queue_context_menu)

    def _create_console_view(self):
        """Erstellt das Konsolen-Log-Widget."""
        self.console_widget = QWidget()
        layout = QVBoxLayout(self.console_widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        self.console = QTextEdit()
        self.console.setObjectName("console_output")
        self.console.setReadOnly(True)
        # Ohne Limit wächst das Log bei langen Encodes unbegrenzt im RAM
        self.console.document().setMaximumBlockCount(5000)
        layout.addWidget(self.console)
        
        btn_clear_console = QPushButton("Log leeren")
        btn_clear_console.setFixedWidth(100)
        btn_clear_console.clicked.connect(self.console.clear)
        layout.addWidget(btn_clear_console)

    def _create_settings_view(self):
        """Erstellt die rechte Einstellungs-Seitenleiste im AME-Format."""
        self.settings_widget = QWidget()
        layout = QVBoxLayout(self.settings_widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        
        # Titel
        self.settings_title_label = QLabel("Video- & Exporteinstellungen")
        self.settings_title_label.setObjectName("title_label")
        layout.addWidget(self.settings_title_label)
        
        # Exporteinstellungen Gruppe
        self.export_group = QGroupBox("Metadaten && Format")
        export_layout = QGridLayout(self.export_group)
        export_layout.setSpacing(4)
        export_layout.setContentsMargins(6, 6, 6, 6)
        
        # 1. Format / Container — bewusst NICHT editierbar: currentTextChanged
        # würde sonst bei jedem Tastendruck das Settings-Dict neu aufbauen und
        # die Dateiendung auf Tippfragmente ("video.h") setzen.
        export_layout.addWidget(QLabel("Format:"), 0, 0)
        self.combo_format = QComboBox()
        # Bildformate erscheinen nur bei Bild-Quellen; Start mit Video-Liste.
        self._format_options_are_image = False
        self.combo_format.addItems(presets.get_format_options(False))
        self.combo_format.sourceTextChanged.connect(self._on_format_changed)
        export_layout.addWidget(self.combo_format, 0, 1)

        # 2. Preset (ebenfalls nicht editierbar, gleiche Begründung)
        export_layout.addWidget(QLabel("Vorgabe:"), 1, 0)
        self.combo_preset = QComboBox()
        self.combo_preset.addItems(presets.get_preset_dropdown_options(False))
        self.combo_preset.sourceTextChanged.connect(self._on_preset_changed)
        export_layout.addWidget(self.combo_preset, 1, 1)
        
        # 3. Ausgabepfad als blauer Link
        export_layout.addWidget(QLabel("Ausgabename:"), 2, 0)
        self.lbl_output_link = QLabel("Keine Datei geladen")
        self.lbl_output_link.setObjectName("output_link")
        self.lbl_output_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_output_link.mousePressEvent = self._on_output_link_clicked
        export_layout.addWidget(self.lbl_output_link, 2, 1)

        output_actions = QHBoxLayout()
        output_actions.setSpacing(4)
        self.btn_output_dir_all = QPushButton("Ausgabeordner fuer alle...")
        self.btn_output_dir_all.clicked.connect(self._on_apply_output_dir_to_all_clicked)
        self.btn_settings_all = QPushButton("Einstellungen auf alle anwenden")
        self.btn_settings_all.clicked.connect(self._on_apply_settings_to_all_clicked)
        output_actions.addWidget(self.btn_output_dir_all)
        output_actions.addWidget(self.btn_settings_all)
        export_layout.addLayout(output_actions, 3, 0, 1, 2)
        
        # 4. Checkboxen Video/Audio exportieren
        chk_layout = QHBoxLayout()
        self.chk_export_video = QCheckBox("Video")
        self.chk_export_video.setChecked(True)
        self.chk_export_video.stateChanged.connect(self._on_export_video_toggled)
        self.chk_export_audio = QCheckBox("Audio")
        self.chk_export_audio.setChecked(True)
        self.chk_export_audio.stateChanged.connect(self._on_export_audio_toggled)
        chk_layout.addWidget(self.chk_export_video)
        chk_layout.addWidget(self.chk_export_audio)
        export_layout.addLayout(chk_layout, 4, 0, 1, 2)
        
        layout.addWidget(self.export_group)
        
        # Summary Box
        self.summary_box = QLabel("Zusammenfassung: Keine Datei ausgewählt.")
        self.summary_box.setObjectName("summary_box")
        self.summary_box.setWordWrap(True)
        layout.addWidget(self.summary_box)
        
        # Tabs für Video/Audio-Parameter
        self.settings_tabs = QTabWidget()
        
        # --- VIDEO TAB ---
        video_tab = QWidget()
        v_tab_layout = QVBoxLayout(video_tab)
        v_tab_layout.setContentsMargins(6, 6, 6, 6)
        v_tab_layout.setSpacing(4)
        
        v_grid = QGridLayout()
        v_grid.setSpacing(4)
        
        # Video Codec
        self.lbl_video_codec = QLabel("Codec:")
        v_grid.addWidget(self.lbl_video_codec, 0, 0)
        self.combo_vcodec = QComboBox()
        self.combo_vcodec.setEditable(True)
        self.combo_vcodec.addItems(["libx264", "libx265", "libvpx-vp9", "libsvtav1", "copy", "none"])
        self.combo_vcodec.sourceTextChanged.connect(self._on_vcodec_changed)
        v_grid.addWidget(self.combo_vcodec, 0, 1)
        
        # Skalierung (Quelle beibehalten / einpassen / verzerren)
        self.lbl_scale_mode = QLabel("Skalierung:")
        v_grid.addWidget(self.lbl_scale_mode, 1, 0)
        self.combo_scale_mode = QComboBox()
        self.combo_scale_mode.addItems(presets.scale_mode_options())
        self.combo_scale_mode.sourceTextChanged.connect(self._on_scale_mode_changed)
        v_grid.addWidget(self.combo_scale_mode, 1, 1)

        # Breite / Höhe
        self.lbl_video_width = QLabel("Breite:")
        v_grid.addWidget(self.lbl_video_width, 2, 0)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(16, 7680)
        self.spin_width.setValue(1920)
        self.spin_width.valueChanged.connect(self._on_spin_width_changed)
        v_grid.addWidget(self.spin_width, 2, 1)

        self.lbl_video_height = QLabel("Höhe:")
        v_grid.addWidget(self.lbl_video_height, 3, 0)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(16, 4320)
        self.spin_height.setValue(1080)
        self.spin_height.valueChanged.connect(self._on_spin_height_changed)
        v_grid.addWidget(self.spin_height, 3, 1)

        # Frame Rate ("Wie Quelle" = kein -r; unabhängig von der Skalierung)
        self.lbl_video_fps = QLabel("Framerate:")
        v_grid.addWidget(self.lbl_video_fps, 4, 0)
        self.combo_fps = QComboBox()
        self.combo_fps.setEditable(True)
        self.combo_fps.addItems([presets.FPS_SOURCE_LABEL, "23.976", "24", "25", "29.97", "30", "50", "60"])
        self.combo_fps.setCurrentText("25")
        self.combo_fps.sourceTextChanged.connect(self._save_ui_settings_to_job)
        v_grid.addWidget(self.combo_fps, 4, 1)

        # Profile
        self.lbl_video_profile = QLabel("Profil:")
        v_grid.addWidget(self.lbl_video_profile, 5, 0)
        self.combo_profile = QComboBox()
        self.combo_profile.setEditable(True)
        self.combo_profile.addItems(["Main", "High", "Baseline"])
        self.combo_profile.setCurrentText("High")
        self.combo_profile.sourceTextChanged.connect(self._save_ui_settings_to_job)
        v_grid.addWidget(self.combo_profile, 5, 1)

        # Bitrate-Codierung
        self.lbl_video_encoding = QLabel("Codierung:")
        v_grid.addWidget(self.lbl_video_encoding, 6, 0)
        self.combo_encoding = QComboBox()
        self.combo_encoding.addItems(["VBR, 1 Durchgang", "CBR", "CRF (Qualitätsbasiert)"])
        self.combo_encoding.sourceTextChanged.connect(self._on_encoding_method_changed)
        v_grid.addWidget(self.combo_encoding, 6, 1)

        # Target Bitrate / CRF mit synchronisiertem Schieberegler
        self.lbl_bitrate_val = QLabel("Zielbitrate:")
        v_grid.addWidget(self.lbl_bitrate_val, 7, 0)
        
        bitrate_layout = QHBoxLayout()
        bitrate_layout.setSpacing(4)
        
        self.slider_bitrate = QSlider(Qt.Orientation.Horizontal)
        self.slider_bitrate.setRange(1, 2000)
        self.slider_bitrate.setValue(80)
        self.slider_bitrate.valueChanged.connect(self._on_slider_bitrate_changed)
        bitrate_layout.addWidget(self.slider_bitrate)
        
        self.spin_bitrate_val = QDoubleSpinBox()
        self.spin_bitrate_val.setRange(0.1, 200.0)
        self.spin_bitrate_val.setValue(8.0)
        self.spin_bitrate_val.setDecimals(1)
        self.spin_bitrate_val.setFixedWidth(65)
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
        a_tab_layout.setContentsMargins(6, 6, 6, 6)
        a_tab_layout.setSpacing(4)
        
        a_grid = QGridLayout()
        a_grid.setSpacing(4)
        
        # Audio Codec
        a_grid.addWidget(QLabel("Codec:"), 0, 0)
        self.combo_audiocodec = QComboBox()
        self.combo_audiocodec.setEditable(True)
        self.combo_audiocodec.addItems(["AAC", "MP3", "Opus", "FLAC", "Kopieren (Copy)"])
        self.combo_audiocodec.sourceTextChanged.connect(self._on_audio_codec_changed)
        a_grid.addWidget(self.combo_audiocodec, 0, 1)
        
        # Audio Bitrate
        a_grid.addWidget(QLabel("Bitrate:"), 1, 0)
        self.combo_audiobitrate = QComboBox()
        self.combo_audiobitrate.setEditable(True)
        self.combo_audiobitrate.addItems(["128k", "192k", "256k", "320k"])
        self.combo_audiobitrate.setCurrentText("192k")
        self.combo_audiobitrate.sourceTextChanged.connect(self._save_ui_settings_to_job)
        a_grid.addWidget(self.combo_audiobitrate, 1, 1)
        
        a_tab_layout.addLayout(a_grid)
        a_tab_layout.addStretch()
        self.settings_tabs.addTab(audio_tab, "Audio")
        
        # --- UNTERTITEL TAB ---
        subtitle_tab = QWidget()
        sub_tab_layout = QVBoxLayout(subtitle_tab)
        sub_tab_layout.setContentsMargins(6, 6, 6, 6)
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
        self.combo_sub_source.sourceTextChanged.connect(self._on_sub_source_changed)
        source_layout.addWidget(self.combo_sub_source)
        
        self.edit_sub_source_custom = QLineEdit()
        self.edit_sub_source_custom.setPlaceholderText("Sprache eingeben...")
        self.edit_sub_source_custom.setVisible(False)
        self.edit_sub_source_custom.textChanged.connect(self._save_ui_settings_to_job)
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
        self.combo_sub_translate.sourceTextChanged.connect(self._on_sub_translate_changed)
        translate_layout.addWidget(self.combo_sub_translate)
        
        self.edit_sub_translate_custom = QLineEdit()
        self.edit_sub_translate_custom.setPlaceholderText("Sprache eingeben...")
        self.edit_sub_translate_custom.setVisible(False)
        self.edit_sub_translate_custom.textChanged.connect(self._save_ui_settings_to_job)
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
        self.edit_sub_file_path.textChanged.connect(self._save_ui_settings_to_job)
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
        self.combo_sub_mode.sourceTextChanged.connect(self._save_ui_settings_to_job)
        sub_grid.addWidget(self.combo_sub_mode, 6, 1)
        
        sub_tab_layout.addLayout(sub_grid)
        sub_tab_layout.addStretch()
        self.settings_tabs.addTab(subtitle_tab, "Untertitel")
        
        layout.addWidget(self.settings_tabs)
        
        # Befehlsvorschau (FFmpeg-Detail, standardmäßig ausgeblendet -> reiner GUI-Encoder)
        self.cmd_group = QGroupBox("FFmpeg Befehlsvorschau")
        cmd_layout = QVBoxLayout(self.cmd_group)
        cmd_layout.setContentsMargins(4, 4, 4, 4)
        cmd_layout.setSpacing(4)
        self.edit_cmd_preview = QTextEdit()
        self.edit_cmd_preview.setObjectName("cmd_preview")
        self.edit_cmd_preview.setReadOnly(True)
        self.edit_cmd_preview.setFixedHeight(65)
        cmd_layout.addWidget(self.edit_cmd_preview)
        self.cmd_group.setVisible(False)
        layout.addWidget(self.cmd_group)
        
        layout.addStretch()

    def _assemble_split_layout(self):
        """Baut das geteilte Layout (Split-Layout) ohne lose Docks zusammen."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        
        # Horizontaler Hauptsplitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # --- LINKE SPALTE (Queue & Console/Presets) ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        # Vertikaler Splitter für die linke Spalte
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_layout.addWidget(self.left_splitter)
        
        # Obere Hälfte: Warteschlange oder fokussierte Bildvorschau
        self.left_mode_stack = QStackedWidget()

        self.queue_group = QGroupBox("Warteschlange (Queue)")
        queue_layout = QVBoxLayout(self.queue_group)
        queue_layout.setContentsMargins(4, 6, 4, 4)
        queue_layout.addWidget(self.queue_table)

        self.image_preview_group = QGroupBox("Bildvorschau")
        image_preview_layout = QVBoxLayout(self.image_preview_group)
        image_preview_layout.setContentsMargins(8, 8, 8, 8)
        image_preview_layout.setSpacing(8)

        image_preview_header = QHBoxLayout()
        image_preview_header.setContentsMargins(0, 0, 0, 0)
        image_preview_header.setSpacing(6)
        self.image_preview_file_label = QLabel("Keine Datei geladen")
        self.image_preview_file_label.setObjectName("title_label")
        image_preview_header.addWidget(self.image_preview_file_label, stretch=1)
        self.btn_show_queue_from_image = QPushButton()
        self.btn_show_queue_from_image.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView))
        self.btn_show_queue_from_image.setToolTip("Warteschlange anzeigen")
        self.btn_show_queue_from_image.setFixedWidth(32)
        self.btn_show_queue_from_image.clicked.connect(self._show_queue_view)
        image_preview_header.addWidget(self.btn_show_queue_from_image)
        image_preview_layout.addLayout(image_preview_header)

        self.image_preview_label = CropImageLabel("[ Bildvorschau ]")
        self.image_preview_label.setObjectName("preview_frame")
        self.image_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview_label.setMinimumSize(QSize(420, 320))
        self.image_preview_label.setToolTip(
            "Zum Zuschneiden mit der Maus ein Rechteck über das Bild ziehen."
        )
        self.image_preview_label.crop_changed.connect(self._on_image_crop_changed)
        image_preview_layout.addWidget(self.image_preview_label, stretch=1)

        # Zuschnitt-/Dreh-Statuszeile + Aktions-Buttons unter der Vorschau
        crop_bar = QHBoxLayout()
        crop_bar.setContentsMargins(0, 0, 0, 0)
        crop_bar.setSpacing(6)
        self.image_crop_info_label = QLabel("")
        crop_bar.addWidget(self.image_crop_info_label, stretch=1)
        self.btn_rotate_left = QPushButton("⟲ 90°")
        self.btn_rotate_left.setToolTip("Bild um 90° gegen den Uhrzeigersinn drehen")
        self.btn_rotate_left.clicked.connect(lambda: self._on_rotate_clicked(-90))
        crop_bar.addWidget(self.btn_rotate_left)
        self.btn_rotate_right = QPushButton("⟳ 90°")
        self.btn_rotate_right.setToolTip("Bild um 90° im Uhrzeigersinn drehen")
        self.btn_rotate_right.clicked.connect(lambda: self._on_rotate_clicked(90))
        crop_bar.addWidget(self.btn_rotate_right)
        self.btn_reset_crop = QPushButton("Zuschnitt aufheben")
        self.btn_reset_crop.setEnabled(False)
        self.btn_reset_crop.clicked.connect(self._on_reset_crop_clicked)
        crop_bar.addWidget(self.btn_reset_crop)
        image_preview_layout.addLayout(crop_bar)

        self.left_mode_stack.addWidget(self.queue_group)
        self.left_mode_stack.addWidget(self.image_preview_group)
        self.left_splitter.addWidget(self.left_mode_stack)
        
        # Untere Hälfte: optionale Logs/FFmpeg-Ausgabe, standardmäßig ausgeblendet.
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.setVisible(False)
        self._console_tab_label = "Logs / FFmpeg-Ausgabe"
        self.left_splitter.addWidget(self.bottom_tabs)
        
        self.main_splitter.addWidget(left_widget)
        
        # --- RECHTE SPALTE (Settings Panel) ---
        self.settings_wrapper = QGroupBox("Exporteinstellungen")
        settings_layout_wrap = QVBoxLayout(self.settings_wrapper)
        settings_layout_wrap.setContentsMargins(4, 4, 4, 4)
        settings_layout_wrap.addWidget(self.settings_widget)
        
        self.main_splitter.addWidget(self.settings_wrapper)
        
        # Splitter-Proportionen festlegen (ca. 70% links, 30% rechts)
        self.main_splitter.setSizes([750, 350])
        # Vertikalen Splitter links aufteilen; Logs werden nur bei Bedarf eingeblendet.
        self.left_splitter.setSizes([650, 1])

    def _show_queue_view(self):
        """Zeigt die klassische Warteschlangenansicht in der linken Spalte."""
        if hasattr(self, "left_mode_stack"):
            self.left_mode_stack.setCurrentWidget(self.queue_group)

    def _show_image_preview_view(self, job):
        """Zeigt für Bildjobs eine fokussierte Vorschau statt der Queue."""
        if not hasattr(self, "left_mode_stack"):
            return
        self._set_image_preview_job(job)
        self.left_mode_stack.setCurrentWidget(self.image_preview_group)

    def _update_left_mode_for_job(self, job):
        """Schaltet die linke Spalte passend zum selektierten Job."""
        if job and presets.is_image_input(job.get("input_file")):
            self._show_image_preview_view(job)
        else:
            self._show_queue_view()

    def _set_image_preview_job(self, job):
        """Lädt das ausgewählte Quellbild in die Hauptvorschau."""
        image_path = job.get("input_file", "")
        self.image_preview_file_label.setText(os.path.basename(image_path) or "Keine Datei geladen")
        self.image_preview_file_label.setToolTip(image_path)

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self._image_preview_pixmap = QPixmap()
            self._image_preview_rotation = 0
            self.image_preview_label.clear()
            self.image_preview_label.setText("[ Bildvorschau nicht verfügbar ]")
            self.image_preview_label.set_interactive(False)
            self.image_preview_label.set_source_size(0, 0)
            self.image_preview_label.set_crop(None)
            self._update_crop_ui(None)
            return

        self._image_preview_pixmap = pixmap
        self._image_preview_rotation = presets.get_rotation(job.get("settings", {}))
        self.image_preview_label.set_source_size(*self._rotated_source_dims(self._image_preview_rotation))
        crop = presets.get_crop(job.get("settings", {}))
        self.image_preview_label.set_crop(crop)
        self.image_preview_label.set_interactive(not self._job_is_busy(job))
        self._update_crop_ui(crop)
        self._render_image_preview_pixmap()

    def _rotated_source_dims(self, angle):
        """Quellmaße (Breite, Höhe) unter Berücksichtigung der Drehung — 90°/270°
        vertauschen die Kantenlängen gegenüber dem unrotierten Quellbild."""
        w, h = self._image_preview_pixmap.width(), self._image_preview_pixmap.height()
        return (h, w) if angle in (90, 270) else (w, h)

    def _update_crop_ui(self, crop):
        """Aktualisiert Zuschnitt-/Dreh-Statuszeile und Aufheben-Button."""
        if crop:
            text = tr(
                "Zuschnitt: {width}×{height} px ab ({x}, {y})",
                width=crop["w"], height=crop["h"], x=crop["x"], y=crop["y"],
            )
            self.btn_reset_crop.setEnabled(True)
        else:
            text = tr("Kein Zuschnitt — Rechteck mit der Maus über das Bild ziehen.")
            self.btn_reset_crop.setEnabled(False)
        if self._image_preview_rotation:
            text = tr(
                "{crop} · Gedreht um {angle}°",
                crop=str(text), angle=self._image_preview_rotation,
            )
        self.image_crop_info_label.setText(text)

    def _on_rotate_clicked(self, delta):
        """Dreht das Bild des selektierten Jobs um 90° (delta=+90 im Uhrzeigersinn,
        -90 gegen den Uhrzeigersinn)."""
        selected_row = self.queue_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.jobs):
            return
        job = self.jobs[selected_row]
        if self._job_is_busy(job):
            return

        current = presets.get_rotation(job.get("settings", {}))
        new_angle = (current + delta) % 360
        job["settings"]["rotate"] = new_angle

        # Ein bestehender Zuschnitt bezieht sich auf die alte Bildausrichtung
        # und würde nach dem Drehen ein falsches Rechteck zeigen — zurücksetzen
        # statt die Koordinaten fehleranfällig umzurechnen.
        job["settings"].pop("crop", None)
        self.image_preview_label.set_crop(None)

        self._image_preview_rotation = new_angle
        self.image_preview_label.set_source_size(*self._rotated_source_dims(new_angle))
        self._render_image_preview_pixmap()
        self._update_crop_ui(None)
        # Drehung um 90°/270° vertauscht das Seitenverhältnis → Höhe nachziehen
        self._sync_size_spins_to_aspect("width")
        self._save_ui_settings_to_job()

    def _apply_image_crop_to_job(self, crop):
        """Schreibt den Zuschnitt in den selektierten Job und aktualisiert die Anzeigen."""
        selected_row = self.queue_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.jobs):
            return
        job = self.jobs[selected_row]
        if self._job_is_busy(job):
            return
        if crop:
            job["settings"]["crop"] = dict(crop)
        else:
            job["settings"].pop("crop", None)
        self._update_crop_ui(crop)
        # Zuschnitt ändert das Seitenverhältnis → Höhe bei AR-Erhalt nachziehen
        self._sync_size_spins_to_aspect("width")
        self._save_ui_settings_to_job()

    def _on_image_crop_changed(self, crop):
        """Signal aus der Bildvorschau: neuer Zuschnitt wurde aufgezogen."""
        self._apply_image_crop_to_job(presets.get_crop({"crop": crop}))

    def _on_reset_crop_clicked(self):
        """Hebt den Zuschnitt für den selektierten Bild-Job auf."""
        self.image_preview_label.set_crop(None)
        self._apply_image_crop_to_job(None)

    def _render_image_preview_pixmap(self):
        """Skaliert das geladene Bild auf die aktuell verfügbare Vorschaufläche
        und dreht es gemäß dem eingestellten Drehwinkel."""
        if self._image_preview_pixmap.isNull() or not hasattr(self, "image_preview_label"):
            return

        target_size = self.image_preview_label.size()
        if target_size.width() < 32 or target_size.height() < 32:
            target_size = QSize(700, 500)

        angle = self._image_preview_rotation
        # Bei 90°/270° vertauscht die Drehung die Kantenlängen — den Zielrahmen
        # vorab spiegeln, damit das gedrehte Ergebnis wieder in die Vorschau passt.
        fit_size = QSize(target_size.height(), target_size.width()) if angle in (90, 270) else target_size

        # Erst das (i. d. R. hochauflösende) Quellbild herunterskalieren, dann
        # das kleine Ergebnis drehen — spart das Drehen voller Auflösung bei
        # jedem Resize-Event.
        scaled = self._image_preview_pixmap.scaled(
            fit_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if angle:
            scaled = scaled.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
        self.image_preview_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if (
            hasattr(self, "left_mode_stack")
            and self.left_mode_stack.currentWidget() == self.image_preview_group
        ):
            self._render_image_preview_pixmap()

    # --- JOB LOGIK & CONTROL ---
    def _add_file_to_queue(self, file_path):
        """Erstellt ein Job-Objekt und fügt es der GUI hinzu."""
        base_dir = os.path.dirname(file_path)

        # Standard-Preset: Bilder bekommen ein Bild-Preset (JPEG-Quellen → PNG,
        # sonst → JPEG), alles andere MP4 H.264.
        if presets.is_image_input(file_path):
            src_ext = os.path.splitext(file_path)[1].lstrip(".").lower()
            if src_ext in ("jpg", "jpeg"):
                default_settings = dict(presets.PRESETS["PNG (Bild) - Verlustfrei"])
            else:
                default_settings = dict(presets.PRESETS["JPEG (Bild) - Hohe Qualität"])
        else:
            default_settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        
        # Zielpfad bauen
        output_file = self._default_output_file(file_path, base_dir, default_settings["container"])
        
        job = {
            "input_file": file_path,
            "output_dir": base_dir,
            "output_file": output_file,
            "settings": default_settings,
            "status": "Bereit",
            "progress": 0.0,
            "speed": "0.0x",
            "time_remaining": "Bereit"
        }
        
        self.jobs.append(job)
        self._insert_job_into_table(job)
        # Quellmaße/-dauer im Hintergrund ermitteln (für AR-Kopplung und ETA)
        self._prefetch_source_info(job)

        # Neue Zeile selektieren
        self.queue_table.selectRow(len(self.jobs) - 1)
        self._update_ui_state()

    # Status-Farbcodierung der Warteschlange (Breeze-Signalfarben)
    STATUS_COLORS = {
        "Fertig": styles.START_GREEN,
        "Fehlgeschlagen": styles.STOP_RED,
        "Abgebrochen": styles.WARN_ORANGE,
    }

    def _apply_status_cell(self, row, job):
        """Färbt die Status-Zelle: grün=fertig, rot=Fehler, orange=Abbruch, blau=aktiv."""
        item = self.queue_table.item(row, 4)
        if item is None:
            return
        item.setText(job["status"])
        color = self.STATUS_COLORS.get(job["status"])
        if color is None and str(job["status"]).endswith("..."):
            color = getattr(self, "_link_color", styles.LINK_DARK)
        if color:
            item.setForeground(QColor(color))
        else:
            item.setData(Qt.ItemDataRole.ForegroundRole, None)
        # Fehlerdetails bzw. Schnellzugriff direkt an der Zeile verfügbar machen
        if job["status"] == "Fehlgeschlagen" and job.get("error_tail"):
            item.setToolTip(tr(
                "Doppelklick für Details.\n\nLetzte FFmpeg-Meldungen:\n{details}",
                details=job["error_tail"],
            ))
        elif job["status"] == "Fertig":
            item.setToolTip("Doppelklick: Ausgabedatei abspielen")
        else:
            item.setToolTip("")

    def _apply_link_cells(self, row, job):
        """Befüllt die AME-Link-Spalten (Format, Vorgabe, Ausgabedatei) einer Zeile."""
        link_color = QColor(getattr(self, "_link_color", styles.LINK_DARK))
        link_font = QFont()
        link_font.setUnderline(True)

        settings = job.get("settings", {})
        preset_name = tr(presets.preset_label(settings))
        # Beschnittene Jobs in der Queue kenntlich machen, damit niemand
        # versehentlich gekürzt exportiert.
        trim = presets.trim_label(settings)
        if trim.endswith("Ende"):
            trim = trim[:-4] + tr("Ende")
        preset_text = tr("{preset} · {trim}", preset=preset_name, trim=trim) if trim else preset_name
        preset_tip = tr("{preset}\nSchnitt: {trim}", preset=preset_name, trim=trim) if trim else preset_name
        cells = [
            (1, presets.format_label(settings),
             tr("{container} — klicken für Exporteinstellungen",
                container=f"{settings.get('container', '')}".upper())),
            (2, preset_text, preset_tip),
            (3, os.path.basename(job["output_file"]), job["output_file"]),
        ]
        for col, text, tooltip in cells:
            item = self.queue_table.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.queue_table.setItem(row, col, item)
            item.setText(text)
            item.setToolTip(tooltip)
            item.setForeground(link_color)
            item.setFont(link_font)

    def _insert_job_into_table(self, job):
        """Erstellt die Zellen-Items für einen Job."""
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)

        # 0. Datei
        file_item = QTableWidgetItem(os.path.basename(job["input_file"]))
        file_item.setToolTip(tr(
            "Quelle: {source}\nZiel: {target}",
            source=job["input_file"], target=job["output_file"],
        ))
        file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.queue_table.setItem(row, 0, file_item)

        # 1.-3. AME-Style: Format, Vorgabe und Ausgabedatei als blaue Links
        self._apply_link_cells(row, job)

        # 4. Status
        status_item = QTableWidgetItem(job["status"])
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.queue_table.setItem(row, 4, status_item)
        self._apply_status_cell(row, job)

        # 5. Fortschrittsbalken
        prog_bar = QProgressBar()
        prog_bar.setValue(int(job["progress"]))
        self.queue_table.setCellWidget(row, 5, prog_bar)

        # 6. Geschwindigkeit
        speed_item = QTableWidgetItem(job["speed"])
        speed_item.setFlags(speed_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.queue_table.setItem(row, 6, speed_item)

        # 7. Verbleibende Zeit
        rem_item = QTableWidgetItem(job["time_remaining"])
        rem_item.setFlags(rem_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.queue_table.setItem(row, 7, rem_item)

    def _update_table_row(self, idx):
        """Aktualisiert die Zeilenanzeige für einen geänderten Job."""
        if idx < 0 or idx >= len(self.jobs):
            return

        job = self.jobs[idx]

        self.queue_table.item(idx, 0).setToolTip(tr(
            "Quelle: {source}\nZiel: {target}",
            source=job["input_file"], target=job["output_file"],
        ))
        self._apply_link_cells(idx, job)
        self._apply_status_cell(idx, job)

        prog_widget = self.queue_table.cellWidget(idx, 5)
        if isinstance(prog_widget, QProgressBar):
            prog_widget.setValue(int(job["progress"]))

        self.queue_table.item(idx, 6).setText(job["speed"])
        self.queue_table.item(idx, 7).setText(job["time_remaining"])

    def _on_table_cell_double_clicked(self, row, column):
        """Öffnet den Export-Settings-Dialog bei Doppelklick auf eine Zeile.
        Doppelklick auf den Status zeigt bei fehlgeschlagenen Jobs die
        FFmpeg-Fehlerdetails und spielt bei fertigen Jobs die Ausgabedatei ab."""
        if column == 4 and 0 <= row < len(self.jobs):
            job = self.jobs[row]
            if job["status"] == "Fehlgeschlagen" and job.get("error_tail"):
                self._show_error_details(row)
                return
            if job["status"] == "Fertig" and os.path.exists(job["output_file"]):
                QDesktopServices.openUrl(QUrl.fromLocalFile(job["output_file"]))
                return
        self._open_export_settings_dialog_for_row(row)

    def _show_error_details(self, row):
        """Zeigt die letzten FFmpeg-Meldungen eines fehlgeschlagenen Jobs."""
        if row < 0 or row >= len(self.jobs):
            return
        job = self.jobs[row]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Fehlerdetails")
        box.setText(tr(
            "Job fehlgeschlagen: {filename}",
            filename=os.path.basename(job["input_file"]),
        ))
        box.setDetailedText(job.get("error_tail") or "Keine FFmpeg-Ausgabe aufgezeichnet.")
        box.exec()

    def _on_table_cell_clicked(self, row, column):
        """AME-Verhalten: Format/Vorgabe öffnen die Exporteinstellungen,
        die Ausgabedatei öffnet den Speichern-Dialog."""
        if column in (1, 2):
            self._open_export_settings_dialog_for_row(row)
        elif column == 3:
            self._choose_output_file_for_row(row)

    def _open_export_settings_dialog_for_row(self, row):
        """Öffnet den modalen Export-Settings-Dialog für die angegebene Zeile."""
        if row < 0 or row >= len(self.jobs):
            return
            
        job = self.jobs[row]
        if self._job_is_busy(job):
            return
            
        from export_settings_dialog import ExportSettingsDialog
        dialog = ExportSettingsDialog(job["input_file"], job["output_file"], job["settings"], self)
        if dialog.exec():
            new_output_file, new_settings = dialog.get_results()
            job["output_file"] = new_output_file
            job["output_dir"] = os.path.dirname(new_output_file)
            job["settings"] = new_settings
            
            self._update_table_row(row)
            self._load_job_settings_to_ui(job)

    # --- SETTINGS LOGIK ---
    def _block_combobox_signals(self, block):
        """Hilfsfunktion zum temporären Unterdrücken von GUI-Trigger-Events."""
        self.combo_format.blockSignals(block)
        self.combo_preset.blockSignals(block)
        self.chk_export_video.blockSignals(block)
        self.chk_export_audio.blockSignals(block)
        self.combo_vcodec.blockSignals(block)
        self.combo_scale_mode.blockSignals(block)
        self.combo_fps.blockSignals(block)
        self.combo_profile.blockSignals(block)
        self.combo_encoding.blockSignals(block)
        self.spin_width.blockSignals(block)
        self.spin_height.blockSignals(block)
        self.spin_bitrate_val.blockSignals(block)
        self.slider_bitrate.blockSignals(block)
        self.combo_audiocodec.blockSignals(block)
        self.combo_audiobitrate.blockSignals(block)
        self.chk_subtitles.blockSignals(block)
        self.combo_sub_source.blockSignals(block)
        self.combo_sub_translate.blockSignals(block)
        self.combo_sub_mode.blockSignals(block)
        self.edit_sub_source_custom.blockSignals(block)
        self.edit_sub_translate_custom.blockSignals(block)
        self.edit_sub_file_path.blockSignals(block)

    def _is_custom_mode(self, settings=None):
        """True, wenn die aktuelle Auswahl alle Codec-Optionen anzeigen soll."""
        return (
            self.combo_preset.currentText() == "Benutzerdefiniert"
            or bool((settings or {}).get("custom_mode"))
        )

    def _sync_video_codec_combobox(self, container, custom=False):
        """Aktualisiert die Video-Codec-Auswahlliste."""
        current_codec = self.combo_vcodec.currentText()
        # Vorherigen Block-Zustand merken und wiederherstellen, damit ein
        # umschließendes _block_combobox_signals(True) nicht aufgehoben wird.
        prev_blocked = self.combo_vcodec.blockSignals(True)
        self.combo_vcodec.clear()
        self.combo_vcodec.addItems(presets.get_video_codec_options(container, custom))
        if current_codec:
            self.combo_vcodec.setCurrentText(current_codec)
        self.combo_vcodec.blockSignals(prev_blocked)

    def _get_container_from_format_text(self, text):
        return presets.container_from_format_text(text)

    def _current_container_is_image(self):
        """True, wenn das aktuell gewählte Format ein Bildformat ist."""
        return self._get_container_from_format_text(self.combo_format.currentText()) in presets.IMAGE_CONTAINERS

    def _current_container(self):
        """Aktueller Zielcontainer aus dem Format-Dropdown."""
        return self._get_container_from_format_text(self.combo_format.currentText())

    def _set_settings_tab_visible(self, index, visible):
        """Qt-Versionen ohne setTabVisible fallen auf deaktivierte Tabs zurück."""
        if hasattr(self.settings_tabs, "setTabVisible"):
            self.settings_tabs.setTabVisible(index, visible)
        self.settings_tabs.setTabEnabled(index, visible and self.settings_tabs.isTabEnabled(index))

    def _apply_media_ui_mode(self, is_image):
        """Schaltet sichtbare Begriffe und Bedienelemente zwischen Video und Bild."""
        if is_image:
            self.settings_title_label.setText("Bild- & Exporteinstellungen")
            if hasattr(self, "settings_wrapper"):
                self.settings_wrapper.setTitle("Bildeinstellungen")
            self.export_group.setTitle("Metadaten && Bildformat")
            self.chk_export_video.setText("Bild")
            self.lbl_video_codec.setText("Bild-Codec:")
            self.settings_tabs.setTabText(0, "Bild")
        else:
            self.settings_title_label.setText("Video- & Exporteinstellungen")
            if hasattr(self, "settings_wrapper"):
                self.settings_wrapper.setTitle("Exporteinstellungen")
            self.export_group.setTitle("Metadaten && Format")
            self.chk_export_video.setText("Video")
            self.lbl_video_codec.setText("Codec:")
            self.settings_tabs.setTabText(0, "Video")

        self.chk_export_audio.setVisible(not is_image)
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

    def _default_output_file(self, input_file, output_dir, container):
        """Erzeugt den Standard-Zielnamen fuer einen Job in einem Ausgabeordner."""
        base_name = os.path.basename(input_file)
        root_name, _ = os.path.splitext(base_name)
        return os.path.join(output_dir, f"{root_name}_lme.{container}")

    def _set_job_output_dir(self, job, output_dir):
        """Setzt nur den Ausgabeordner; Dateiname bleibt pro Quelle eindeutig."""
        container = job.get("settings", {}).get("container", "mp4")
        job["output_dir"] = output_dir
        job["output_file"] = self._default_output_file(job["input_file"], output_dir, container)

    def _set_job_output_extension(self, job, container):
        """Passt die Dateiendung an, ohne benutzerdefinierte Dateinamen zu verlieren."""
        output_dir = job.get("output_dir") or os.path.dirname(job.get("output_file", ""))
        if not output_dir:
            output_dir = os.path.dirname(job["input_file"])

        current_name = os.path.basename(job.get("output_file", ""))
        root_name, _ = os.path.splitext(current_name)
        if not root_name:
            source_root, _ = os.path.splitext(os.path.basename(job["input_file"]))
            root_name = f"{source_root}_lme"

        job["output_dir"] = output_dir
        job["output_file"] = os.path.join(output_dir, f"{root_name}.{container}")

    @staticmethod
    def _job_is_busy(job):
        """True, solange der Job verarbeitet wird — Encode ("Codiert...") ebenso
        wie die KI-Phasen ("Audio extrahieren...", "KI-Transkription...", ...).
        Alle Laufzeit-Status enden per Konvention auf '...'."""
        return str((job or {}).get("status", "")).endswith("...")

    def _editable_job_indexes(self):
        """Alle Jobs, deren Settings aktuell geaendert werden duerfen."""
        return [
            idx for idx, job in enumerate(self.jobs)
            if not self._job_is_busy(job)
        ]

    def _sync_format_and_preset_options(self, image_input):
        """Befüllt Format- und Vorgaben-Dropdown passend zum Quelltyp des Jobs.
        Bildformate sind nur für Bild-Quellen sichtbar, Video-Formate nur für
        Video-/Audio-Quellen. Signale muss der Aufrufer geblockt haben."""
        image_input = bool(image_input)
        if getattr(self, "_format_options_are_image", None) == image_input:
            return
        self._format_options_are_image = image_input
        self.combo_format.clear()
        self.combo_format.addItems(presets.get_format_options(image_input))
        self.combo_preset.clear()
        self.combo_preset.addItems(presets.get_preset_dropdown_options(image_input))

    def _load_job_settings_to_ui(self, job):
        """Lädt die Job-Einstellungen in die Formularwidgets."""
        self._block_combobox_signals(True)

        # Dropdown-Inhalte an den Quelltyp anpassen (Bild vs. Video/Audio)
        self._sync_format_and_preset_options(presets.is_image_input(job["input_file"]))

        settings = job["settings"]
        container = settings.get("container", "mp4").lower()
        vcodec = settings.get("video_codec", "libx264").lower()
        acodec = settings.get("audio_codec", "aac").lower()
        preset_name_for_settings = presets.get_preset_for_settings(settings)
        stored_label = str(settings.get("preset_label") or "").strip()

        # Ausgabepfad Link setzen
        self.lbl_output_link.setText(os.path.basename(job["output_file"]))
        self.lbl_output_link.setToolTip(job["output_file"])

        # Format Dropdown setzen (zentrales Mapping in presets)
        self.combo_format.setCurrentText(presets.format_option_for_settings(settings))

        # Checkboxen
        self.chk_export_video.setChecked(vcodec != "none")
        self.chk_export_audio.setChecked(acodec != "none")
        self.settings_tabs.setTabEnabled(0, vcodec != "none")
        self.settings_tabs.setTabEnabled(1, acodec != "none")

        custom_mode = bool(settings.get("custom_mode"))
        if (not custom_mode and not stored_label
                and preset_name_for_settings == "Benutzerdefiniert"
                and not (vcodec == "copy" and acodec == "copy")):
            custom_mode = True
        settings["custom_mode"] = custom_mode

        if custom_mode:
            self.combo_preset.setCurrentText("Benutzerdefiniert")
        elif stored_label and self.combo_preset.findText(stored_label) != -1:
            # Beim Auswählen gespeichertes Label (z. B. Quick-Preset "YouTube
            # 1080p HD") wieder anzeigen statt "Benutzerdefiniert".
            self.combo_preset.setCurrentText(stored_label)
        elif preset_name_for_settings != "Benutzerdefiniert":
            self.combo_preset.setCurrentText(preset_name_for_settings)
        elif vcodec == "copy" and acodec == "copy":
            self.combo_preset.setCurrentText("Stream-Kopie (Verlustfrei)")
        else:
            self.combo_preset.setCurrentText("Benutzerdefiniert")

        # Sync Video Codec Box
        self._sync_video_codec_combobox(container, custom_mode)
        self.combo_vcodec.setCurrentText(vcodec)

        # Skalierungsmodus / Breite / Höhe / FPS / Profil laden
        self.combo_scale_mode.setCurrentText(
            presets.scale_mode_to_label(presets.get_scale_mode(settings))
        )
        self.spin_width.setValue(int(settings.get("width", 1920)))
        self.spin_height.setValue(int(settings.get("height", 1080)))
        fps_setting = str(settings.get("fps", "") or "").strip()
        self.combo_fps.setCurrentText(fps_setting if fps_setting else presets.FPS_SOURCE_LABEL)
        self.combo_profile.setCurrentText(str(settings.get("profile", "High")))
        
        # Sync Audio Codec Box
        self._sync_audio_codec_combobox(container, custom_mode)
        
        # Bitrate / CRF / Bildqualität belegen
        crf = settings.get("crf", "")
        vbitrate = settings.get("video_bitrate", "")
        mode = settings.get("encoding_mode", "")

        if container in presets.IMAGE_CONTAINERS:
            quality = int(settings.get("image_quality", 90) or 90)
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
            self.slider_bitrate.setRange(1, 2000)
            num_val = presets.bitrate_to_mbps(vbitrate, 8.0) if vbitrate else 8.0
            self._configure_bitrate_spin(num_val)
            self.spin_bitrate_val.setValue(num_val)
            self.slider_bitrate.setValue(int(num_val * 10))
                
        # Audio Codec und Bitrate setzen
        self.combo_audiocodec.setCurrentText(presets.audio_codec_to_label(acodec))
            
        self.combo_audiobitrate.setCurrentText(settings.get("audio_bitrate", "192k"))

        # Subtitle Tab laden
        self.combo_sub_source.setCurrentText(settings.get("subtitles_source", "Automatisch erkennen"))
        self.edit_sub_source_custom.setText(settings.get("subtitles_source_custom", ""))
        self.combo_sub_translate.setCurrentText(settings.get("subtitles_translate", "Keine (Originalsprache)"))
        self.edit_sub_translate_custom.setText(settings.get("subtitles_translate_custom", ""))
        self.chk_subtitles.setChecked(bool(settings.get("subtitles_enabled", False)))
        self.edit_sub_file_path.setText(settings.get("subtitles_file_path", ""))
        self.combo_sub_mode.setCurrentText(settings.get("subtitles_mode", "Soft-Untertitel (in Container einbetten)"))
        # Sichtbarkeit der "Andere..."-Felder direkt setzen — die Handler würden
        # mitten im Laden speichern und den Fokus stehlen.
        self.edit_sub_source_custom.setVisible(self.combo_sub_source.currentText() == "Andere...")
        self.edit_sub_translate_custom.setVisible(self.combo_sub_translate.currentText() == "Andere...")
        
        self._update_widget_visibilities()
        self._update_summary(job)
        
        self._block_combobox_signals(False)
        self._update_command_preview(job)

    def _sync_audio_codec_combobox(self, container, custom=False):
        """Aktualisiert die Audio-Codec-Auswahlliste."""
        current_codec = presets.audio_label_to_codec(self.combo_audiocodec.currentText())
        prev_blocked = self.combo_audiocodec.blockSignals(True)
        self.combo_audiocodec.clear()
        self.combo_audiocodec.addItems(presets.get_audio_codec_labels(container, custom))
        if current_codec:
            self.combo_audiocodec.setCurrentText(presets.audio_codec_to_label(current_codec))
        self.combo_audiocodec.blockSignals(prev_blocked)

    def _update_widget_visibilities(self):
        """Passt die Aktivität von Widgets an die aktuelle Codec-Auswahl an."""
        container = self._current_container()
        is_image = container in presets.IMAGE_CONTAINERS
        is_audio_only = container in presets.AUDIO_ONLY_CONTAINERS

        if is_image:
            self.chk_export_video.blockSignals(True)
            self.chk_export_audio.blockSignals(True)
            self.chk_export_video.setChecked(True)
            self.chk_export_audio.setChecked(False)
            self.chk_export_video.blockSignals(False)
            self.chk_export_audio.blockSignals(False)

        self._apply_media_ui_mode(is_image)

        v_active = self.chk_export_video.isChecked()
        a_active = self.chk_export_audio.isChecked()
        self.settings_tabs.setTabEnabled(0, v_active)
        self.settings_tabs.setTabEnabled(1, a_active and not is_image)

        vcodec = self.combo_vcodec.currentText().lower()
        acodec = presets.audio_label_to_codec(self.combo_audiocodec.currentText()).lower()

        # Detail-Sperren bei Video-Kopie oder Deaktivierung
        video_editable = v_active and vcodec != "copy" and vcodec != "none"
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
        audio_editable = a_active and acodec not in ("copy", "none")
        lossless_audio = acodec in ("flac", "alac", "pcm_s16le", "pcm_s24le", "wavpack")
        self.combo_audiobitrate.setEnabled(audio_editable and not lossless_audio)

        # Detail-Sperren bei Untertiteln (für Bilder komplett gesperrt)
        self.settings_tabs.setTabEnabled(2, not is_image)
        self.chk_subtitles.setEnabled(not is_image)
        sub_active = self.chk_subtitles.isChecked() and not is_image
        self.edit_sub_file_path.setEnabled(sub_active)
        self.btn_browse_sub_file.setEnabled(sub_active)
        self.combo_sub_mode.setEnabled(sub_active)

    def _update_summary(self, job):
        """Baut den Zusammenfassungstext."""
        settings = job["settings"]
        in_file = os.path.basename(job["input_file"])
        vcodec = settings.get("video_codec", "libx264")
        acodec = settings.get("audio_codec", "aac")
        crf = settings.get("crf", "")
        v_bitrate = settings.get("video_bitrate", "")
        a_bitrate = settings.get("audio_bitrate", "")
        scale_mode = presets.get_scale_mode(settings)
        keep_source_size = scale_mode == presets.SCALE_MODE_SOURCE
        scale_note = str(tr(" (verzerrt)")) if scale_mode == presets.SCALE_MODE_STRETCH else ""

        rate_mode = "CBR" if settings.get("encoding_mode") == "cbr" else "VBR"

        is_image = str(settings.get("container", "")).lower() in presets.IMAGE_CONTAINERS
        if is_image:
            size_info = str(tr("Quelle beibehalten")) if keep_source_size else f"{self.spin_width.value()}x{self.spin_height.value()}{scale_note}"
            crop = presets.get_crop(settings)
            if crop:
                size_info = str(tr(
                    "Zuschnitt {width}x{height}, {size}",
                    width=crop["w"], height=crop["h"], size=size_info,
                ))
            rotate = presets.get_rotation(settings)
            if rotate:
                size_info = str(tr(
                    "{size}, gedreht {angle}°", size=size_info, angle=rotate
                ))
            quality = settings.get("image_quality", 90)
            quality_info = str(tr("verlustfrei")) if vcodec == "png" else str(tr(
                "Qualität {quality} %", quality=quality
            ))
            v_sum = str(tr(
                "Bild: {format}, {size}, {quality}",
                format=presets.format_label(settings), size=size_info,
                quality=quality_info,
            ))
        elif vcodec == "none":
            v_sum = str(tr("Kein Video"))
        elif vcodec == "copy":
            v_sum = str(tr("Video: Kopieren (Stream Copy)"))
        elif keep_source_size:
            v_encoding = f"CRF {crf}" if crf else f"{rate_mode} {v_bitrate}"
            v_sum = str(tr(
                "Video: {codec}, Quelle beibehalten, {encoding}",
                codec=vcodec, encoding=v_encoding,
            ))
        else:
            v_encoding = f"CRF {crf}" if crf else f"{rate_mode} {v_bitrate}"
            v_sum = str(tr(
                "Video: {codec}, {width}x{height}{scale_note} ({fps} fps), {encoding}",
                codec=vcodec, width=self.spin_width.value(),
                height=self.spin_height.value(), scale_note=scale_note,
                fps=self.combo_fps.currentText(), encoding=v_encoding,
            ))
            
        if acodec == "none":
            a_sum = str(tr("Kein Audio"))
        elif acodec == "copy":
            a_sum = str(tr("Audio: Kopieren (Stream Copy)"))
        else:
            a_sum = str(tr("Audio: {codec}, {bitrate}", codec=acodec, bitrate=a_bitrate))
            
        summary = tr(
            "<b>Quelle:</b> {input}<br><b>Ausgabe:</b> {output}<br>{video}",
            input=in_file, output=os.path.basename(job["output_file"]),
            video=v_sum,
        )
        if not is_image:
            summary = LocalizedString(
                str(summary) + f"<br>{a_sum}", summary.source_text
            )
        self.summary_box.setText(summary)

    def _update_command_preview(self, job):
        """Generiert die FFmpeg-Befehlszeile für die Live-Vorschau."""
        args = presets.get_ffmpeg_args(job["input_file"], job["output_file"], job["settings"])
        preview_cmd = "ffmpeg " + " ".join([f'"{a}"' if " " in a or "/" in a else a for a in args])
        self.edit_cmd_preview.setText(preview_cmd)

    def _save_ui_settings_to_job(self):
        """Speichert die Formularinhalte zurück in das selektierte Job-Objekt."""
        selected_row = self.queue_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.jobs):
            return
            
        job = self.jobs[selected_row]
        if self._job_is_busy(job):
            return
            
        settings = job["settings"]
        old_container = settings.get("container", "mp4")
        
        # Format / Container
        fmt_text = self.combo_format.currentText()
        settings["container"] = self._get_container_from_format_text(fmt_text)
        settings["custom_mode"] = self.combo_preset.currentText() == "Benutzerdefiniert"
        
        # Video exportieren Checkbox auswerten
        if not self.chk_export_video.isChecked():
            settings["video_codec"] = "none"
        else:
            settings["video_codec"] = self.combo_vcodec.currentText()
                
        # Audio exportieren Checkbox auswerten
        if not self.chk_export_audio.isChecked():
            settings["audio_codec"] = "none"
        else:
            settings["audio_codec"] = presets.audio_label_to_codec(self.combo_audiocodec.currentText())

        # Skalierungsmodus (gilt für Video- und Bild-Export)
        scale_mode = presets.scale_mode_from_label(self.combo_scale_mode.currentText())
        settings["scale_mode"] = scale_mode
        settings["match_source"] = (scale_mode == presets.SCALE_MODE_SOURCE)

        vcodec = str(settings.get("video_codec", "")).lower()
        if settings["container"] in presets.IMAGE_CONTAINERS:
            # Bild-Export: Qualitätsregler statt Bitrate/CRF
            settings["width"] = self.spin_width.value()
            settings["height"] = self.spin_height.value()
            settings["image_quality"] = int(self.spin_bitrate_val.value())
            settings["encoding_mode"] = "image"
            settings["crf"] = ""
            settings["video_bitrate"] = ""
        elif vcodec in ("copy", "none"):
            settings["encoding_mode"] = vcodec
            settings["crf"] = ""
            settings["video_bitrate"] = ""
        else:
            # Breite / Höhe / FPS / Profil speichern
            settings["width"] = self.spin_width.value()
            settings["height"] = self.spin_height.value()
            fps_text = self.combo_fps.currentText().strip()
            settings["fps"] = "" if fps_text.casefold() == presets.FPS_SOURCE_LABEL.casefold() else fps_text
            settings["profile"] = self.combo_profile.currentText()

            # Bitrate / CRF
            enc = self.combo_encoding.currentText()
            if enc == "CRF (Qualitätsbasiert)":
                settings["encoding_mode"] = "crf"
                # %g erhält halbe CRF-Stufen (23.5), ohne "23.0" zu erzeugen
                settings["crf"] = f"{self.spin_bitrate_val.value():g}"
                settings["video_bitrate"] = ""
            else:
                settings["encoding_mode"] = "cbr" if enc == "CBR" else "vbr"
                settings["crf"] = ""
                settings["video_bitrate"] = presets.format_mbps(self.spin_bitrate_val.value())
            
        settings["audio_bitrate"] = self.combo_audiobitrate.currentText()
        
        # Subtitles Settings
        settings["subtitles_source"] = self.combo_sub_source.currentText()
        settings["subtitles_source_custom"] = self.edit_sub_source_custom.text()
        settings["subtitles_translate"] = self.combo_sub_translate.currentText()
        settings["subtitles_translate_custom"] = self.edit_sub_translate_custom.text()
        settings["subtitles_enabled"] = self.chk_subtitles.isChecked()
        settings["subtitles_file_path"] = self.edit_sub_file_path.text()
        settings["subtitles_mode"] = self.combo_sub_mode.currentText()
        
        # Ausgabename nur bei Containerwechsel anpassen. Audio-/Codec-Aenderungen
        # duerfen keinen manuell gesetzten Ausgabeordner oder Dateinamen ueberschreiben.
        new_ext = settings["container"]
        current_ext = os.path.splitext(job["output_file"])[1].lstrip(".").lower()
        if old_container != new_ext or current_ext != new_ext.lower():
            self._set_job_output_extension(job, new_ext)
        self.lbl_output_link.setText(os.path.basename(job["output_file"]))
        self.lbl_output_link.setToolTip(job["output_file"])
        
        self._update_table_row(selected_row)
        self._update_summary(job)
        self._update_command_preview(job)

    # --- EVENTS & LISTENERS ---
    def _on_job_selection_changed(self):
        """Wird ausgelöst, wenn ein anderer Job in der Warteschlange selektiert wird."""
        selected_row = self.queue_table.currentRow()
        if selected_row >= 0 and selected_row < len(self.jobs):
            job = self.jobs[selected_row]
            self._load_job_settings_to_ui(job)
            self._update_left_mode_for_job(job)

            # Einstellungs-Panel aktivieren/deaktivieren abhängig davon, ob Job läuft
            is_job_running = self._job_is_busy(job)
            self.settings_widget.setEnabled(not is_job_running)
        else:
            # Kein Job ausgewählt: Panel sperren, sonst können Format/Vorgabe
            # geändert werden ohne dass die abhängigen Felder (Codec etc.)
            # synchronisiert werden – die Handler brechen mangels Job früh ab.
            self.settings_widget.setEnabled(False)
            self.edit_cmd_preview.clear()
            self._image_preview_pixmap = QPixmap()
            self._image_preview_rotation = 0
            self._show_queue_view()

    def _on_scale_mode_changed(self, text):
        """Skalierungsmodus geändert: Größenfelder freigeben und Job speichern."""
        self._sync_size_spins_to_aspect("width")
        self._update_widget_visibilities()
        self._save_ui_settings_to_job()

    def _get_job_source_size(self, job):
        """Pixelmaße der Quelldatei aus dem asynchronen Prefetch-Cache oder None.
        Blockiert nie den UI-Thread — falls der Prefetch noch läuft, greift die
        Seitenverhältnis-Kopplung einfach erst bei der nächsten Änderung."""
        if not job:
            return None
        if "source_size" not in job:
            self._prefetch_source_info(job)
            return None
        return job["source_size"] or None

    def _prefetch_source_info(self, job):
        """Ermittelt Quellmaße und -dauer asynchron via ffprobe (kein UI-Freeze,
        z. B. bei Netzlaufwerken) und cacht sie am Job.

        Bewusst ein Daemon-Thread mit subprocess statt QProcess: ein noch
        laufender QProcess bricht in Qt 6 beim Zerstören des Elternobjekts
        die ganze Anwendung mit qFatal ab."""
        if not job or "source_size" in job or job.get("_probe_running"):
            return

        settings = job.get("settings", {})
        if settings.get("input_args") or settings.get("disc_type"):
            w = settings.get("source_width")
            h = settings.get("source_height")
            if w and h:
                job["source_size"] = (int(w), int(h))
            else:
                job["source_size"] = None
            job["source_duration"] = float(settings.get("source_duration") or 0.0)
            return

        path = job.get("input_file", "")
        if not path or not os.path.exists(path):
            job["source_size"] = None
            job["source_duration"] = 0.0
            return
        job["_probe_running"] = True

        def work():
            import subprocess
            size = None
            duration = 0.0
            try:
                r = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height:format=duration",
                     "-print_format", "json", path],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
                )
                if r.returncode == 0:
                    data = json.loads(r.stdout)
                    streams = data.get("streams") or []
                    if streams:
                        w = int(streams[0].get("width") or 0)
                        h = int(streams[0].get("height") or 0)
                        if w > 0 and h > 0:
                            size = (w, h)
                    duration = float(data.get("format", {}).get("duration") or 0.0)
            except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
                pass
            # Nur einfache dict-Schreibzugriffe (GIL-sicher), keine Qt-Aufrufe
            job["source_size"] = size
            job["source_duration"] = duration
            job.pop("_probe_running", None)

        import threading
        threading.Thread(target=work, daemon=True, name="lme-ffprobe").start()

    def _effective_aspect_source(self):
        """Maßgebliche Quellmaße für die Seitenverhältnis-Kopplung des selektierten
        Jobs. Ein gesetzter Zuschnitt bestimmt das Seitenverhältnis, sonst die
        (ggf. um 90°/270° gedrehte) Quelle."""
        selected_row = self.queue_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.jobs):
            return None
        job = self.jobs[selected_row]
        crop = presets.get_crop(job.get("settings", {}))
        if crop:
            # Der Zuschnitt bezieht sich bereits auf das gedrehte Bild, kein
            # weiteres Vertauschen nötig.
            return crop["w"], crop["h"]
        dims = self._get_job_source_size(job)
        if not dims:
            return None
        if presets.get_rotation(job.get("settings", {})) in (90, 270):
            return dims[1], dims[0]
        return dims

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

    def _on_spin_width_changed(self, _value):
        """Breite manuell geändert: Höhe ggf. mitziehen, dann speichern."""
        self._sync_size_spins_to_aspect("width")
        self._save_ui_settings_to_job()

    def _on_spin_height_changed(self, _value):
        """Höhe manuell geändert: Breite ggf. mitziehen, dann speichern."""
        self._sync_size_spins_to_aspect("height")
        self._save_ui_settings_to_job()

    def _on_format_changed(self, text):
        """Format-Dropdown-Handler. Aktualisiert das Job-Objekt mit Standardeinstellungen für das Format."""
        selected_row = self.queue_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.jobs):
            return
        job = self.jobs[selected_row]

        # Vom Benutzer gewählte Auflösung/FPS/Profil über den Format-Wechsel hinweg behalten.
        prev = job.get("settings", {}) or {}
        custom_mode = self.combo_preset.currentText() == "Benutzerdefiniert" or bool(prev.get("custom_mode"))
        keep = {
            "width": prev.get("width", 1920),
            "height": prev.get("height", 1080),
            "fps": prev.get("fps", "25"),
            "scale_mode": prev.get("scale_mode", ""),
        }
        keep_crop = presets.get_crop(prev)
        keep_rotate = presets.get_rotation(prev)
        # Untertitel-/Schnitt-Konfiguration überlebt den Wechsel — die
        # Format-Zweige unten ersetzen das settings-Dict komplett.
        keep_subs = {k: prev[k] for k in presets.SUBTITLE_SETTING_KEYS if k in prev}
        keep_trim = {k: prev[k] for k in ("trim_start", "trim_end") if k in prev}

        # Standardeinstellungen basierend auf Format zuweisen (zentrales Mapping)
        defaults = presets.default_settings_for_format(text)
        if custom_mode:
            if "settings" not in job or not isinstance(job["settings"], dict):
                job["settings"] = {}
            job["settings"]["container"] = presets.container_from_format_text(text)
            job["settings"]["custom_mode"] = True
            for key, value in (
                ("video_codec", "libx264"), ("audio_codec", "aac"),
                ("video_bitrate", "8M"), ("audio_bitrate", "192k"),
                ("crf", ""), ("width", 1920), ("height", 1080),
                ("fps", "25"), ("profile", "High"),
            ):
                job["settings"].setdefault(key, value)
        elif defaults is not None:
            job["settings"] = defaults
        else:
            container = presets.container_from_format_text(text)
            if "settings" not in job or not isinstance(job["settings"], dict):
                job["settings"] = {}
            job["settings"]["container"] = container
            for key, value in (
                ("video_codec", "libx264"), ("audio_codec", "aac"),
                ("width", 1920), ("height", 1080),
                ("fps", "25"), ("profile", "High"),
            ):
                job["settings"].setdefault(key, value)

        if not custom_mode:
            job["settings"]["custom_mode"] = False

        # Vorherige Auflösung/FPS für Video-Formate wiederherstellen (kein Reset
        # auf 1080p). Bildformate behalten "Quelle beibehalten" aus dem Preset.
        if (job["settings"].get("video_codec") != "none"
                and job["settings"].get("container") not in presets.IMAGE_CONTAINERS):
            job["settings"]["width"] = keep["width"]
            job["settings"]["height"] = keep["height"]
            job["settings"]["fps"] = keep["fps"]
            if keep["scale_mode"]:
                job["settings"]["scale_mode"] = keep["scale_mode"]
                job["settings"]["match_source"] = keep["scale_mode"] == presets.SCALE_MODE_SOURCE

        # Zuschnitt/Drehung sind quellbezogen und überleben den Format-Wechsel bei Bild-Jobs
        if job["settings"].get("container") in presets.IMAGE_CONTAINERS:
            if keep_crop:
                job["settings"]["crop"] = keep_crop
            if keep_rotate:
                job["settings"]["rotate"] = keep_rotate

        # Untertitel-/Schnitt-Einstellungen wiederherstellen (für Bildformate irrelevant)
        if job["settings"].get("container") not in presets.IMAGE_CONTAINERS:
            if keep_subs:
                job["settings"].update(keep_subs)
            if keep_trim:
                job["settings"].update(keep_trim)

        # UI neu laden aus dem aktualisierten Job (dies blockiert Signale automatisch)
        self._load_job_settings_to_ui(job)
        self._save_ui_settings_to_job()

    def _on_preset_changed(self, text):
        """Preset-Dropdown-Handler."""
        selected_row = self.queue_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.jobs):
            return
        job = self.jobs[selected_row]

        # Gewähltes Preset-Label merken, damit Quick-Presets ("YouTube 1080p
        # HD") nach dem Neuladen nicht als "Benutzerdefiniert" erscheinen.
        if text == "Benutzerdefiniert":
            job["settings"].pop("preset_label", None)
        else:
            job["settings"]["preset_label"] = text

        if text == "Benutzerdefiniert":
            job["settings"]["custom_mode"] = True
            mode = presets.scale_mode_from_label(self.combo_scale_mode.currentText())
            job["settings"]["scale_mode"] = mode
            job["settings"]["match_source"] = (mode == presets.SCALE_MODE_SOURCE)
            container = job["settings"].get("container", "mp4")
            current_vcodec = self.combo_vcodec.currentText() or job["settings"].get("video_codec", "libx264")
            current_acodec = presets.audio_label_to_codec(
                self.combo_audiocodec.currentText() or job["settings"].get("audio_codec", "aac")
            )
            self._sync_video_codec_combobox(container, custom=True)
            self.combo_vcodec.setCurrentText(current_vcodec)
            self._sync_audio_codec_combobox(container, custom=True)
            self.combo_audiocodec.setCurrentText(presets.audio_codec_to_label(current_acodec))
            self._update_widget_visibilities()
            self._save_ui_settings_to_job()
            return

        if text in presets.PRESETS:
            prev = job.get("settings", {}) or {}
            keep_crop = presets.get_crop(prev)
            keep_rotate = presets.get_rotation(prev)
            keep_subs = {k: prev[k] for k in presets.SUBTITLE_SETTING_KEYS if k in prev}
            keep_trim = {k: prev[k] for k in ("trim_start", "trim_end") if k in prev}
            job["settings"] = dict(presets.PRESETS[text])
            job["settings"]["custom_mode"] = False
            job["settings"]["preset_label"] = text
            if job["settings"].get("container") in presets.IMAGE_CONTAINERS:
                if keep_crop:
                    job["settings"]["crop"] = keep_crop
                if keep_rotate:
                    job["settings"]["rotate"] = keep_rotate
            # Untertitel-/Schnitt-Konfiguration überlebt den Preset-Wechsel
            if job["settings"].get("container") not in presets.IMAGE_CONTAINERS:
                if keep_subs:
                    job["settings"].update(keep_subs)
                if keep_trim:
                    job["settings"].update(keep_trim)
            self._load_job_settings_to_ui(job)
            self._save_ui_settings_to_job()
            return

        quick_settings = presets.quick_preset_settings(text)
        if quick_settings is not None:
            prev = job.get("settings", {}) or {}
            keep_subs = {k: prev[k] for k in presets.SUBTITLE_SETTING_KEYS if k in prev}
            keep_trim = {k: prev[k] for k in ("trim_start", "trim_end") if k in prev}
            job["settings"] = dict(quick_settings)
            job["settings"]["custom_mode"] = False
            job["settings"]["preset_label"] = text
            if job["settings"].get("container") not in presets.IMAGE_CONTAINERS:
                if keep_subs:
                    job["settings"].update(keep_subs)
                if keep_trim:
                    job["settings"].update(keep_trim)
            self._load_job_settings_to_ui(job)
            self._save_ui_settings_to_job()
            return

    def _on_encoding_method_changed(self, text):
        """Synchronisiert Codierungs-Methode und regelt Slider-Skalierung."""
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
        else:
            self.lbl_bitrate_val.setText("Zielbitrate (Mbps):")
            self._configure_bitrate_spin()
            self.spin_bitrate_val.setValue(8.0)
            
            self.slider_bitrate.setRange(1, 2000)
            self.slider_bitrate.setValue(80)
            
        self.slider_bitrate.blockSignals(False)
        self.spin_bitrate_val.blockSignals(False)
        self._save_ui_settings_to_job()

    def _on_vcodec_changed(self, text):
        self._update_widget_visibilities()
        self._save_ui_settings_to_job()

    def _on_audio_codec_changed(self, text):
        self._update_widget_visibilities()
        self._save_ui_settings_to_job()

    def _on_export_video_toggled(self, state):
        self._update_widget_visibilities()
        self._save_ui_settings_to_job()

    def _on_export_audio_toggled(self, state):
        self._update_widget_visibilities()
        self._save_ui_settings_to_job()

    def _on_subtitles_toggled(self, state):
        self._update_widget_visibilities()
        self._save_ui_settings_to_job()

    def _on_sub_source_changed(self, text):
        show_custom = (text == "Andere...")
        self.edit_sub_source_custom.setVisible(show_custom)
        if show_custom:
            self.edit_sub_source_custom.setFocus()
        self._save_ui_settings_to_job()

    def _on_sub_translate_changed(self, text):
        show_custom = (text == "Andere...")
        self.edit_sub_translate_custom.setVisible(show_custom)
        if show_custom:
            self.edit_sub_translate_custom.setFocus()
        self._save_ui_settings_to_job()

    def _on_browse_sub_file_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Untertiteldatei auswählen", "", "SubRip Untertitel (*.srt)"
        )
        if file_path:
            self.edit_sub_file_path.setText(file_path)
            self._save_ui_settings_to_job()

    def _on_transcribe_clicked(self):
        selected_row = self.queue_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.jobs):
            QMessageBox.warning(self, "Kein Job ausgewählt", "Bitte wählen Sie zuerst einen Job aus der Warteschlange aus.")
            return
            
        job = self.jobs[selected_row]
        
        # Get languages
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
        dialog = SubtitleEditorDialog(job["input_file"], job["output_file"], src_lang, tr_lang, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            saved_path = dialog.get_saved_srt_path()
            if saved_path:
                self.edit_sub_file_path.setText(saved_path)
                self.chk_subtitles.setChecked(True)
                self._save_ui_settings_to_job()

    def _configure_bitrate_spin(self, value=None):
        """Erlaubt bei Bedarf präzise Bitraten unterhalb von 0,1 Mbps."""
        low_bitrate = value is not None and 0 < float(value) < 0.1
        self.spin_bitrate_val.setDecimals(3 if low_bitrate else 1)
        self.spin_bitrate_val.setRange(0.001 if low_bitrate else 0.1, 200.0)
        self.spin_bitrate_val.setSingleStep(0.001 if low_bitrate else 0.5)

    def _on_slider_bitrate_changed(self, value):
        """Schieberegler synchronisiert das Eingabefeld."""
        self.spin_bitrate_val.blockSignals(True)
        if self._current_container_is_image() or self.combo_encoding.currentText() == "CRF (Qualitätsbasiert)":
            self.spin_bitrate_val.setValue(value)
        else:
            self.spin_bitrate_val.setValue(value / 10.0)
        self.spin_bitrate_val.blockSignals(False)
        self._save_ui_settings_to_job()

    def _on_spin_bitrate_changed(self, value):
        """Zahleneingabefeld synchronisiert den Schieberegler."""
        self.slider_bitrate.blockSignals(True)
        if self._current_container_is_image() or self.combo_encoding.currentText() == "CRF (Qualitätsbasiert)":
            self.slider_bitrate.setValue(int(value))
        else:
            self.slider_bitrate.setValue(int(value * 10))
        self.slider_bitrate.blockSignals(False)
        self._save_ui_settings_to_job()

    def _on_output_link_clicked(self, event):
        """Klick auf den blauen Ausgabenamen öffnet den Dateispeichern-Dialog."""
        self._choose_output_file_for_row(self.queue_table.currentRow())

    def _choose_output_file_for_row(self, row):
        """Öffnet den Speichern-Dialog für die Ausgabedatei eines Queue-Jobs."""
        if row < 0 or row >= len(self.jobs):
            return

        job = self.jobs[row]
        if self._job_is_busy(job):
            return

        ext = job["settings"].get("container", "mp4")
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Ausgabedatei festlegen", job["output_file"],
            tr("Format (*.{ext});;Alle Dateien (*)", ext=ext),
        )
        if file_path:
            job["output_file"] = file_path
            job["output_dir"] = os.path.dirname(file_path)
            if row == self.queue_table.currentRow():
                self.lbl_output_link.setText(os.path.basename(file_path))
                self.lbl_output_link.setToolTip(file_path)
                self._update_summary(job)
                self._update_command_preview(job)
            self._update_table_row(row)

            other_editable = [idx for idx in self._editable_job_indexes() if idx != row]
            if other_editable:
                reply = QMessageBox.question(
                    self,
                    "Ausgabeordner uebernehmen?",
                    "Diesen Ausgabeordner auch fuer alle anderen Jobs in der Warteschlange verwenden?\n\n"
                    "Die anderen Dateinamen werden automatisch aus den jeweiligen Quelldateien erzeugt.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._apply_output_dir_to_jobs(job["output_dir"], other_editable)

    def _apply_output_dir_to_jobs(self, output_dir, indexes):
        changed = 0
        for idx in indexes:
            if idx < 0 or idx >= len(self.jobs):
                continue
            job = self.jobs[idx]
            if self._job_is_busy(job):
                continue
            self._set_job_output_dir(job, output_dir)
            self._update_table_row(idx)
            changed += 1

        selected_row = self.queue_table.currentRow()
        if 0 <= selected_row < len(self.jobs):
            self._load_job_settings_to_ui(self.jobs[selected_row])
        self.statusBar().showMessage(tr(
            "Ausgabeordner auf {count} Job(s) angewendet.", count=changed
        ))

    def _on_apply_output_dir_to_all_clicked(self):
        """Setzt einen Ausgabeordner fuer alle Jobs in der Warteschlange."""
        if self.is_running or not self.jobs:
            return

        selected_row = self.queue_table.currentRow()
        current_dir = os.path.expanduser("~")
        if 0 <= selected_row < len(self.jobs):
            current_dir = self.jobs[selected_row].get("output_dir") or os.path.dirname(self.jobs[selected_row]["output_file"])

        output_dir = QFileDialog.getExistingDirectory(self, "Ausgabeordner fuer alle Jobs", current_dir)
        if not output_dir:
            return

        self._apply_output_dir_to_jobs(output_dir, self._editable_job_indexes())

    def _on_apply_settings_to_all_clicked(self):
        """Uebernimmt die aktuellen Video-/Audio-/Container-Settings fuer alle Jobs."""
        if self.is_running:
            return

        selected_row = self.queue_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.jobs):
            return

        self._save_ui_settings_to_job()
        source_job = self.jobs[selected_row]
        source_settings = dict(source_job["settings"])
        # Quellbezogene Settings (Zuschnitt, Schnittmarken) nicht mitkopieren
        for key in presets.SOURCE_SETTING_KEYS:
            source_settings.pop(key, None)
        # Laufzeit-Zwischenzustände (Temp-Pfade, KI-Stufen) gehören nur zum Quell-Job
        for key in presets.TRANSIENT_SETTING_KEYS:
            source_settings.pop(key, None)
        # Nur auf Jobs mit gleichem Quelltyp anwenden — Bild-Einstellungen
        # passen nicht auf Video-Quellen und umgekehrt.
        source_is_image = presets.is_image_input(source_job["input_file"])
        target_indexes = [
            idx for idx in self._editable_job_indexes()
            if idx != selected_row
            and presets.is_image_input(self.jobs[idx]["input_file"]) == source_is_image
        ]
        if not target_indexes:
            self.statusBar().showMessage(tr(
                "Keine passenden Jobs (gleicher Quelltyp) in der Warteschlange."
            ))
            return

        reply = QMessageBox.question(
            self,
            "Einstellungen auf alle anwenden?",
            "Aktuelle Format-, Video- und Audio-Einstellungen auf alle anderen Jobs in der Warteschlange anwenden?\n\n"
            "Ausgabeordner bleiben erhalten; Dateiendungen werden an den Ziel-Container angepasst.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for idx in target_indexes:
            job = self.jobs[idx]
            job["settings"] = dict(source_settings)
            self._set_job_output_extension(job, source_settings.get("container", "mp4"))
            self._update_table_row(idx)

        self._load_job_settings_to_ui(source_job)
        self.statusBar().showMessage(tr(
            "Einstellungen auf {count} Job(s) angewendet.",
            count=len(target_indexes),
        ))

    # --- BUTTONS & CONTROLS ---
    def _on_add_files_clicked(self):
        """Erlaubt das Auswählen von Mediendateien via FileDialog."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Mediendatei(en) hinzufügen", "",
            "Medien (*.mp4 *.mkv *.avi *.mov *.mp3 *.wav *.flac *.webm *.ogg *.m4v "
            "*.png *.jpg *.jpeg *.webp *.avif *.bmp *.tif *.tiff *.gif *.heic *.heif *.jxl);;"
            "Videos & Audio (*.mp4 *.mkv *.avi *.mov *.mp3 *.wav *.flac *.webm *.ogg *.m4v);;"
            "Bilder (*.png *.jpg *.jpeg *.webp *.avif *.bmp *.tif *.tiff *.gif *.heic *.heif *.jxl);;"
            "Alle Dateien (*)"
        )
        for path in file_paths:
            self._add_file_to_queue(path)

    def _on_rip_disc_clicked(self, initial_source=None):
        """Öffnet den CD/DVD/BD-Ripper-Dialog."""
        from disc_ripper_dialog import DiscRipperDialog
        dlg = DiscRipperDialog(initial_source=initial_source, parent=self)
        dlg.jobs_queued.connect(self._on_disc_jobs_queued)
        dlg.exec()

    def _on_disc_jobs_queued(self, jobs_list):
        """Fügt vom DiscRipper übergebene Jobs in die Warteschlange ein."""
        if not jobs_list:
            return
        for job in jobs_list:
            self.jobs.append(job)
            self._insert_job_into_table(job)
            self._prefetch_source_info(job)
        self.queue_table.selectRow(len(self.jobs) - 1)
        self._update_ui_state()

    def _on_trim_video_clicked(self):
        """Öffnet den Schnittbereich für den aktuell ausgewählten Video-Job."""
        row = self.queue_table.currentRow()
        if row < 0 or row >= len(self.jobs):
            QMessageBox.information(
                self, "Video verkürzen",
                "Bitte wählen Sie zuerst einen Video-Job in der Warteschlange aus."
            )
            return
        job = self.jobs[row]
        if presets.is_image_input(job.get("input_file")):
            QMessageBox.information(
                self, "Video verkürzen",
                "Die Verkürzung steht nur für Video- oder Audio-Jobs zur Verfügung."
            )
            return
        if self._job_is_busy(job):
            return
        self._open_export_settings_dialog_for_row(row)

    def _selected_job_rows(self):
        """Alle selektierten Zeilenindizes (aufsteigend)."""
        rows = sorted({index.row() for index in self.queue_table.selectionModel().selectedRows()})
        return [r for r in rows if 0 <= r < len(self.jobs)]

    def _on_remove_selected_clicked(self):
        """Entfernt die ausgewählten Jobs aus Tabelle und Warteschlange."""
        rows = self._selected_job_rows()
        if not rows:
            return

        busy = [r for r in rows if self._job_is_busy(self.jobs[r])]
        if busy:
            QMessageBox.warning(self, "Aktion gesperrt", "Laufende Codierungen können nicht gelöscht werden.")

        # Von hinten löschen, damit die Indizes stabil bleiben
        for row in sorted(set(rows) - set(busy), reverse=True):
            self.jobs.pop(row)
            self.queue_table.removeRow(row)
            if self.current_job_idx != -1 and row < self.current_job_idx:
                self.current_job_idx -= 1

        if not self.jobs:
            self._image_preview_pixmap = QPixmap()
            self._image_preview_rotation = 0
            self._show_queue_view()
        self._update_ui_state()

    # --- QUEUE-KONTEXTMENÜ ---
    def _rebuild_queue_table(self, select_row=None):
        """Baut die Tabelle komplett aus self.jobs neu auf (nach Umsortieren)."""
        self.queue_table.blockSignals(True)
        self.queue_table.setRowCount(0)
        for job in self.jobs:
            self._insert_job_into_table(job)
        self.queue_table.blockSignals(False)
        if select_row is not None and 0 <= select_row < len(self.jobs):
            self.queue_table.selectRow(select_row)

    def _on_queue_context_menu(self, pos):
        row = self.queue_table.rowAt(pos.y())
        if row < 0 or row >= len(self.jobs):
            return
        self.queue_table.selectRow(row)
        job = self.jobs[row]
        busy = self._job_is_busy(job)

        menu = QMenu(self)
        act_start = menu.addAction("Nur diesen Job starten")
        act_start.setEnabled(not self.is_running and not busy)
        act_duplicate = menu.addAction("Job duplizieren")
        act_duplicate.setEnabled(not self.is_running and not busy)
        act_trim = menu.addAction("Video verkürzen (Schnitt)...")
        act_trim.setEnabled(not busy and not presets.is_image_input(job.get("input_file")))
        menu.addSeparator()
        act_up = menu.addAction("Nach oben")
        act_up.setEnabled(not self.is_running and row > 0)
        act_down = menu.addAction("Nach unten")
        act_down.setEnabled(not self.is_running and row < len(self.jobs) - 1)
        menu.addSeparator()
        act_show = menu.addAction("Zieldatei im Dateimanager anzeigen")
        act_show.setEnabled(os.path.exists(job["output_file"]))
        act_errors = menu.addAction("Fehlerdetails anzeigen")
        act_errors.setEnabled(bool(job.get("error_tail")) and job["status"] == "Fehlgeschlagen")
        menu.addSeparator()
        act_remove = menu.addAction("Entfernen")
        act_remove.setEnabled(not self.is_running and not busy)

        chosen = menu.exec(self.queue_table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_start:
            self._start_single_job(row)
        elif chosen == act_duplicate:
            self._duplicate_job(row)
        elif chosen == act_trim:
            self._open_export_settings_dialog_for_row(row)
        elif chosen == act_up:
            self._move_job(row, -1)
        elif chosen == act_down:
            self._move_job(row, 1)
        elif chosen == act_show:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(job["output_file"])))
        elif chosen == act_errors:
            self._show_error_details(row)
        elif chosen == act_remove:
            self._on_remove_selected_clicked()

    def _duplicate_job(self, row):
        if row < 0 or row >= len(self.jobs):
            return
        source = self.jobs[row]
        new_job = {
            "input_file": source["input_file"],
            "output_dir": source["output_dir"],
            "output_file": source["output_file"],
            "settings": dict(source["settings"]),
            "status": "Bereit",
            "progress": 0.0,
            "speed": "0.0x",
            "time_remaining": "Bereit",
        }
        for key in presets.TRANSIENT_SETTING_KEYS:
            new_job["settings"].pop(key, None)
        if "source_size" in source:
            new_job["source_size"] = source["source_size"]
            new_job["source_duration"] = source.get("source_duration", 0.0)
        self.jobs.insert(row + 1, new_job)
        self._rebuild_queue_table(select_row=row + 1)
        self._update_ui_state()
        if self.current_job_idx != -1 and row + 1 <= self.current_job_idx:
            self.current_job_idx += 1
        self.statusBar().showMessage(tr(
            "Job dupliziert — Hinweis: gleiche Ausgabedatei, ggf. Zielnamen anpassen."
        ))

    def _move_job(self, row, delta):
        new_row = row + delta
        if self.is_running or not (0 <= row < len(self.jobs)) or not (0 <= new_row < len(self.jobs)):
            return
        self.jobs[row], self.jobs[new_row] = self.jobs[new_row], self.jobs[row]
        self._rebuild_queue_table(select_row=new_row)

    def _start_single_job(self, row):
        """Startet ausschließlich den angeklickten Job (Kontextmenü)."""
        if self.is_running or row < 0 or row >= len(self.jobs):
            return
        job = self.jobs[row]
        if self._job_is_busy(job):
            return
        job["status"] = "Bereit"
        self._update_table_row(row)

        if not self._confirm_overwrites([row]):
            return

        self._single_job_idx = row
        self._run_total = 1
        self._run_done = 0
        self.is_running = True
        self.console.append("[LME WARTSCHLANGE] Einzelner Job gestartet.")
        self._update_ui_state()
        self._process_next_job()

    def _on_clear_queue_clicked(self):
        """Leert die gesamte Tabelle."""
        if self.is_running:
            QMessageBox.warning(self, "Aktion gesperrt", "Bitte stoppe zuerst den Codierungs-Prozess.")
            return
            
        self.jobs.clear()
        self.queue_table.setRowCount(0)
        self.edit_cmd_preview.clear()
        self._image_preview_pixmap = QPixmap()
        self._image_preview_rotation = 0
        self._show_queue_view()
        self._update_ui_state()

    def _on_start_queue(self):
        """Startet die Warteschlangen-Verarbeitung."""
        if self.is_running:
            return
            
        ready_jobs = [j for j in self.jobs if j["status"] in ["Bereit", "Fehlgeschlagen", "Abgebrochen"]]
        if not ready_jobs:
            QMessageBox.information(self, "Warteschlange", "Keine bereiten Konvertierungs-Jobs in der Liste.")
            return

        # Fehlgeschlagene/abgebrochene Jobs für diesen Lauf erneut bereitstellen.
        # Während des Laufs gelten dann nur noch "Bereit"-Jobs als verarbeitbar –
        # sonst würde _process_next_job einen fehlgeschlagenen Job sofort wieder
        # auswählen und endlos neu starten.
        for idx, j in enumerate(self.jobs):
            if j["status"] in ("Fehlgeschlagen", "Abgebrochen"):
                j["status"] = "Bereit"
                self._update_table_row(idx)

        # Doppelte Ausgabedateien abfangen: der spätere Job würde das Ergebnis
        # des früheren wegen -y kommentarlos überschreiben.
        seen_outputs = {}
        for idx, j in enumerate(self.jobs):
            if j["status"] != "Bereit":
                continue
            key = os.path.normcase(os.path.normpath(os.path.abspath(j["output_file"])))
            if key in seen_outputs:
                j["status"] = "Fehlgeschlagen"
                self._update_table_row(idx)
                self.console.append(
                    f"[LME FEHLER] Doppelte Ausgabedatei: {os.path.basename(j['output_file'])} "
                    f"wird bereits von Job {seen_outputs[key] + 1} erzeugt – Job {idx + 1} übersprungen."
                )
            else:
                seen_outputs[key] = idx

        ready_rows = [idx for idx, j in enumerate(self.jobs) if j["status"] == "Bereit"]
        if not self._confirm_overwrites(ready_rows):
            return

        self._single_job_idx = None
        self._run_total = len(ready_rows)
        self._run_done = 0
        self.is_running = True
        self.console.append("[LME WARTSCHLANGE] Verarbeitung gestartet.")
        self._update_ui_state()
        self._process_next_job()

    def _confirm_overwrites(self, rows):
        """Warnt einmalig, wenn Zieldateien bereits auf der Platte existieren
        (FFmpeg läuft mit -y und würde sie kommentarlos überschreiben).
        Kollisionen mit Quelldateien blockt _start_current_ffmpeg_job separat."""
        existing = []
        for idx in rows:
            job = self.jobs[idx]
            out = job["output_file"]
            if os.path.exists(out):
                existing.append(out)
        if not existing:
            return True

        shown = "\n".join(os.path.basename(p) for p in existing[:6])
        if len(existing) > 6:
            shown += tr("\n… und {count} weitere", count=len(existing) - 6)
        reply = QMessageBox.question(
            self, "Vorhandene Dateien überschreiben?",
            tr(
                "{count} Zieldatei(en) existieren bereits und werden überschrieben:\n\n"
                "{files}\n\nFortfahren?",
                count=len(existing), files=shown,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def closeEvent(self, event):
        """Beendet laufende Prozesse sauber, bevor das Fenster schließt."""
        if self.is_running:
            reply = QMessageBox.question(
                self, "Konvertierung läuft",
                "Es läuft noch eine Konvertierung. Wirklich beenden und abbrechen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # WICHTIG: Queue-Flag VOR dem Beenden der Hilfsprozesse löschen. Deren
        # Kill feuert synchron 'finished'; die Handler würden bei is_running=True
        # noch einen neuen (dann verwaisten) FFmpeg-Encode starten.
        self.is_running = False

        # Untertitel-Hilfsprozesse beenden
        for attr in ("sub_process", "sub_ai_process"):
            proc = getattr(self, attr, None)
            if proc and proc.state() != QProcess.ProcessState.NotRunning:
                proc.kill()
                proc.waitForFinished(1000)

        # Laufenden FFmpeg-Worker stoppen (killt QProcess + wartet kurz)
        if self.active_worker:
            self.active_worker.stop()

        self._save_session_state()
        super().closeEvent(event)

    # --- SITZUNGS-PERSISTENZ (Queue, Geometrie, Splitter) ---
    _PERSISTED_JOB_KEYS = ("input_file", "output_dir", "output_file", "settings", "status")

    def enable_session_persistence(self):
        """Aktiviert Speichern/Wiederherstellen der Sitzung (nur echte App)."""
        self._session_persistence = True
        self._restore_session_state()

    def _save_session_state(self):
        """Speichert Queue, Fenstergeometrie und Splitter-Positionen."""
        if not getattr(self, "_session_persistence", False):
            return
        self.settings_store.setValue("geometry", self.saveGeometry())
        self.settings_store.setValue("main_splitter", self.main_splitter.saveState())
        self.settings_store.setValue("left_splitter", self.left_splitter.saveState())

        entries = []
        for job in self.jobs:
            settings = dict(job.get("settings") or {})
            for key in presets.TRANSIENT_SETTING_KEYS:
                settings.pop(key, None)
            status = job.get("status", "Bereit")
            # Laufzeit-Status ("Codiert...") überleben den Neustart nicht
            if str(status).endswith("..."):
                status = "Bereit"
            entries.append({
                "input_file": job.get("input_file", ""),
                "output_dir": job.get("output_dir", ""),
                "output_file": job.get("output_file", ""),
                "settings": settings,
                "status": status,
            })
        try:
            self.settings_store.setValue("queue_json", json.dumps(entries))
        except (TypeError, ValueError):
            pass

    def _restore_session_state(self):
        """Stellt Queue, Fenstergeometrie und Splitter der letzten Sitzung her."""
        geometry = self.settings_store.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        for key, splitter in (("main_splitter", self.main_splitter),
                              ("left_splitter", self.left_splitter)):
            state = self.settings_store.value(key)
            if state is not None:
                splitter.restoreState(state)

        raw = self.settings_store.value("queue_json", "")
        if not raw:
            return
        try:
            entries = json.loads(raw)
        except (TypeError, ValueError):
            return
        restored = 0
        for entry in entries if isinstance(entries, list) else []:
            input_file = str(entry.get("input_file", "") or "")
            if not input_file or (not os.path.exists(input_file) and not input_file.startswith("/dev/")):
                continue
            settings = entry.get("settings")
            if not isinstance(settings, dict):
                continue
            status = str(entry.get("status", "Bereit") or "Bereit")
            job = {
                "input_file": input_file,
                "output_dir": entry.get("output_dir") or os.path.dirname(input_file),
                "output_file": entry.get("output_file") or input_file,
                "settings": settings,
                "status": status,
                "progress": 100.0 if status == "Fertig" else 0.0,
                "speed": "0.0x",
                "time_remaining": "0s" if status == "Fertig" else "Bereit",
            }
            self.jobs.append(job)
            self._insert_job_into_table(job)
            self._prefetch_source_info(job)
            restored += 1
        if restored:
            self.queue_table.selectRow(0)
            self._update_ui_state()
            self.statusBar().showMessage(tr(
                "{count} Job(s) aus der letzten Sitzung wiederhergestellt.",
                count=restored,
            ))

    # --- BENACHRICHTIGUNG & ENERGIE-AKTION ---
    def _notify(self, title, body, folder=None):
        """Desktop-Benachrichtigung (DBus, Fallback notify-send, sonst still).
        Mit folder bekommt die Benachrichtigung einen "Ordner öffnen"-Button
        (nur über DBus möglich; der notify-send-Fallback bleibt ohne Aktion)."""
        try:
            from PyQt6.QtDBus import QDBusInterface
            iface = QDBusInterface(
                "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications",
            )
            if iface.isValid():
                actions = []
                if folder and self._connect_notification_actions():
                    actions = ["open-folder", tr("Ordner öffnen")]
                reply = iface.call(
                    "Notify", "Linux Media Encoder", 0, "linux-media-encoder",
                    title, body, actions, {}, 8000,
                )
                if reply.errorName() == "":
                    if actions:
                        try:
                            notify_id = int(reply.arguments()[0])
                            self._notify_folder_by_id[notify_id] = folder
                        except (IndexError, TypeError, ValueError):
                            pass
                    return
        except Exception:
            pass
        QProcess.startDetached("notify-send", ["-a", "Linux Media Encoder", title, body])

    def _connect_notification_actions(self):
        """Lauscht (einmalig) auf ActionInvoked des Notification-Daemons."""
        if getattr(self, "_notify_signal_connected", None) is not None:
            return self._notify_signal_connected
        self._notify_folder_by_id = {}
        try:
            from PyQt6.QtDBus import QDBusConnection
            self._notify_signal_connected = bool(QDBusConnection.sessionBus().connect(
                "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications", "ActionInvoked",
                self._on_notification_action,
            ))
        except Exception:
            self._notify_signal_connected = False
        return self._notify_signal_connected

    @pyqtSlot(int, str)
    def _on_notification_action(self, notification_id, action_key):
        """Der Daemon meldet Aktionen ALLER Apps — nur auf unsere IDs reagieren."""
        folder = getattr(self, "_notify_folder_by_id", {}).pop(int(notification_id), None)
        if folder and action_key == "open-folder" and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _selected_power_action(self):
        for key, action in getattr(self, "power_actions", {}).items():
            if key != "none" and action.isChecked():
                return key
        return None

    def _maybe_run_power_action(self):
        """Führt nach Queue-Ende die gewählte Energie-Aktion mit Countdown aus."""
        action = self._selected_power_action()
        if not action:
            return
        label = "Ruhezustand" if action == "suspend" else "Herunterfahren"

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Energie-Aktion")
        box.setStandardButtons(QMessageBox.StandardButton.Cancel)
        remaining = {"sec": 20}

        timer = QTimer(box)

        def tick():
            remaining["sec"] -= 1
            if remaining["sec"] <= 0:
                timer.stop()
                box.accept()
                QProcess.startDetached("systemctl", [action])
                return
            box.setText(tr(
                "{action} in {seconds} Sekunden …\n\nAbbrechen, um am System zu bleiben.",
                action=tr(label), seconds=remaining["sec"],
            ))

        box.setText(tr(
            "{action} in {seconds} Sekunden …\n\nAbbrechen, um am System zu bleiben.",
            action=tr(label), seconds=remaining["sec"],
        ))
        timer.timeout.connect(tick)
        timer.start(1000)
        box.exec()
        timer.stop()

    def _on_stop_queue(self):
        """Stoppt die Warteschlangen-Verarbeitung und bricht den laufenden Worker ab."""
        if not self.is_running:
            return
            
        self.is_running = False
        self.console.append("[LME WARTSCHLANGE] Verarbeitung wird gestoppt...")
        
        # Falls Untertitel-Extraktion/Transkription läuft, diese beenden
        if hasattr(self, "sub_process") and self.sub_process and self.sub_process.state() == QProcess.ProcessState.Running:
            self.sub_process.kill()
        if hasattr(self, "sub_ai_process") and self.sub_ai_process and self.sub_ai_process.state() == QProcess.ProcessState.Running:
            self.sub_ai_process.kill()
            
        if self.active_worker:
            self.active_worker.stop()
        else:
            self._update_ui_state()

    # --- CORE WORKER EXECUTION ---
    def _process_next_job(self):
        """Sucht den nächsten bereiten Job und startet den FFmpegWorker."""
        if not self.is_running:
            self._update_ui_state()
            return
            
        self.current_job_idx = -1
        if self._single_job_idx is not None:
            # Kontextmenü-Modus: nur den einen Job verarbeiten, dann beenden.
            idx = self._single_job_idx
            if 0 <= idx < len(self.jobs) and self.jobs[idx]["status"] == "Bereit":
                self.current_job_idx = idx
        else:
            for idx, job in enumerate(self.jobs):
                # Nur "Bereit"-Jobs verarbeiten. Bereits in diesem Lauf
                # fehlgeschlagene/übersprungene Jobs werden NICHT erneut gewählt
                # (sonst Endlosschleife). Retry erfolgt beim nächsten Start.
                if job["status"] == "Bereit":
                    self.current_job_idx = idx
                    break

        if self.current_job_idx == -1:
            self.is_running = False
            self._single_job_idx = None
            self.console.append("[LME WARTSCHLANGE] Alle Jobs verarbeitet.")
            done = sum(1 for j in self.jobs if j["status"] == "Fertig")
            failed = sum(1 for j in self.jobs if j["status"] == "Fehlgeschlagen")
            summary = tr(
                "Warteschlange abgeschlossen — {done}/{total} Jobs fertig.",
                done=done, total=len(self.jobs),
            )
            self.statusBar().showMessage(summary)
            # Desktop-Benachrichtigung statt modalem Dialog: blockiert nichts
            # und ist auch sichtbar, wenn das Fenster im Hintergrund liegt.
            body = tr("{count} Job(s) fertig", count=done)
            if failed:
                body += tr(", {count} fehlgeschlagen", count=failed)
            folder = next(
                (os.path.dirname(j["output_file"]) for j in self.jobs if j["status"] == "Fertig"),
                None,
            )
            self._notify("Warteschlange abgeschlossen", body, folder=folder)
            self._update_ui_state()
            self._maybe_run_power_action()
            return
            
        job = self.jobs[self.current_job_idx]

        # Disc-Jobs werden zweistufig verarbeitet: erst verlustfrei von der
        # Disc in eine Zwischendatei, dann daraus konvertieren. So laeuft das
        # Laufwerk nur waehrend des kurzen Auslesens statt ueber die gesamte
        # Umwandlung, und ein Lesefehler kostet nicht den ganzen Durchgang.
        if self._job_needs_disc_rip(job):
            self._run_disc_rip_stage(job)
            return

        if self._job_needs_subtitle_generation(job):
            self._run_subtitle_pipeline(job)
            return

        self._start_current_ffmpeg_job(job)

    def _job_needs_disc_rip(self, job):
        """True, wenn die Quelle eine Disc ist und noch keine Zwischendatei existiert."""
        settings = job.get("settings") or {}
        if not settings.get("input_args") and not settings.get("disc_type"):
            return False
        # Vorgabe ist der direkte Weg. Gemessen an einer Blu-ray liegen beide
        # Wege beim Auslesen gleichauf (5,6x gegen 5,5x) — die Grenze setzt das
        # Laufwerk, nicht die CPU. Zweistufig lohnt erst, wenn die Umwandlung
        # langsamer ist als das Laufwerk.
        if not settings.get("two_stage"):
            return False
        staged = settings.get("_staged_source")
        return not (staged and os.path.exists(staged))

    def _run_disc_rip_stage(self, job):
        """Stufe 1: Titel verlustfrei von der Disc in eine Zwischendatei lesen."""
        import optical_media

        settings = job["settings"]
        disc_type = optical_media.DiscType(settings.get("disc_type") or "bluray")

        needed = optical_media.estimate_remux_bytes(
            settings.get("source_duration") or 0.0,
            settings.get("source_bitrate") or 0,
            disc_type,
        )
        staging_dir, report = optical_media.choose_staging_dir(
            needed,
            preferred=settings.get("staging_dir") or self._configured_staging_dir(),
            output_dir=job.get("output_dir"),
        )

        if staging_dir is None:
            # Kein Platz ist kein Grund zu scheitern: der direkte Weg braucht
            # gar keinen Zwischenspeicher und funktioniert genauso.
            lines = "\n".join(
                f"  {path} — {optical_media.format_bytes(free)} frei"
                for path, free in report
            )
            self.console.append(
                "\n[LME DISC] Kein Zwischenspeicher mit genug Platz "
                f"(benoetigt etwa {optical_media.format_bytes(int(needed * optical_media.STAGING_MARGIN))}):\n"
                f"{lines}\n[LME DISC] Weiche auf direkte Konvertierung von der Disc aus."
            )
            settings.pop("_staged_source", None)
            settings["two_stage"] = False
            self._start_current_ffmpeg_job(job)
            return

        try:
            os.makedirs(staging_dir, exist_ok=True)
        except OSError as exc:
            self._fail_current_job(tr("Zwischenspeicher nicht nutzbar: {error}", error=str(exc)))
            return

        staged_path = os.path.join(
            staging_dir, f".lme_stage_{uuid.uuid4().hex}.mkv"
        )
        settings["_staged_source"] = staged_path

        title_num = int(settings.get("title_num") or 1)
        audio_idx = settings.get("audio_stream_idx")
        sub_idx = settings.get("subtitle_stream_idx")

        if disc_type == optical_media.DiscType.DVD_VIDEO:
            args, staged_path = optical_media.build_dvd_rip_args(
                source_path=job["input_file"], title_num=title_num,
                audio_stream_idx=audio_idx, subtitle_stream_idx=sub_idx,
                output_file=staged_path, remux_mkv=True,
            )
        else:
            args, staged_path = optical_media.build_bluray_rip_args(
                source_path=job["input_file"], playlist_num=title_num,
                audio_stream_idx=audio_idx, subtitle_stream_idx=sub_idx,
                output_file=staged_path, remux_mkv=True,
            )
        settings["_staged_source"] = staged_path

        job["_phase"] = "rip"
        job["status"] = self._phase_status(job, "Liest Disc...")
        job["progress"] = 0.0
        job["time_remaining"] = "Berechnet..."
        self._update_table_row(self.current_job_idx)

        self.console.append(
            f"\n[LME DISC] Stufe 1 von 2 — verlustfreies Auslesen nach {staging_dir}"
            f" (geschaetzt {optical_media.format_bytes(needed)})"
        )
        self.console.append("[LME DISC] Befehl: ffmpeg " + " ".join(args) + "\n")

        self.active_worker = FFmpegWorker(
            job["input_file"], staged_path, args,
            total_duration=float(settings.get("source_duration") or 0.0) or None,
        )
        self.active_worker.progress_updated.connect(self._on_worker_progress)
        self.active_worker.log_received.connect(self._on_worker_log)
        self.active_worker.status_changed.connect(self._on_worker_status)
        self.active_worker.finished.connect(self._on_disc_rip_stage_finished)
        self.active_worker.start()

    def _on_disc_rip_stage_finished(self, success, message):
        """Stufe 1 fertig — danach ganz normal konvertieren."""
        if self.current_job_idx == -1 or self.current_job_idx >= len(self.jobs):
            return
        job = self.jobs[self.current_job_idx]

        if not success:
            self._cleanup_staged_source(job)
            self._fail_current_job(tr("Auslesen der Disc fehlgeschlagen: {error}", error=message))
            return

        self.console.append("[LME DISC] Stufe 1 fertig. Stufe 2 von 2 — Konvertierung.")
        job["progress"] = 0.0
        self._update_table_row(self.current_job_idx)
        # Entkoppelt weiterreichen, damit der beendete Worker sauber abgebaut wird.
        QTimer.singleShot(0, lambda: self._start_current_ffmpeg_job(job))

    def _cleanup_staged_source(self, job):
        """Entfernt die Zwischendatei eines Disc-Jobs."""
        settings = job.get("settings") or {}
        staged = settings.pop("_staged_source", "")
        if staged and os.path.exists(staged):
            try:
                os.remove(staged)
                self.console.append(f"[LME DISC] Zwischendatei entfernt: {staged}")
            except OSError as exc:
                self.console.append(f"[LME DISC] Zwischendatei blieb liegen ({exc}): {staged}")

    def _fail_current_job(self, message):
        """Markiert den laufenden Job als fehlgeschlagen und macht weiter."""
        if self.current_job_idx == -1 or self.current_job_idx >= len(self.jobs):
            return
        job = self.jobs[self.current_job_idx]
        job["status"] = "Fehlgeschlagen"
        job["error_tail"] = str(message)
        self._run_done += 1
        self._update_table_row(self.current_job_idx)
        self.console.append(f"\n[LME FEHLER] {message}")
        QTimer.singleShot(0, self._process_next_job)

    def _configured_staging_dir(self):
        """Vom Anwender eingestellter Zwischenspeicher (leer = automatisch)."""
        return str(self.settings_store.value("staging_dir", "") or "").strip()

    def _existing_subtitle_path(self, settings):
        for key in ("temp_srt_path", "subtitles_file_path"):
            path = str(settings.get(key, "") or "").strip()
            if path and os.path.exists(path):
                return path
        return ""

    def _job_needs_subtitle_generation(self, job):
        settings = job["settings"]
        if str(settings.get("container", "")).lower() in presets.IMAGE_CONTAINERS:
            return False
        if not settings.get("subtitles_enabled", False):
            return False
        return not bool(self._existing_subtitle_path(settings))

    def _start_current_ffmpeg_job(self, job):
        """Startet FFmpeg fuer den bereits ausgewaehlten Queue-Job."""
        if self.current_job_idx == -1 or not self.is_running:
            return

        # Schutz: Ausgabe darf keine Quelldatei sein – weder die eigene noch
        # die eines anderen Queue-Jobs. FFmpeg läuft mit -y und würde die
        # Datei beim Lesen/Schreiben zerstören.
        output_path = os.path.abspath(job["output_file"])
        conflicting_input = None
        for other in self.jobs:
            try:
                same_file = os.path.abspath(other["input_file"]) == output_path
                if not same_file and os.path.exists(job["output_file"]):
                    same_file = os.path.samefile(other["input_file"], job["output_file"])
            except OSError:
                same_file = False
            if same_file:
                conflicting_input = other["input_file"]
                break
        if conflicting_input is not None:
            job["status"] = "Fehlgeschlagen"
            self._run_done += 1
            self._update_table_row(self.current_job_idx)
            self.console.append(
                f"\n[LME FEHLER] Ausgabedatei ist identisch mit einer Quelldatei der Warteschlange: "
                f"{os.path.basename(job['output_file'])} – Job übersprungen, um die Quelle nicht zu überschreiben."
            )
            QMessageBox.warning(
                self, "Ungültige Ausgabedatei",
                tr(
                    "Die Ausgabedatei ist identisch mit einer Quelldatei der Warteschlange:\n"
                    "{path}\n\n"
                    "Bitte einen anderen Zielnamen/-ordner wählen, sonst würde die "
                    "Originaldatei zerstört. Der Job wurde übersprungen.",
                    path=conflicting_input,
                ),
            )
            # Entkoppelt weitermachen — direkte Rekursion würde bei vielen
            # übersprungenen Jobs den Call-Stack aufblähen.
            QTimer.singleShot(0, self._process_next_job)
            return

        # Liegt eine Zwischendatei vor (Stufe 1 eines Disc-Jobs), wird ab hier
        # ganz normal aus dieser Datei konvertiert: die Disc-Optionen duerfen
        # dann NICHT mehr in die Befehlszeile, sonst wuerde FFmpeg erneut das
        # Laufwerk ansprechen.
        settings = job["settings"]
        staged = settings.get("_staged_source", "")
        if staged and os.path.exists(staged):
            job["_phase"] = "encode"
            effective_input = staged
            effective_settings = {
                k: v for k, v in settings.items()
                if k not in ("input_args", "disc_type")
            }
        else:
            effective_input = job["input_file"]
            effective_settings = settings

        job["status"] = self._phase_status(job, "Codiert...")
        job["progress"] = 0.0
        job["speed"] = "0.0x"
        job["time_remaining"] = "Berechnet..."
        job["_log_tail"] = []
        job.pop("error_tail", None)
        self._update_table_row(self.current_job_idx)

        self._on_job_selection_changed()

        ffmpeg_args = presets.get_ffmpeg_args(effective_input, job["output_file"], effective_settings)

        self.console.append(f"\n[LME LOGS] Starte Konvertierung von: {os.path.basename(job['input_file'])}")
        self.console.append(f"[LME LOGS] Befehl: ffmpeg " + " ".join(ffmpeg_args) + "\n")

        # Bei gesetzten Schnittmarken die erwartete Ausgabedauer vorgeben,
        # sonst rechnet der Fortschritt gegen die volle Quelldauer.
        # Bei Disc-Quellen ist die Titeldauer aus der Disc-Abfrage bekannt. Sie
        # vorzugeben macht den Fortschritt unabhaengig davon, ob FFmpeg im
        # Kopfbereich eine brauchbare Dauer meldet -- bei manchen Playlists und
        # Titeln fehlt sie oder ist irrefuehrend.
        expected_duration = None
        if settings.get("disc_type") or settings.get("input_args"):
            disc_duration = float(settings.get("source_duration") or 0.0)
            if disc_duration > 0:
                expected_duration = disc_duration

        trim_start = presets.parse_seconds(job["settings"].get("trim_start"))
        trim_end = presets.parse_seconds(job["settings"].get("trim_end"))
        if trim_start is not None or trim_end is not None:
            start = trim_start or 0.0
            end = trim_end if trim_end is not None else float(job.get("source_duration") or 0.0)
            if end > start:
                expected_duration = end - start

        self.active_worker = FFmpegWorker(
            effective_input, job["output_file"], ffmpeg_args,
            total_duration=expected_duration,
        )
        self.active_worker.progress_updated.connect(self._on_worker_progress)
        self.active_worker.log_received.connect(self._on_worker_log)
        self.active_worker.status_changed.connect(self._on_worker_status)
        self.active_worker.finished.connect(self._on_worker_finished)
        
        self.active_worker.start()

    def _run_subtitle_pipeline(self, job):
        """Vorbereitungsschritt: Audiospur extrahieren und transkribieren."""
        job["status"] = "Audio extrahieren..."
        self._update_table_row(self.current_job_idx)
        self.console.append(f"\n[LME KI] Starte Untertitel-Pipeline für: {os.path.basename(job['input_file'])}")
        
        import tempfile
        # Temp-Datei für MP3-Audio: mkstemp statt vorhersagbarem Namen in /tmp
        # (Symlink-Angriffe auf Mehrbenutzersystemen); -y überschreibt die leere Datei.
        fd, temp_audio = tempfile.mkstemp(prefix="lme_temp_audio_", suffix=".mp3")
        os.close(fd)
        job["settings"]["temp_audio_path"] = temp_audio
        
        self.sub_process = QProcess(self)
        self.sub_process.finished.connect(self._on_subtitle_audio_extracted)
        self.sub_process.errorOccurred.connect(self._on_subtitle_process_failed_to_start)

        # Audio extrahieren (mono, 16kHz MP3)
        args = ["-y", "-i", job["input_file"], "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", temp_audio]
        self.console.append(f"[LME KI] Extrahiere Audiospur...")
        self.sub_process.start("ffmpeg", args)

    def _on_subtitle_audio_extracted(self, exit_code, exit_status):
        """Wird aufgerufen, sobald die Audiospur extrahiert wurde."""
        if self.current_job_idx == -1:
            return
        job = self.jobs[self.current_job_idx]
        temp_audio = job["settings"].get("temp_audio_path")
        
        if not self.is_running:
            job["status"] = "Abgebrochen"
            self._update_table_row(self.current_job_idx)
            self._cleanup_subtitle_temp_audio(job)
            return
            
        if exit_code != 0 or not os.path.exists(temp_audio) or os.path.getsize(temp_audio) == 0:
            self.console.append("[LME WARNING] Audio-Extraktion fehlgeschlagen. Fahre ohne Untertitel fort.")
            self._cleanup_subtitle_temp_audio(job)
            self._start_current_ffmpeg_job(job)
            return
            
        self.console.append("[LME KI] Audio-Extraktion erfolgreich. Starte KI-Transkription...")
        job["status"] = "KI-Transkription..."
        self._update_table_row(self.current_job_idx)

        settings = job["settings"]
        source_lang = subtitle_utils.resolve_language(
            settings.get("subtitles_source", "Automatisch erkennen"),
            settings.get("subtitles_source_custom", ""),
        )
        settings["_subtitle_ai_stage"] = "transcribe"
        settings.pop("_subtitle_source_srt", None)

        prompt = subtitle_utils.build_transcription_prompt(temp_audio, source_lang)
        self._start_subtitle_ai_process(prompt)

    def _start_subtitle_ai_process(self, prompt):
        cli_cmd = subtitle_utils.choose_ai_cli()
        self.sub_ai_process = QProcess(self)
        self.sub_ai_process.finished.connect(self._on_subtitle_transcription_finished)
        self.sub_ai_process.errorOccurred.connect(self._on_subtitle_process_failed_to_start)
        args = subtitle_utils.build_ai_args(cli_cmd, prompt)
        self.sub_ai_process.start(cli_cmd, args)
        if cli_cmd in ("agy", "antigravity-cli"):
            self.sub_ai_process.write(prompt.encode("utf-8"))
            self.sub_ai_process.closeWriteChannel()

    def _on_subtitle_process_failed_to_start(self, error):
        """Fängt FailedToStart ab (ffmpeg/KI-CLI fehlt) — 'finished' feuert dann nie,
        ohne diesen Handler bliebe die Warteschlange endlos im Untertitel-Schritt hängen."""
        if error != QProcess.ProcessError.FailedToStart:
            return
        if self.current_job_idx < 0 or self.current_job_idx >= len(self.jobs):
            return
        job = self.jobs[self.current_job_idx]
        self._cleanup_subtitle_temp_audio(job)
        if not self.is_running:
            job["status"] = "Abgebrochen"
            self._update_table_row(self.current_job_idx)
            return
        self._continue_without_generated_subtitles(
            job,
            "Hilfsprogramm für Untertitel nicht gefunden (ffmpeg bzw. KI-CLI nicht installiert?).",
        )

    def _cleanup_subtitle_temp_audio(self, job):
        temp_audio = job["settings"].get("temp_audio_path")
        if temp_audio and os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except OSError:
                pass
        job["settings"].pop("temp_audio_path", None)

    def _continue_without_generated_subtitles(self, job, reason):
        if reason:
            self.console.append(f"[LME WARNING] {reason}\nFahre ohne automatisch erzeugte Untertitel fort.")
        job["settings"].pop("temp_srt_path", None)
        job["settings"].pop("_subtitle_ai_stage", None)
        job["settings"].pop("_subtitle_source_srt", None)
        self._start_current_ffmpeg_job(job)

    def _on_subtitle_transcription_finished(self, exit_code, exit_status):
        """Wird aufgerufen, sobald die KI-Transkription/Übersetzung fertig ist."""
        if self.current_job_idx == -1:
            return
        job = self.jobs[self.current_job_idx]
        settings = job["settings"]
        stage = settings.get("_subtitle_ai_stage", "transcribe")
            
        if not self.is_running:
            job["status"] = "Abgebrochen"
            self._update_table_row(self.current_job_idx)
            self._cleanup_subtitle_temp_audio(job)
            return
            
        if exit_code != 0:
            err = self.sub_ai_process.readAllStandardError().data().decode("utf-8", errors="replace").strip()
            if stage == "translate" and settings.get("_subtitle_source_srt"):
                self.console.append(
                    f"[LME WARNING] KI-Übersetzung fehlgeschlagen: {err}\n"
                    "Verwende die Original-Transkription mit unveränderten Timecodes."
                )
                self._finish_subtitle_pipeline(job, settings["_subtitle_source_srt"])
            else:
                self._cleanup_subtitle_temp_audio(job)
                self._continue_without_generated_subtitles(job, f"KI-Transkription fehlgeschlagen: {err}")
            return
            
        output = self.sub_ai_process.readAllStandardOutput().data().decode("utf-8", errors="replace").strip()

        if stage == "transcribe":
            self._cleanup_subtitle_temp_audio(job)
            try:
                source_srt = subtitle_utils.normalize_srt(output)
            except ValueError as e:
                self._continue_without_generated_subtitles(
                    job,
                    f"KI hat keine validen SRT-Untertitel geliefert: {e}",
                )
                return

            settings["_subtitle_source_srt"] = source_srt
            target_lang = subtitle_utils.resolve_language(
                settings.get("subtitles_translate", subtitle_utils.NO_TRANSLATION),
                settings.get("subtitles_translate_custom", ""),
            )

            if target_lang != subtitle_utils.NO_TRANSLATION:
                settings["_subtitle_ai_stage"] = "translate"
                job["status"] = "KI-Übersetzung..."
                self._update_table_row(self.current_job_idx)
                self.console.append(
                    "[LME KI] Transkription fertig. Übersetze Untertitel und erhalte die Timecodes..."
                )
                prompt = subtitle_utils.build_translation_prompt(source_srt, target_lang)
                self._start_subtitle_ai_process(prompt)
                return

            self._finish_subtitle_pipeline(job, source_srt)
            return

        try:
            srt_content = subtitle_utils.merge_translated_text_with_source_timecodes(
                settings.get("_subtitle_source_srt", ""),
                output,
            )
        except ValueError as e:
            self.console.append(
                f"[LME WARNING] Übersetzung hatte keine stabile SRT-Struktur: {e}\n"
                "Verwende die Original-Transkription mit unveränderten Timecodes."
            )
            srt_content = settings.get("_subtitle_source_srt", "")

        self._finish_subtitle_pipeline(job, srt_content)

    def _finish_subtitle_pipeline(self, job, srt_content):
        try:
            srt_content = subtitle_utils.normalize_srt(srt_content)
        except ValueError as e:
            self._continue_without_generated_subtitles(job, f"Finale SRT ist ungueltig: {e}")
            return

        mode = job["settings"].get("subtitles_mode", "Soft-Untertitel (in Container einbetten)")
        
        import tempfile
        if mode == "Nur externe .srt-Datei erzeugen":
            srt_path = f"{os.path.splitext(job['output_file'])[0]}.srt"
            # Vorhandene .srt nicht stillschweigend überschreiben — mitten in
            # der Queue ist kein Dialog möglich, daher eindeutiger Name.
            if os.path.exists(srt_path):
                base, ext = os.path.splitext(srt_path)
                counter = 1
                while os.path.exists(f"{base}_{counter}{ext}"):
                    counter += 1
                srt_path = f"{base}_{counter}{ext}"
                self.console.append(
                    f"[LME KI] Hinweis: .srt existierte bereits, speichere als {os.path.basename(srt_path)}"
                )
            job["settings"]["temp_srt_path"] = srt_path
            job["settings"]["subtitles_file_path"] = srt_path
        else:
            # mkstemp statt vorhersagbarem Namen; der Prefix "lme_temp_sub_"
            # steuert weiterhin das Aufräumen in _on_worker_finished.
            fd, srt_path = tempfile.mkstemp(prefix="lme_temp_sub_", suffix=".srt")
            os.close(fd)
            job["settings"]["temp_srt_path"] = srt_path
            
        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            self.console.append(f"[LME KI] Untertitel erfolgreich erstellt: {srt_path}")
        except Exception as e:
            self.console.append(f"[LME WARNING] Fehler beim Schreiben der Untertiteldatei: {e}")
            self._continue_without_generated_subtitles(job, "")
            return
            
        job["settings"].pop("_subtitle_ai_stage", None)
        job["settings"].pop("_subtitle_source_srt", None)
        self._start_current_ffmpeg_job(job)

    def _on_worker_progress(self, percent, speed, time_remaining):
        if self.current_job_idx == -1:
            return
        job = self.jobs[self.current_job_idx]
        job["progress"] = percent
        job["speed"] = speed
        job["time_remaining"] = time_remaining
        self._update_table_row(self.current_job_idx)
        self.statusBar().showMessage(tr(
            "Codiere {filename} — {percent:.0f} % · {speed} · noch {remaining}  "
            "(Job {current}/{total})",
            filename=os.path.basename(job["input_file"]), percent=percent,
            speed=speed, remaining=time_remaining,
            current=self.current_job_idx + 1, total=len(self.jobs),
        ))
        # Gesamtfortschritt über alle Jobs des Laufs
        if self._run_total > 0:
            overall = (self._run_done + percent / 100.0) / self._run_total * 100.0
            self.queue_progress.setValue(int(min(100.0, max(0.0, overall))))
            self.queue_progress.setVisible(True)

    def _on_worker_log(self, text):
        self.console.append(text)
        # Letzte FFmpeg-Zeilen am Job sammeln — Grundlage für die
        # Fehlerdetails an der Queue-Zeile (das Log ist standardmäßig versteckt).
        if 0 <= self.current_job_idx < len(self.jobs):
            tail = self.jobs[self.current_job_idx].setdefault("_log_tail", [])
            stripped = text.strip()
            if stripped:
                tail.append(stripped)
                del tail[:-15]

    def _on_worker_status(self, text):
        if self.current_job_idx == -1:
            return
        job = self.jobs[self.current_job_idx]
        job["status"] = self._phase_status(job, text)
        self._update_table_row(self.current_job_idx)

    @staticmethod
    def _phase_status(job, text):
        """Stellt bei Disc-Jobs die Stufe vor die Meldung des Workers."""
        phase = job.get("_phase")
        if not phase:
            return text
        label = tr("Stufe 1/2 · Liest Disc") if phase == "rip" else tr("Stufe 2/2 · Konvertiert")
        # Die Anlaufmeldung des Workers traegt keine eigene Aussage.
        if str(text).startswith("Initialisiere"):
            return f"{label}..."
        return f"{label} · {text}"

    def _on_worker_finished(self, success, message):
        if self.current_job_idx != -1:
            job = self.jobs[self.current_job_idx]
            # Zwischendatei eines Disc-Jobs raeumen — bei Erfolg wie bei
            # Misserfolg, sonst bleiben zweistellige Gigabytebetraege liegen.
            self._cleanup_staged_source(job)
            job.pop("_phase", None)
            self._run_done += 1
            if success:
                job["status"] = "Fertig"
                job["progress"] = 100.0
                job["speed"] = "0.0x"
                job["time_remaining"] = "0s"
                job.pop("_log_tail", None)
                self.console.append(f"[LME INFO] Job erfolgreich abgeschlossen: {message}\n")
            else:
                # Nur ein aktiver Benutzerabbruch ist "Abgebrochen" — alles andere
                # (ffmpeg fehlt, Datei fehlt, Exit-Code != 0) ist ein Fehler.
                job["status"] = "Abgebrochen" if "abgebrochen" in message.lower() else "Fehlgeschlagen"
                job["speed"] = "0.0x"
                job["time_remaining"] = "--"
                if job["status"] == "Fehlgeschlagen":
                    tail = job.pop("_log_tail", [])
                    details = [message] + tail if message else tail
                    job["error_tail"] = "\n".join(details[-15:])
                else:
                    job.pop("_log_tail", None)
                self.console.append(f"[LME WARNING] Job beendet: {message}\n")
                
            # Temp SRT Datei aufräumen falls vorhanden
            temp_srt = job["settings"].get("temp_srt_path")
            if temp_srt and "lme_temp_sub_" in os.path.basename(temp_srt) and os.path.exists(temp_srt):
                try:
                    os.remove(temp_srt)
                except OSError:
                    pass
                
            self._update_table_row(self.current_job_idx)
            
        self.active_worker = None
        # Entkoppelt statt direkt: verhindert Rekursion über die ganze Queue,
        # wenn Jobs synchron scheitern (z. B. ffmpeg nicht installiert).
        QTimer.singleShot(0, self._process_next_job)

    def _update_ui_state(self):
        """Aktiviert/Deaktiviert Toolbar-Buttons basierend auf Warteschlangen-Aktivität."""
        has_jobs = len(self.jobs) > 0
        
        self.action_add.setEnabled(not self.is_running)
        self.action_remove.setEnabled(not self.is_running and has_jobs)
        self.action_clear.setEnabled(not self.is_running and has_jobs)
        if hasattr(self, "action_trim"):
            self.action_trim.setEnabled(not self.is_running and has_jobs)
        
        btn_start = self.findChild(QPushButton, "btn_start")
        btn_stop = self.findChild(QPushButton, "btn_stop")
        
        if btn_start:
            btn_start.setEnabled(not self.is_running)
        if btn_stop:
            btn_stop.setEnabled(self.is_running)
        if hasattr(self, "btn_output_dir_all"):
            self.btn_output_dir_all.setEnabled(not self.is_running and has_jobs)
        if hasattr(self, "btn_settings_all"):
            self.btn_settings_all.setEnabled(not self.is_running and has_jobs)
        if hasattr(self, "queue_progress") and not self.is_running:
            self.queue_progress.setVisible(False)
            self.queue_progress.setValue(0)

    def _get_current_video_duration(self, input_file):
        """Ermittelt die Dauer eines Videos mittels ffprobe."""
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

    def _on_intelligent_mode_clicked(self):
        """Öffnet den Intelligenten Bitraten-Rechner Dialog."""
        selected_row = self.queue_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.jobs):
            QMessageBox.warning(self, "Kein Job ausgewählt", "Bitte wählen Sie zuerst einen Job aus der Warteschlange aus.")
            return
            
        job = self.jobs[selected_row]
        input_file = job["input_file"]
        codec = self.combo_vcodec.currentText()

        # Dauer ermitteln: bevorzugt aus dem asynchronen Prefetch-Cache,
        # nur im Ausnahmefall synchron via ffprobe.
        duration = float(job.get("source_duration") or 0.0)
        if duration <= 0:
            duration = self._get_current_video_duration(input_file)
        
        from PyQt6.QtWidgets import QDialog
        from intelligent_dialog import IntelligentBitrateDialog
        dialog = IntelligentBitrateDialog(duration, codec, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            v_bitrate_mbps, a_bitrate_kbps = dialog.get_calculated_bitrates()
            
            # Werte in die GUI eintragen
            self.combo_encoding.setCurrentText("VBR, 1 Durchgang")
            self._configure_bitrate_spin(v_bitrate_mbps)
            self.spin_bitrate_val.setValue(v_bitrate_mbps)
            self.combo_audiobitrate.setCurrentText(a_bitrate_kbps)

            self._save_ui_settings_to_job()

    def _on_toggle_ffmpeg_view(self, checked):
        """Blendet das FFmpeg-Log und die Befehlsvorschau ein/aus (Standard: aus)."""
        if checked:
            self.bottom_tabs.setVisible(True)
            if self.bottom_tabs.indexOf(self.console_widget) == -1:
                idx = self.bottom_tabs.insertTab(0, self.console_widget, self._console_tab_label)
                self.bottom_tabs.setCurrentIndex(idx)
        else:
            i = self.bottom_tabs.indexOf(self.console_widget)
            if i != -1:
                self.bottom_tabs.removeTab(i)
            self.bottom_tabs.setVisible(False)
        self.cmd_group.setVisible(checked)

    def _set_theme(self, name, persist=True):
        """Wendet ein Theme app-weit an und merkt sich die Auswahl."""
        app = QApplication.instance()
        if name == "dark":
            styles.apply_dark_theme(app)
            self._link_color = styles.LINK_DARK
        else:
            name = "native"
            styles.apply_native_theme(app)
            self._link_color = styles.LINK_NATIVE
        self.dark_action.setChecked(name == "dark")
        self.native_action.setChecked(name == "native")
        # Link-/Statusfarben der Queue an das Theme anpassen
        for idx in range(len(self.jobs)):
            self._update_table_row(idx)
        if persist:
            self.settings_store.setValue("theme", name)

    def _on_about_clicked(self):
        QMessageBox.about(
            self,
            "Über Linux Media Encoder",
            tr(
                "<h3>Linux Media Encoder v{version}</h3>"
                "<p>Ein getreues, professionelles GUI-Werkzeug für FFmpeg, inspiriert vom Adobe Media Encoder.</p>"
                "<p>Entwickelt mit Python 3 und PyQt6.</p>"
                "<p>© 2026</p>",
                version=__version__,
            )
        )
