# Linux Media Encoder (LME)

[English](README.md) | **Deutsch** | [Français](README.fr.md)

Ein professioneller GUI-Encoder für **FFmpeg** im Stil des Adobe Media Encoder –
geschrieben in Python 3 mit PyQt6.

![LME](linux-media-encoder.svg)

## Funktionen

- **CD / DVD / BD Ripper (Strg+D)**: Einlesen und Rippen von Audio-CDs (inkl. CD-Text nach FLAC/MP3/AAC/Opus), DVD-Video (Titel-, Audio- & Untertitel-Auswahl nach MKV oder Warteschlange), Blu-ray Discs (Playlist-Inspektion) sowie 1:1 ISO-Abbilderstellung
- Warteschlange (Queue) mit mehreren Jobs, Drag & Drop von Dateien und Disc-/ISO-Images
- AME-artiger Export-Dialog mit echter Quell-Vorschau & Metadaten (via `ffprobe`)
- Presets (MP4/H.264, HEVC, VP9, AV1, MKV, Match Source, Social/Delivery, MP3, FLAC, Stream-Copy)
- Video: Auflösung, Framerate, Profil, **CRF / VBR / CBR**
- Audio: AAC, MP3, Opus, FLAC, Copy; `Benutzerdefiniert` zeigt alle erkannten FFmpeg-Video-/Audio-Codecs plus Stream-Copy
- Batch-Aktionen: aktuelle Video-/Audio-Einstellungen oder Ausgabeordner auf die ganze Warteschlange anwenden
- Stream-Copy bleibt echte Stream-Copy: Video kann unverändert kopiert werden, während nur Audio neu encodiert wird
- Intelligenter Bitraten-Rechner mit optionalem lokalem KI-CLI und Formel-Fallback
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
- „Öffnen mit…“-Integration: per Dateimanager übergebene Dateien landen direkt in der Queue
- Native Fensterdekorationen des Desktops mit klassischer App-Menüleiste
- Breeze-Dark-Theme im AME-Stil oder natives System-Theme (Auswahl wird gemerkt)

## Voraussetzungen

- `python` (3.11+)
- `python-pyqt6`
- `ffmpeg` (inkl. `ffprobe`) im `PATH`
- *Optional (für optische Datenträger)*: `cdparanoia` (Audio-CDs), `lsdvd` (DVD-Strukturen), `libbluray` (Blu-ray-Playlists), `libdvdcss` (CSS-DVDs), `libaacs` (AACS-Blu-rays)

> **Fehlende Komponenten nachinstallieren:** Der Ripper-Dialog prüft beim Öffnen, welche der
> optionalen Werkzeuge und Bibliotheken auf dem System vorhanden sind, und bietet eine
> Schaltfläche „Fehlende Komponenten installieren…“ an. Die Distributionsfamilie wird aus `ID`
> und `ID_LIKE` in `/etc/os-release` abgeleitet (deckt damit auch Ableger wie CachyOS,
> EndeavourOS, Garuda, Linux Mint, TUXEDO OS, Pop!_OS, Bazzite oder Nobara ab), die
> Kennwortabfrage läuft grafisch über `pkexec`. Vor dem Ausführen wird der vollständige Befehl
> angezeigt. Pakete, die auf dem System nicht auffindbar sind, werden übersprungen und einzeln
> benannt, statt den ganzen Lauf scheitern zu lassen. Fremdquellen (RPM Fusion, AUR) schaltet
> LME nicht eigenmächtig frei. Unter Debian, Ubuntu und Mint wird libdvdcss über `libdvd-pkg`
> aus dem Quelltext gebaut; der dafür nötige debconf-Schritt läuft vorbeantwortet im selben
> privilegierten Aufruf, sodass die Kennwortabfrage nur einmal erscheint. Das braucht eine
> Internetverbindung und dauert einige Minuten; der Fortschritt steht im Protokoll.
> Unter Fedora prüft LME, ob RPM Fusion (free) eingerichtet ist; ist es das nicht, erscheint ein
> Hinweis mit der Bitte, es einzurichten — die übrigen Komponenten werden trotzdem installiert.
> Unter Arch entscheidet `pacman -Si` und damit die tatsächliche Lage auf dem Rechner, ob ein
> Paket aus einer eingerichteten Quelle kommt oder nur im AUR liegt: CachyOS, EndeavourOS oder
> Garuda führen vieles in eigenen Quellen, und das wird so auch erkannt. Der Bestätigungsdialog
> nennt zu jedem Paket seine Quelle. Was nirgends zu finden ist, wird als AUR-Fall gemeldet —
> LME baut keine AUR-Pakete, nennt aber den passenden Befehl, falls ein AUR-Helfer vorhanden ist.

> **Kopiergeschützte Blu-rays:** LME bringt keine Entschlüsselungsschlüssel mit und lädt auch keine
> herunter. Unverschlüsselte Discs und BDMV-Ordner funktionieren ohne Zusatz. Für AACS-geschützte
> Discs sucht `libaacs` eine `KEYDB.cfg` unter `$XDG_CONFIG_HOME/aacs/` (Vorgabe `~/.config/aacs/`)
> und in den Verzeichnissen aus `$XDG_CONFIG_DIRS` (Vorgabe `/etc/xdg/aacs/`); LME durchsucht alle
> diese Orte und meldet im Ripper-Dialog, was fehlt. Das Bereitstellen solcher Schlüssel ist Sache
> der Nutzerin bzw. des Nutzers und in manchen Rechtsordnungen (u. a. Deutschland, § 95a UrhG)
> nicht zulässig. Discs mit zusätzlichem BD+-Schutz benötigen darüber hinaus `libbdplus`.

## Direkt starten (ohne Installation)

```bash
python main.py
```

## Als Arch-Paket bauen und installieren

Im entpackten Ordner:

```bash
makepkg -si
```

Danach erscheint **Linux Media Encoder** im Anwendungsmenü und ist über den
Befehl `linux-media-encoder` startbar.

Paket entfernen:

```bash
sudo pacman -R linux-media-encoder
```

## Lizenz

MIT
