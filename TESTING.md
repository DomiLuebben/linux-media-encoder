# Lokale Prüfung

Voraussetzungen: Python 3, PyQt6, FFmpeg und ffprobe mit den angebotenen
Software-Audiocodecs. Ein optisches Laufwerk ist für die Tests nicht nötig.

```bash
bash scripts/verify-all.sh
```

Der Einstieg prüft Python-Syntax, führt die Gesamtsuite aus, startet jede
Testdatei zusätzlich in einem eigenen Prozess und prüft den Aufbau der
Dialoge. Einstellungen liegen während des Laufs in einem temporären
Konfigurationsordner. Jeder fehlgeschlagene Schritt beendet den Lauf mit
einem Fehler. Tests verwenden temporäre Dateien; einige ältere Tests erzeugen
zusätzlich ignorierte Encoder-Ausgaben im Projektordner.

`test_audit_20260908.py` prüft die Audio-CD-Kette mit echtem FFmpeg in sechs
Formaten einschließlich Metadaten. Nur das Lesen vom CD-Laufwerk wird durch
das Kopieren einer erzeugten WAV-Datei ersetzt. Abbruchtests verwenden echte
Prozesse, Untertitel- und Kollisionsprüfungen echte temporäre Dateien.
Einzelner Start: `QT_QPA_PLATFORM=offscreen python -m unittest test_audit_20260908 -v`.

Nach Quelländerungen die SHA-256-Werte im PKGBUILD aktualisieren und das Paket
separat mit `makepkg -f` bauen. Ein erfolgreicher Paketbau allein führt die
Tests nicht aus und ist keine Funktionsfreigabe. Installation und Veröffentlichung
sind eigene Schritte.

Die lokalen Tests ersetzen keinen vollständigen Hardware-Rip, keine Abnahme
verschlüsselter/beschädigter Discs und keinen Test der externen KI-Dienste.
