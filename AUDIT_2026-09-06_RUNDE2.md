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

## Nachtrag — Blu-ray an echter Hardware geprüft

Nach Abschluss des Berichts wurde das Laufwerk angeschlossen. Geprüft an
**PIONEER BD-RW BDR-UD03** (`/dev/sr0`) mit der **AACS-verschlüsselten** Disc
`INFERNO_2016`. Damit sind die BD-Korrekturen beider Runden nicht mehr nur
durch Attrappen belegt.

| Prüfung | Ergebnis |
|---|---|
| AACS | **erkannt und entschlüsselt** (`/etc/xdg/aacs/KEYDB.cfg`, BD+ auf dieser Disc nicht vorhanden) |
| Analyse der Disc | **5,8 s**; Hauptfilm korrekt mit **121,6 min**, 1920×1080, 4 Ton-, 5 Untertitelspuren |
| Zweistufiger Rip | gewählte **DTS-Spur 2** und **PGS-Untertitel 1** überstehen Stufe 1 und werden in Stufe 2 korrekt als Spur 0 wiedergefunden |
| `-playlist -1` | von libbluray als Vorgabetitel akzeptiert, `rc=0` |

**Ein Verdacht wurde widerlegt, nicht bestätigt:** `_probe_bluray_playlist()`
lässt das Argument bei negativen Werten weg (`optical_media.py:860`),
`build_bluray_rip_args()` schreibt dagegen `-playlist -1`. Das sah nach einem
Fehler aus — die Messung an der Disc zeigt, dass libbluray `-1` als
Vorgabetitel annimmt. Kein Handlungsbedarf.

### ⚠️ Bekannte Einschränkung — bewusst so belassen

Am **physischen Laufwerk** bietet LME nur **einen** Titel an, `bd_info` meldet
aber **49 HDMV- und 2 BD-J-Titel**. `list_bluray_playlists()` liest
`BDMV/PLAYLIST/*.mpls` und braucht dafür ein offenes Dateisystem, das ein
Laufwerk nicht hat: leere Liste, Rückfall auf libblurays Vorgabetitel.

**Folge: Bonusmaterial ist von einer physischen Blu-ray nicht rippbar** — nur
aus einem Ordner oder einer ISO. Nebeneffekt: die Korrektur „Hauptfilm jenseits
der ersten 40 Playlists" aus Runde 1 kann am Laufwerk **nie** greifen, weil die
Liste 0 Einträge hat und nicht mehr als 40.

Aufzählen wäre möglich — `ffprobe -playlist 1 -i bluray:/dev/sr0` liefert den
Film sauber, ganz ohne Dateisystem —, kostet aber gemessene **2,46 s pro
Playlist** an diesem Laufwerk: 40 Stück wären 98 s statt der heutigen 6 s.
**Nicht umgesetzt; Dominik zieht den schnellen Weg vor. Nicht ohne Rückfrage
nachrüsten.**

Nicht LME zuzurechnen: FFmpeg gibt für diese Disc **weder Sprach-Tags noch
Kapitel** heraus (`tags={}` bereits auf ffprobe-Ebene). Die Anzeige „Unbekannt"
gibt das korrekt wieder, statt etwas zu erfinden.

## Grenzen

- **DVD-Analysedauer weiterhin ungemessen.** `scan_dvd_source()` ruft für
  **jeden** Titel einzeln `ffprobe -f dvdvideo` auf; gegen einen Ordner sind das
  35 ms. Aus dem BD-Wert hochgerechnet wären es an echter Hardware ~2,5 s pro
  Titel, also **~75 s bei einer 30-Titel-DVD**. Die Analyse läuft im Hintergrund
  und ist jederzeit abbrechbar (Prüfung des Abbruchsignals alle 100 ms), die
  Anwendung blockiert also nicht. **Entscheidung: erst an einer echten DVD
  messen, vorher nichts ändern** — die Zahl ist hochgerechnet, nicht gemessen.
- Nicht geprüft: BD+, CSS, zerkratzte Discs, Schichtwechsel, BD-J-Titel.
- Das Playlist-Limit und die ISO-Signaturheuristik bestehen unverändert fort.

Dieser Bericht ist kein Nachweis, dass die Anwendung insgesamt fehlerfrei ist.

## Installation

Systemweit läuft weiterhin **1.11.2-1**; die Installation verlangt das
Administratorpasswort.

```sh
sudo pacman -U /home/domi/Projekte/linux-media-encoder/linux-media-encoder-1.12.1-1-any.pkg.tar.zst
```
