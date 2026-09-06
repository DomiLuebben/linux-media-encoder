# Linux Media Encoder — Ripping-Audit, zweiter Durchgang (06.09.2026)

Version **1.12.1-1**. Ausgangspunkt: Commit `75743d9` (1.12.0) plus ein
unfertiger Arbeitsstand aus einer abgebrochenen Codex-Sitzung. Dieser Bericht
deckt zwei Dinge ab: die Fertigstellung des übernommenen Arbeitsstands und eine
eigene kritische Nachprüfung desselben.

## Teil 1 — Übernommener Arbeitsstand (Codex, abgebrochen)

Die Sitzung endete nach dem Satz „Ich mache noch einen vollständigen Durchlauf
über die Warteschlange und prüfe die DVD-Vorschau; danach baue ich das
korrigierte Paket." Weder Versionssprung noch Paketbau noch Commit lagen vor.
Inhaltlich enthielt der Arbeitsbaum diese Korrekturen:

- `lsdvd` wurde ohne `-x` aufgerufen und lieferte deshalb **keine Ton- und
  Untertitelinformationen**; die Stream-Nummern aus `lsdvd` waren zudem
  1-basiert, FFmpeg zählt ab 0 — die Auswahl war um eins verschoben.
- Kapitel hatten keine Startzeit (`start_sec`).
- Ein Wechsel der Exportvorgabe verwarf die Disc-Zuordnung des Jobs
  (Titelnummer, Spuren, Transportargumente).
- Die Vorschau-Abfrage im Export-Dialog reichte den Disc-Pfad ohne Transport an
  `ffprobe` — bei einem VIDEO\_TS-Ordner scheiterte das mit *Is a directory*,
  die Vorschau blieb still leer.
- Stufe 2 eines zweistufigen Disc-Jobs übersprang die angeforderte
  KI-Untertitelerzeugung.
- Die Audioextraktion der Untertitel-Pipeline las immer die erste Tonspur der
  Rohquelle statt der gewählten.
- Ein abgebrochenes ISO-Abbild ersetzte die vorhandene Zieldatei.
- Schließen des Dialogs beendete einen laufenden Rip nicht.
- Direkt-Rip (Video, ISO) ohne Überschreibschutz.
- `FFmpegWorker.stop()` griff nur im Zustand `Running`, nicht bei `Starting`.

## Teil 2 — Eigene Nachprüfung: fünf Befunde im übernommenen Stand

Alle fünf sind durch je einen Test abgedeckt, der ohne die Korrektur **rot**
wird (gegengeprüft an einer zurückgebauten Kopie des Arbeitsbaums).

### 🔴 Befund 1 — Ein Patch landete in der falschen Methode; „zweistufig" wurde nicht mehr gespeichert

`_confirm_rip_outputs()` wurde mitten in `_on_two_stage_toggled()` eingefügt.
Dabei rutschte die abschließende Zeile

```python
QSettings(...).setValue("two_stage_rip", bool(checked))
```

