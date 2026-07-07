# -*- coding: utf-8 -*-
"""
Theme-Definitionen für den Linux Media Encoder.
Ein modernes, flaches Dark-Theme (Breeze/AME mit Akzentblau) sowie eine dezente
Politur für das native System-Theme.
"""

# Zentrale Farben: KDE-Breeze-Dark-Basis mit LME-eigener Note — AME-artige
# Dichte und Struktur, aber Breeze-Blau (#3daee9) als Akzent und die
# vertrauten Breeze-Signalfarben. Bewusst kein Adobe-Klon.
WINDOW = "#1a1d20"
SURFACE = "#232629"
SURFACE_RAISED = "#2a2e32"
SURFACE_SUNKEN = "#1c1f22"
BORDER = "#3a3f44"
BORDER_SOFT = "#31363b"
TEXT = "#eff0f1"
TEXT_MUTED = "#bdc3c7"
TEXT_DISABLED = "#70777d"
ACCENT = "#3daee9"
ACCENT_HOVER = "#5cc1f2"
ACCENT_DARK = "#2980b9"
START_GREEN = "#27ae60"
START_GREEN_HOVER = "#2ecc71"
STOP_RED = "#da4453"
STOP_RED_HOVER = "#ed5565"
WARN_ORANGE = "#f67400"

# Linkfarben für die Queue-Spalten (Breeze-Link-Blau, je Theme lesbar gewählt)
LINK_DARK = "#3daee9"
LINK_NATIVE = "#2980b9"

