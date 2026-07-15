# -*- coding: utf-8 -*-
"""
Einstiegspunkt für den Linux Media Encoder (LME).
Initialisiert die QApplication, wendet das Styling an und öffnet das Hauptfenster.
"""

import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from mainwindow import MainWindow
from i18n import configure_application
from version import __version__

def main():
    # Anlegen der PyQt-Applikation
    app = QApplication(sys.argv)
    configure_application(app)

    # App-Informationen für Betriebssystem-Integration (Desktop-Datei, QSettings, Notifications)
    app.setApplicationName("Linux Media Encoder")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("LinuxMediaEncoder")
    app.setDesktopFileName("linux-media-encoder")

    # Anwendungs-Icon (neben dem Skript oder im Installationsverzeichnis)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linux-media-encoder.svg")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Hauptfenster instanziieren und anzeigen; Sitzung (Queue, Geometrie)
    # der letzten Nutzung wiederherstellen
    window = MainWindow()
    window.enable_session_persistence()
    window.show()

    # Per Kommandozeile bzw. "Öffnen mit..." übergebene Dateien einreihen
    # (die Desktop-Datei deklariert Exec=... %F).
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):
            window._add_file_to_queue(os.path.abspath(arg))

    # PyQt Event-Loop starten
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