ans Ende von `_confirm_rip_outputs()` — **hinter ein `return`**. Zwei Folgen:
`_on_two_stage_toggled()` speicherte die Einstellung nicht mehr (die Wahl
„zweistufig rippen" war nach jedem Programmstart wieder weg), und in
`_confirm_rip_outputs()` stand unerreichbarer Code, der einen dort gar nicht
existierenden Namen `checked` benutzt. Die 263 Tests des Arbeitsstands liefen
grün darüber hinweg, weil kein Test die Persistenz prüft.

**Behoben:** Zeile zurück in `_on_two_stage_toggled()`. Zusätzlich prüft jetzt
ein Skript über alle Projektdateien auf Anweisungen hinter `return`/`raise`/
`break`/`continue` — genau diese Fehlerklasse. Aktueller Stand: keine Fundstelle.

### 🟠 Befund 2 — Fehlertoleranz wurde als Disc-Eigenschaft eingestuft und dadurch von „Einstellungen auf alle anwenden" ausgesperrt

`ignore_errors` war in `DISC_SETTING_KEYS` aufgenommen und damit auch in
`SOURCE_SETTING_KEYS` — der Liste, die beim Kopieren auf andere Jobs bewusst
verworfen wird. Die Fehlertoleranz ist aber ein Kontrollkästchen für **jeden**
Job, auch für reine Dateiquellen (`mainwindow.py:494`,
`export_settings_dialog.py:429`). Ein Nutzer, der sie setzt und „auf alle
anwenden" drückt, bekam sie stillschweigend nicht übertragen.

**Behoben:** zwei getrennte Schlüsselgruppen statt einer.
`preserve_disc_settings()` (Vorgabenwechsel) rettet Identität **und**
Fehlertoleranz; das neue `preserve_source_identity()` (Kopieren auf andere Jobs)
rettet nur die Identität des Zieljobs. Beide Anforderungen gelten jetzt
gleichzeitig — vorher schloss die eine die andere aus.

### 🟠 Befund 3 — Datenträger ohne verwertbares Label ergab die versteckte Datei `.iso`

Der neue Helfer `_safe_disc_label()` wurde in `_start_iso_dump()` nicht benutzt;
dort stand weiterhin der alte Ausdruck ohne Rückfallnamen. Ein Label, das nur aus
Sonderzeichen besteht, wurde zu einem leeren Namen — das Abbild landete als
`.iso` im Zielordner, für den Nutzer unsichtbar.

**Behoben:** `_safe_disc_label(label, fallback=...)` mit Rückfallnamen, an beiden
Stellen benutzt.

### 🟠 Befund 4 — Der Audio-CD-Direkt-Rip überschrieb weiterhin kommentarlos

Der Überschreibschutz wurde für Video- und ISO-Rip nachgerüstet, für den
CD-Zweig desselben Dialogs nicht. `AudioCdRipWorker` ersetzt vorhandene Dateien
ohne Rückfrage.

**Behoben:** derselbe Schutz auch im CD-Zweig. Damit Dialog und Worker nicht
auseinanderlaufen können, ist der Zieldateiname jetzt eine einzige Funktion
(`disc_rip_worker.audio_cd_output_filename()`), die beide benutzen — ein
eigener Namensbau im Dialog hätte die Prüfung wertlos gemacht. Ein Test hält
Worker und Dialog auf demselben Namen fest.

### 🟡 Befund 5 — Rückfall-Titelsuche konnte 16 Minuten blockieren

`probe_dvd_titles_ffprobe()` wurde von 15 auf 99 Titel erweitert. Findet die
Quelle gar keinen Titel (keine DVD, unlesbare Disc), lief jeder der 99 Versuche
in den 10-Sekunden-Zeitablauf: bis zu 16 Minuten mit stehendem
Fortschrittsbalken. Vorher waren es max. 2,5 Minuten.

**Behoben:** Zeitschranke von 30 s für die ergebnislose Phase — billige
Fehlschläge (sofortiger Rückgabewert ungleich 0) bleiben davon unberührt, sodass
ein fehlschlagender Titel 1 die Suche weiterhin nicht abbricht.

### Nebenbefund — zwei Tests hingen an einer Datei, die es im Klon nicht gibt

`test_rip_deep.py` benutzte `test_input_lme.mp4` als zweite Videoquelle. Diese
Datei ist eine Encoder-Ausgabe aus einem früheren Testlauf und wird von
`.gitignore` (`*_lme.*`) erfasst — sie liegt in keinem Klon des Projekts. Da
`_add_file_to_queue()` die Existenz nicht prüft, wäre der Test anderswo
stillschweigend gegen einen Phantompfad gelaufen statt zu scheitern.
Ersetzt durch `second_video_source()`, das sich eine temporäre Kopie von
`test_input.mp4` anlegt. Gegengeprüft: die Suite bleibt vollständig grün, wenn
`test_input_lme.mp4` nicht vorhanden ist.

### Nebenbefund — `manual_ui_check.py` war seit dem 07.07.2026 defekt

Die Sichtprüfung erwartete vier Menüs, die Anwendung hat seit v1.7.0 sechs
(`Bearbeiten` und `Warteschlange` kamen hinzu). Das Skript brach mit
`AssertionError` ab, bevor es einen einzigen Dialog erreichte. Es ist weder Teil
von `unittest discover` (Name beginnt nicht mit `test_`) noch im Paket, deshalb
fiel es zwei Monate nicht auf. Zusicherung berichtigt, Skript läuft wieder durch.

## Prüfstand

| Prüfung | Ergebnis |
|---|---|
| `QT_QPA_PLATFORM=offscreen python3 -m unittest discover` | **274/274 grün** (263 übernommen + 11 neue) |
| Neue Tests gegen zurückgebauten Stand | 6 Fehlschläge über alle 5 Befunde — die Tests greifen wirklich |
| Echter zweistufiger DVD-Rip (FFmpeg, Test-DVD) | Englisch bleibt `eng`, Deutsch bleibt `ger`, je 2 Kapitel erhalten |
| Echte Audioextraktion der Untertitel-Pipeline von DVD | 16 kHz mono MP3, je Spur **unterschiedlicher Inhalt** (MD5 verglichen) |
| Vorschau-Abfrage des Export-Dialogs gegen die Test-DVD | `rc=0`, Dauer 3,0 s, Video + `eng` + `ger` erkannt |
| Ripper-Dialog offscreen mit Test-DVD | Titel, beide Tonspuren mit 0-basierten Nummern, UI-Zustand sauber |
| `manual_ui_check.py` offscreen | läuft vollständig durch |
| Suche nach Code hinter `return`/`raise`/`break`/`continue` | 0 Fundstellen |
| `updpkgsums` + `makepkg -f` | Paket `1.12.1-1` gebaut |
| Paketierte Python-Quellen gegen Arbeitsbaum | bytegleich |

Die Meldung `ExcessNotificationGeneration` im Testlauf stammt vom
Benachrichtigungsdienst des Desktops, der wiederholte Testblasen drosselt. Sie
ist kein fehlgeschlagener Test.

## Grenzen

**Kein optisches Laufwerk verfügbar.** Alle Disc-Prüfungen liefen gegen einen
VIDEO\_TS-Ordner, nicht gegen `/dev/sr*`. Nicht nachgeprüft sind daher:

- Blu-ray insgesamt. Sämtliche BD-Korrekturen (Playlist 00000, BDMV-Basispfad,
  libbluray-Vorgabetitel, `bluray:`-Vorschau) sind **ausschließlich durch Tests
  mit Attrappen belegt**, nie an einer Disc.
- AACS/BD+, CSS, zerkratzte Discs, Schichtwechsel.
- **Die Laufzeit der neuen DVD-Analyse an echter Hardware.** `scan_dvd_source()`
  ruft jetzt für **jeden** Titel einzeln `ffprobe -f dvdvideo` auf. Gegen den
  Ordner sind das 35 ms pro Titel; an einem physischen Laufwerk, das für jeden
  Titel neu positionieren muss, kann eine DVD mit 30–40 Titeln spürbar länger
  brauchen als die eine `lsdvd`-Abfrage von vorher. Die Analyse läuft im
  Hintergrund und ist jederzeit abbrechbar (Prüfung des Abbruchsignals alle
  100 ms), die Anwendung blockiert also nicht — aber die Wartezeit ist real und
  bisher ungemessen. **Das ist die erste Stelle, die an echter Hardware
  nachzumessen ist.**

Das Playlist-Limit und die ISO-Signaturheuristik bestehen unverändert fort.
Dieser Bericht ist kein Nachweis, dass die Anwendung insgesamt fehlerfrei ist.

## Installation

Systemweit läuft weiterhin **1.11.2-1**; die Installation verlangt das
Administratorpasswort.

```sh
sudo pacman -U /home/domi/Projekte/linux-media-encoder/linux-media-encoder-1.12.1-1-any.pkg.tar.zst
```