DARK_STYLESHEET = f"""
/* Globale Widget-Stile */
QWidget {{
    background-color: {SURFACE};
    color: {TEXT};
    font-family: 'Noto Sans', 'Inter', 'Cantarell', 'Ubuntu', 'DejaVu Sans', sans-serif;
    font-size: 12px;
}}

QMainWindow, QDialog {{
    background-color: {WINDOW};
}}

/* Menüleiste */
QMenuBar {{
    background-color: {WINDOW};
    color: {TEXT_MUTED};
    padding: 2px;
    border-bottom: 1px solid {BORDER_SOFT};
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background-color: {SURFACE_RAISED};
    color: {TEXT};
}}
QMenu {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 22px 5px 18px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: #ffffff;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER_SOFT};
    margin: 4px 6px;
}}

/* Toolbar */
QToolBar {{
    background-color: {SURFACE};
    border: none;
    border-bottom: 1px solid {BORDER_SOFT};
    padding: 5px;
    spacing: 6px;
}}
QToolBar QToolButton {{
    background: transparent;
    padding: 5px 8px;
    border-radius: 5px;
    color: {TEXT_MUTED};
}}
QToolBar QToolButton:hover {{
    background-color: {SURFACE_RAISED};
    color: {TEXT};
}}
QToolBar::separator {{
    width: 1px;
    background: {BORDER};
    margin: 4px 6px;
}}

/* Statusleiste */
QStatusBar {{
    background-color: {WINDOW};
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER_SOFT};
}}
QStatusBar::item {{ border: none; }}

/* ScrollBars */
QScrollBar:vertical {{
    border: none;
    background-color: {SURFACE_SUNKEN};
    width: 8px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background-color: {BORDER};
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{ background-color: #4b535a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{
    border: none;
    background-color: {SURFACE_SUNKEN};
    height: 8px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background-color: {BORDER};
    min-width: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{ background-color: #4b535a; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

/* Buttons */
QPushButton {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    padding: 6px 14px;
    border-radius: 5px;
    color: {TEXT};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: rgba(239, 240, 241, 0.08);
    border-color: {ACCENT};
    color: {TEXT};
}}
QPushButton:pressed {{
    background-color: {ACCENT_DARK};
    border-color: {ACCENT_DARK};
    color: #ffffff;
}}
QPushButton:disabled {{
    background-color: {SURFACE_SUNKEN};
    border-color: {BORDER_SOFT};
    color: {TEXT_DISABLED};
}}

/* Start-Button (grün) */
QPushButton#btn_start {{
    background-color: {START_GREEN};
    color: #ffffff;
    border: 1px solid {START_GREEN};
    font-weight: bold;
    padding: 6px 18px;
}}
QPushButton#btn_start:hover {{
    background-color: {START_GREEN_HOVER};
    border-color: {START_GREEN_HOVER};
}}
QPushButton#btn_start:pressed {{ background-color: #268a3a; }}
QPushButton#btn_start:disabled {{
    background-color: #234033;
    border-color: #234033;
    color: #8fa99b;
}}

/* Stop-Button (rot) */
QPushButton#btn_stop {{
    background-color: {STOP_RED};
    color: #ffffff;
    border: 1px solid {STOP_RED};
    font-weight: bold;
    padding: 6px 18px;
}}
QPushButton#btn_stop:hover {{
    background-color: {STOP_RED_HOVER};
    border-color: {STOP_RED_HOVER};
}}
QPushButton#btn_stop:pressed {{ background-color: #b83232; }}
QPushButton#btn_stop:disabled {{
    background-color: #46282d;
    border-color: #46282d;
    color: #ad8d92;
}}

QPushButton#btn_primary {{
    background-color: {ACCENT_DARK};
    border-color: {ACCENT_DARK};
    color: #ffffff;
    font-weight: bold;
}}
QPushButton#btn_primary:hover {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
QPushButton#btn_primary:disabled {{
    background-color: {SURFACE_SUNKEN};
    border-color: {BORDER_SOFT};
    color: {TEXT_DISABLED};
}}

QPushButton#btn_ai_subtitles {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {ACCENT_DARK};
    color: {TEXT};
    font-weight: bold;
}}
QPushButton#btn_ai_subtitles:hover {{
    background-color: rgba(61, 174, 233, 0.14);
    border-color: {ACCENT};
}}

/* Eingabefelder */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {SURFACE_SUNKEN};
    border: 1px solid {BORDER};
    padding: 5px 8px;
    border-radius: 5px;
    color: {TEXT};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
    background-color: rgba(61, 174, 233, 0.08);
}}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {{
    color: {TEXT_DISABLED};
    background-color: {SURFACE};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid {BORDER_SOFT};
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
    padding: 2px;
    outline: none;
}}

/* Tabellen / Listen */
QTableWidget, QListWidget, QTreeView {{
    background-color: {SURFACE_SUNKEN};
    border: 1px solid {BORDER_SOFT};
    border-radius: 6px;
    gridline-color: {BORDER_SOFT};
    selection-background-color: rgba(61, 174, 233, 0.28);
    selection-color: #ffffff;
    alternate-background-color: #26292d;
    outline: none;
}}
QTableWidget::item, QListWidget::item {{
    padding: 6px;
    border-bottom: 1px solid #262a2e;
}}
QListWidget::item {{ border-radius: 4px; }}
QTableWidget::item:selected, QListWidget::item:selected {{
    background-color: rgba(61, 174, 233, 0.30);
    color: #ffffff;
}}
QListWidget::item:hover, QTableWidget::item:hover {{ background-color: rgba(239, 240, 241, 0.06); }}
QHeaderView::section {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_MUTED};
    padding: 7px;
    border: none;
    border-bottom: 1px solid {BORDER_SOFT};
    border-right: 1px solid {BORDER_SOFT};
    font-weight: bold;
}}
QTableCornerButton::section {{ background-color: {SURFACE_RAISED}; border: none; }}

/* Labels */
QLabel {{
    color: {TEXT};
    background: transparent;
}}
QLabel#title_label {{
    font-size: 14px;
    font-weight: bold;
    color: {TEXT};
    padding-bottom: 6px;
    border-bottom: 1px solid {BORDER_SOFT};
}}

/* Tabs */
QTabWidget::pane {{
    border: 1px solid {BORDER_SOFT};
    border-radius: 6px;
    background-color: {SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background-color: {SURFACE_SUNKEN};
    color: {TEXT_MUTED};
    padding: 7px 16px;
    border: 1px solid {BORDER_SOFT};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {SURFACE};
    color: {TEXT};
    border-color: {BORDER_SOFT};
    border-top: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; background-color: {SURFACE_RAISED}; }}
QTabBar::tab:disabled {{ color: {TEXT_DISABLED}; }}

/* Fortschrittsbalken */
QProgressBar {{
    border: 1px solid {BORDER_SOFT};
    background-color: {SURFACE_SUNKEN};
    text-align: center;
    color: {TEXT};
    font-weight: bold;
    height: 16px;
    border-radius: 5px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 4px;
}}

/* Slider */
QSlider::groove:horizontal {{
    border: none;
    height: 5px;
    background-color: {BORDER_SOFT};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background-color: {ACCENT};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background-color: {TEXT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background-color: {ACCENT_HOVER}; }}
QSlider::groove:horizontal:disabled {{ background-color: {SURFACE_SUNKEN}; }}
QSlider::handle:horizontal:disabled {{ background-color: {BORDER}; }}

/* Checkboxen */
QCheckBox {{ spacing: 7px; color: {TEXT_MUTED}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background-color: {SURFACE_SUNKEN};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* Konsolen- / Log-Output */
QTextEdit#console_output {{
    background-color: #17191b;
    color: #8ff0a4;
    font-family: 'Hack', 'JetBrains Mono', 'Fira Code', 'Noto Sans Mono', monospace;
    font-size: 11px;
    border: 1px solid {BORDER_SOFT};
    border-radius: 6px;
    padding: 6px;
}}

/* Tooltips */
QToolTip {{
    background-color: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {ACCENT};
    border-radius: 4px;
    padding: 4px 6px;
}}

/* GroupBox */
QGroupBox {{
    border: 1px solid {BORDER_SOFT};
    border-radius: 6px;
    margin-top: 12px;
    font-weight: bold;
    padding-top: 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_MUTED};
}}

/* Benannte Panels */
QLabel#summary_box {{
    background-color: {SURFACE_SUNKEN};
    border: 1px solid {BORDER_SOFT};
    border-radius: 6px;
    padding: 8px;
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QTextEdit#cmd_preview {{
    background-color: #17191b;
    color: #9ccdf3;
    font-family: 'Hack', 'JetBrains Mono', 'Fira Code', 'Noto Sans Mono', monospace;
    font-size: 11px;
    border: 1px solid {BORDER_SOFT};
    border-radius: 6px;
    padding: 6px;
}}
QLabel#output_link {{
    color: {ACCENT_HOVER};
    font-weight: bold;
    text-decoration: underline;
}}
QLabel#link_label {{
    color: {ACCENT_HOVER};
    font-weight: bold;
    text-decoration: underline;
}}
QLabel#preview_frame {{
    background-color: #17191b;
    border: 1px solid {BORDER_SOFT};
    border-radius: 6px;
    color: {TEXT_DISABLED};
    font-size: 15px;
}}
QLabel#time_current {{
    color: {ACCENT_HOVER};
    font-family: 'Hack', 'JetBrains Mono', 'Fira Code', 'Noto Sans Mono', monospace;
}}
QLabel#time_total {{
    color: {TEXT_MUTED};
    font-family: 'Hack', 'JetBrains Mono', 'Fira Code', 'Noto Sans Mono', monospace;
}}
QSplitter::handle {{ background-color: {BORDER_SOFT}; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QSplitter::handle:vertical {{ height: 3px; }}
"""

