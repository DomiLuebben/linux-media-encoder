# Linux Media Encoder (LME)

Ein professioneller GUI-Encoder für **FFmpeg** im Stil des Adobe Media Encoder –
geschrieben in Python 3 mit PyQt6.

![LME](linux-media-encoder.svg)

## Funktionen

- Warteschlange (Queue) mit mehreren Jobs, Drag & Drop von Dateien
- AME-artiger Export-Dialog mit echter Quell-Vorschau & Metadaten (via `ffprobe`)
- Presets (MP4/H.264, HEVC, VP9, AV1, MKV, Match Source, Social/Delivery, MP3, FLAC, Stream-Copy)
- Video: Auflösung, Framerate, Profil, **CRF / VBR / CBR**
- Audio: AAC, MP3, Opus, FLAC, Copy; `Benutzerdefiniert` zeigt alle erkannten FFmpeg-Video-/Audio-Codecs plus Stream-Copy
- Batch-Aktionen: aktuelle Video-/Audio-Einstellungen oder Ausgabeordner auf die ganze Warteschlange anwenden
- Stream-Copy bleibt echte Stream-Copy: Video kann unverändert kopiert werden, während nur Audio neu encodiert wird
- Intelligenter Bitraten-Rechner (lokales `claude`/`agy` Antigravity-CLI + Formel-Fallback)
- KI-Untertitel: automatische SRT-Erzeugung aus Audio, optionale Übersetzung und Einbettung als Soft- oder Hard-Subtitles
- Web-optimierte MP4/MOV (`+faststart`) und kompatibles `yuv420p` für H.264/H.265
- Live-Fortschritt, Geschwindigkeit, Restzeit; Gesamtfortschritt der Queue in der Statusleiste; optionale FFmpeg-Konsole
- **GPU-Encoding (NVENC)**: H.264/HEVC/AV1 als eigene Formate, sofern das installierte FFmpeg die Encoder kennt (CRF wird automatisch auf `-cq` gemappt)
- **Trim/Schnitt**: In-/Out-Punkte auf der Timeline des Export-Dialogs (frame-genau, Untertitel bleiben synchron)
- Zusätzliche Audio-Formate: WAV (PCM) und OGG (Opus)
- Warteschlangen-Kontextmenü: einzelnen Job starten, duplizieren, umsortieren, Zieldatei im Dateimanager zeigen; Mehrfachauswahl beim Löschen
- Fehlgeschlagene Jobs zeigen die letzten FFmpeg-Meldungen per Tooltip/Doppelklick
- Warnung, bevor existierende Zieldateien überschrieben werden
- Desktop-Benachrichtigung bei Queue-Ende; optional Ruhezustand/Herunterfahren nach Abschluss
- Sitzung (Warteschlange, Fenster-Layout) wird beim Beenden gespeichert und wiederhergestellt
- "Öffnen mit…"-Integration: per Dateimanager übergebene Dateien landen direkt in der Queue
- Native Fensterdekorationen des Desktops mit klassischer App-Menüleiste
- Breeze-Dark-Theme im AME-Stil oder natives System-Theme (Auswahl wird gemerkt)

## Voraussetzungen

- `python` (3.11+)
- `python-pyqt6`
- `ffmpeg` (inkl. `ffprobe`) im `PATH`

## Direkt starten (ohne Installation)

```sh
python main.py
```

## Als Arch-Paket bauen & installieren

Im entpackten Ordner:

```sh
makepkg -si
```

Danach erscheint **Linux Media Encoder** im Anwendungsmenü und ist über den
Befehl `linux-media-encoder` startbar.

Paket entfernen:

```sh
sudo pacman -R linux-media-encoder
```

## Lizenz

MIT