# Dezente Politur für das native System-Theme. Statt eines leeren Stylesheets
# geben wir den benannten Panels palette-basierte Farben, damit sie sowohl unter
# hellen als auch dunklen System-Themes sauber aussehen.
NATIVE_STYLESHEET = """
QLabel#title_label {
    font-size: 14px;
    font-weight: bold;
    padding-bottom: 6px;
    border-bottom: 1px solid palette(mid);
}
QLabel#summary_box {
    background-color: palette(base);
    border: 1px solid palette(mid);
    border-radius: 6px;
    padding: 8px;
    color: palette(text);
    font-size: 11px;
}
QTextEdit#cmd_preview {
    background-color: palette(base);
    color: palette(text);
    font-family: monospace;
    font-size: 11px;
    border: 1px solid palette(mid);
    border-radius: 6px;
    padding: 6px;
}
QLabel#output_link {
    color: #3daee9;
    font-weight: bold;
    text-decoration: underline;
}
QLabel#link_label {
    color: #3daee9;
    font-weight: bold;
    text-decoration: underline;
}
QLabel#preview_frame {
    background-color: palette(base);
    border: 1px solid palette(mid);
    border-radius: 6px;
    color: palette(mid);
}
QLabel#time_current {
    color: #3daee9;
    font-family: monospace;
}
QLabel#time_total {
    color: palette(mid);
    font-family: monospace;
}
QTextEdit#console_output {
    font-family: monospace;
    font-size: 11px;
}
QPushButton#btn_start {
    background-color: #2ea043;
    color: #ffffff;
    border: 1px solid #2a8f3c;
    border-radius: 5px;
    padding: 6px 18px;
    font-weight: bold;
}
QPushButton#btn_start:hover { background-color: #3fb950; }
QPushButton#btn_stop {
    background-color: #d13a3a;
    color: #ffffff;
    border: 1px solid #bb3333;
    border-radius: 5px;
    padding: 6px 18px;
    font-weight: bold;
}
QPushButton#btn_stop:hover { background-color: #e5484d; }
QPushButton#btn_primary {
    background-color: #2980b9;
    color: #ffffff;
    border: 1px solid #22729c;
    border-radius: 5px;
    padding: 6px 14px;
    font-weight: bold;
}
QPushButton#btn_primary:hover { background-color: #3daee9; }
QPushButton#btn_ai_subtitles {
    font-weight: bold;
    border: 1px solid #3daee9;
    border-radius: 5px;
    padding: 6px 14px;
}
QPushButton#btn_ai_subtitles:hover { background-color: palette(alternate-base); }
"""

def apply_dark_theme(app):
    """Wendet das benutzerdefinierte dunkle Theme auf die Anwendung an."""
    app.setStyleSheet(DARK_STYLESHEET)

def apply_native_theme(app):
    """Nutzt den nativen System-Look mit dezenter Politur für benannte Panels."""
    app.setStyleSheet(NATIVE_STYLESHEET)
