# Auftragsdokument — CD/DVD/BD-Ripper für den Linux Media Encoder

**Fassung:** 2026-08-23 · **Prüfung des Gemini-Plans durch Claude/Opus 5**
**Projekt:** `/home/domi/Projekte/linux-media-encoder` (Git, Remote `github.com/DomiLuebben/linux-media-encoder`, Branch `main`)

> Dieses Dokument **ersetzt** Geminis „Implementation Plan – CD/DVD/BD Ripper".
> Die Richtung stimmt, die Modulaufteilung ist tragfähig. Was fehlte, sind die
> Stellen, an denen die Umsetzung tatsächlich scheitert: falsch angenommene
> FFmpeg-Fähigkeiten, ein nicht existierender Weg für die Titel-Enumeration,
> die Verschlüsselung (CSS/AACS), der bestehende Bauvertrag des PKGBUILD und
> die Tatsache, dass **in diesem Rechner kein optisches Laufwerk steckt**.

---

## 0. Verifizierter Ist-Zustand (selbst gemessen, nicht übernommen)

| Sache | Befund |
|---|---|
| Version | `version.py` = **1.9.0**, `PKGBUILD` `pkgver=1.9.0` → Sprung auf **1.10.0** ist korrekt |
| Testsuite | `QT_QPA_PLATFORM=offscreen python3 -m unittest discover` → **137 Tests, OK** (die in `ai-knowledge.md` genannten „124" sind veraltet) |
| Git | sauberer Arbeitsbaum, letzter Commit `0fc1204` |
| i18n | `i18n.py`, `translations.py`, `test_i18n.py`, `README.de.md`, `README.fr.md` **existieren** — Geminis `[MODIFY]` ist richtig |
| Atomares Schreiben | **existiert bereits** in `ffmpeg_worker.py:37` (`.lme_tmp_<uuid><ext>`) + `os.replace()` in `_handle_finished` |
| `src/` | enthält **von `makepkg` erzeugte Symlinks** und steht in `.gitignore` → **kein Arbeitsschritt** |
| Menüs | `Datei`, **`Bearbeiten` (existiert bereits, enthält „Video verkürzen (Schnitt)…")**, `Design`, `Ansicht`, `Warteschlange`, `Hilfe` |
| Tastenkürzel | **es gibt bisher keines** — `Strg+D` ist frei |
| FFmpeg | 9.0.1, gebaut mit `--enable-libdvdnav --enable-libdvdread --enable-libbluray` |
| Demuxer `dvdvideo` | vorhanden |
| Protokoll `bluray:` | vorhanden |
| FFmpeg + Audio-CD | **nicht möglich** — `ffmpeg -devices \| grep cdio` ist leer, libcdio ist nicht einkompiliert |
| `libdvdcss` | 1.6.0 installiert → CSS-DVDs lesbar |
| `libaacs` | **NICHT installiert** → verschlüsselte Blu-rays sind nicht lesbar |
| Werkzeuge da | `cdparanoia`, `cd-info`, `bd_info` (aus libbluray), `eject` (util-linux), `udevadm`, `lsblk`, `dd` |
| Werkzeuge fehlen | `lsdvd`, `dvdbackup`, `ddrescue`, `xorriso`, `dvdauthor` — alle in `[extra]` verfügbar |
| **Optisches Laufwerk** | **keines vorhanden** (`/dev/sr*` existiert nicht, kein `sr` in `/sys/block`) |
| Testmaterial | keine DVD/BD/ISO im Projekt; die einzige ISO auf dem Rechner ist ein Spiele-Abbild |

---

## 1. Was am vorgelegten Plan falsch ist

### 1.1 `[NEW] Symlinks in src/` — kein Arbeitsschritt
`src/` ist das Bauverzeichnis von `makepkg`. Die Symlinks entstehen automatisch aus
`source=(...)`, und `.gitignore` enthält `src/`. Manuell angelegte Symlinks landen
nie im Repository. **Streichen.**

### 1.2 `sha256sums` fehlt im Plan — das bricht `makepkg` garantiert
Das PKGBUILD arbeitet **nicht** mit `source=()` (das war ein alter Stand), sondern mit
einer vollen `source=(...)`-Liste **plus 17 `sha256sums`**. Wer Dateien in `source=()`
aufnimmt, ohne die Summen nachzuziehen, bekommt „ERROR: Integrity checks are missing".

**Vorgabe:** nach jeder Quelldatei-Änderung im Projektordner

```bash
updpkgsums
```

(aus `pacman-contrib`) ausführen und das Ergebnis committen. Danach `makepkg -f` als Beleg.

### 1.3 Doppelter Menüeintrag
Der Plan will den Ripper **gleichzeitig** in `Datei` und `Bearbeiten`. `Bearbeiten`
existiert bereits und ist thematisch der Videoschnitt. **Genau ein Eintrag**, in `Datei`,
direkt nach „Datei(en) hinzufügen…", plus Toolbar-Knopf. `Strg+D` bleibt.

### 1.4 Falscher unittest-Aufruf
`python3 -m unittest test_optical_media.py` erwartet einen **Modulnamen**, keinen Dateinamen.
Richtig:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest test_optical_media -v
```

### 1.5 Atomares Schreiben nicht neu erfinden
`.lme_tmp_*` + `os.replace()` steckt bereits im `FFmpegWorker`. Eine zweite, eigene
Implementierung im Rip-Worker läuft garantiert auseinander (genau das Muster, das im
Dojo-Projekt schon dreimal zugeschlagen hat). **Für alles, was FFmpeg macht, den
bestehenden `FFmpegWorker` benutzen.** Eigener Code nur für `cdparanoia` und `dd`.

### 1.6 „Titelerkennung via FFmpeg" gibt es nicht
Der `dvdvideo`-Demuxer **kann keine Titel auflisten** — er spielt einen Titel ab, den man
ihm vorgibt. Dasselbe für `bluray:`. Der Plan setzt eine Fähigkeit voraus, die nicht
existiert. Siehe Abschnitt 3.2 für den korrekten Weg.

### 1.7 Verschlüsselung kommt im ganzen Plan nicht vor
Handelsübliche DVDs sind CSS-, Blu-rays AACS-verschlüsselt. Ohne `libdvdcss` bzw.
`libaacs` + `KEYDB.cfg` scheitert das Lesen — mit einer FFmpeg-Fehlermeldung, die
niemand versteht. Das gehört in `optdepends`, in eine Laufzeitprüfung und in eine
verständliche Fehlermeldung. Siehe 3.5.

### 1.8 Modus-Beschreibung widersprüchlich
Die Kopfzeile verspricht „ins Wunschformat konvertieren", Modus 2 heißt aber
„Direkt rippen (Verlustfrei / Remux)". Damit baut man am Ende zwei Preset-Oberflächen.

**Festlegung:**
* **Modus 1 „In Warteschlange einreihen"** = der einzige Weg zum Transcodieren. Die Titel
  landen als normale Jobs in der Queue und benutzen die vorhandenen LME-Presets.
* **Modus 2 „Direkt rippen"** = ausschließlich verlustfreies Remuxen nach MKV
  (bzw. Encodieren bei Audio-CD) ohne Umweg über die Queue. **Keine eigene Preset-UI.**
* **Modus 3 „1:1 ISO-Abbild"**.

---

## 2. Was den Rechner betrifft — bitte vorher lesen

**Es steckt kein optisches Laufwerk in diesem Rechner.** Damit gilt:

* Der komplette Audio-CD-Pfad (`cdparanoia`) ist **hier nicht abnehmbar**.
* Der Laufwerks-Scan ist nur gegen erfundene `sysfs`-Bäume prüfbar.
* Der DVD-Pfad **ist** abnehmbar — über eine selbst erzeugte, unverschlüsselte
  Test-DVD (Abschnitt 5.2). Das ist Pflicht, nicht optional.
* Der Blu-ray-Pfad ist **nicht** abnehmbar (kein Material, kein `libaacs`).

**Regel:** Was nicht am laufenden Programm belegt wurde, wird im Abschlussbericht
als *nicht abgenommen* gekennzeichnet — nicht als erledigt gemeldet.

---

## 3. Fachliche Vorgaben (hier entstehen sonst die Fehler)

### 3.1 `cdparanoia`: TOC steht auf **stderr**
Selbst gemessen: `cdparanoia -Q` schreibt die Titelliste nach **stderr**, stdout bleibt
leer, und ohne Laufwerk ist der Rückgabewert **1**. Wer `stdout` parst, bekommt immer
eine leere Liste — und der Fehler fällt erst am echten Laufwerk auf.

```python
r = subprocess.run(["cdparanoia", "-Q", "-d", device],
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                   text=True, timeout=30)
```

Umrechnung: **75 Sektoren = 1 Sekunde** (CDDA).

### 3.2 Titel-Enumeration — der einzige Weg, der funktioniert

**DVD (Primärweg):** `lsdvd -Oy <pfad>` liefert ein **Python-Literal** und ist damit
ohne eigenen Parser auswertbar. Paket `lsdvd` aus `[extra]`, als `optdepends`.

```python
import ast
data = ast.literal_eval(stdout.split("=", 1)[1])   # lsdvd gibt "lsdvd = {...}"
```

**DVD (Fallback ohne `lsdvd`):** Schleife `ffprobe -v error -f dvdvideo -title N -i <pfad>
-show_format -show_streams -of json` für N = 1…99; Titel, bei denen ffprobe fehlschlägt,
existieren nicht. Langsam, aber abhängigkeitsfrei.

**Blu-ray:** `bd_info <pfad>` (kommt mit `libbluray`, **ist installiert**) für die
Playlist-Liste; alternativ `ffprobe -playlist N -i bluray:<pfad>`.

> **Ausdrückliche Vorgabe: den Parser nicht raten.** Erst die **echte Ausgabe**
> von `lsdvd -Oy` und `bd_info` gegen die Test-DVD aus 5.2 einfangen, wörtlich als
> Fixture in `test_optical_media.py` ablegen, dann den Parser dagegen schreiben.
> Erfundene Ausgabeformate sind hier die wahrscheinlichste Fehlerquelle.

### 3.3 Verifizierte FFmpeg-Optionen (bitte wörtlich übernehmen)

Beides sind **Input-Optionen und stehen vor `-i`** — selbst gegengeprüft, beide Formen
werden von FFmpeg 9.0.1 angenommen.

**`dvdvideo`-Demuxer:**
`-title <1-99>` (0 = auto) · `-chapter_start <1-99>` · `-chapter_end <0-99>` (0 = Ende) ·
`-angle <1-9>` · `-pgc` · `-pg` · `-preindex <bool>` (genaue Kapitelmarken, 2 Durchläufe, langsam) ·
`-trim <bool>` (Standard true) · `-region` · `-menu`

```
ffmpeg -y -f dvdvideo -title 3 -chapter_start 1 -chapter_end 0 -i /pfad/zur/DVD  …
```

**`bluray:`-Protokoll:**
`-playlist <int>` · `-angle <int>` · `-chapter <int>`
**Achtung: nur Start-Kapitel, es gibt kein `-chapter_end`.** Ein Kapitelbereich muss
über `-to` nach dem Input gelöst werden.

```
ffmpeg -y -playlist 811 -i bluray:/pfad/zum/BDMV-Wurzelverzeichnis  …
```

### 3.4 Container-Regeln — sonst bricht das Remuxen ab

* **PGS (`hdmv_pgs_subtitle`) und DVD-Untertitel (`dvd_subtitle`) lassen sich nicht in MP4 muxen.**
  Sobald eine Untertitelspur gewählt ist → **MKV erzwingen** und in der UI begründen.
* **DTS-HD MA / TrueHD `copy`** ebenfalls nur MKV.
* Der Direkt-Rip (Modus 2) schreibt deshalb grundsätzlich `.mkv`.

### 3.5 Verschlüsselung sichtbar machen

* `optdepends`: `libdvdcss` (CSS-DVDs), `libaacs` (AACS-Blu-rays), `lsdvd`, `ddrescue`.
* **Laufzeitprüfung** beim Öffnen einer Quelle: schlägt das Lesen fehl **und** fehlt
  die jeweilige Bibliothek (`ctypes.util.find_library("dvdcss")` /
  `find_library("aacs")`), dann eine eigene, verständliche Meldung ausgeben statt
  der FFmpeg-Rohmeldung. Für AACS zusätzlich der Hinweis, dass `libaacs` ohne
  `~/.config/aacs/KEYDB.cfg` nichts nützt.
* **Ebenso zur Laufzeit prüfen, nicht annehmen:** `ffmpeg -demuxers` auf `dvdvideo`
  und `ffmpeg -protocols` auf `bluray`. Nicht jedes Arch-FFmpeg ist so gebaut wie
  das hier installierte. Fehlt die Fähigkeit → Modus im Dialog deaktivieren, nicht
  erst beim Start scheitern.

### 3.6 ISO-Abbild

* **Für Audio-CDs sperren.** Eine CDDA hat kein Dateisystem; `dd` erzeugt dort Müll.
* Nicht blind bis EOF lesen — viele Laufwerke laufen am Discende in I/O-Fehler.
  Größe vorher bestimmen (`blockdev --getsize64 /dev/srX`, bzw. Sektorzahl aus dem
  ISO-9660-Primary-Volume-Descriptor) und exakt so viele Blöcke lesen.
* `dd status=progress` schreibt den Fortschritt nach **stderr**. `ddrescue` als
  robustere Alternative anbieten, wenn installiert.
* Die ISO einer CSS-DVD bleibt **verschlüsselt** — reines Backup, nicht abspielbar
  ohne libdvdcss. Das muss in der UI stehen, sonst ist es ein Fehlerbericht.

### 3.7 Audio-CD: Metadaten und Fortschritt

* **Kein Netzwerkzugriff.** Der Plan sagt „inkl. Metadaten-Tagging", nennt aber keine
  Quelle — dabei wird sonst MusicBrainz/freedb erfunden, samt neuer Abhängigkeit und
  ungefragtem Netzverkehr. Erlaubt ist ausschließlich **CD-TEXT** über das bereits
  installierte `cd-info` (libcdio); ist keins vorhanden, bleiben die Felder leer und
  **in der Tabelle editierbar**. Tags dann über `ffmpeg -metadata title=… artist=…`.
* **Fortschritt:** die Fortschrittsanzeige von `cdparanoia` (Smiley-Balken auf stderr)
  nicht parsen. Pro Track `cdparanoia "N-N" <tmp>.wav` in eine `.lme_tmp_*`-Datei,
  Gesamtfortschritt = fertige Tracks ÷ Gesamtzahl, danach Encoding über den
  bestehenden `FFmpegWorker`.
* **Kein QProcess-Pipe-Gebastel** (`setStandardOutputProcess`). Zwei gekoppelte
  Prozesse verdoppeln Abbruch- und Fehlerbehandlung; der Zwischenschritt über eine
  temporäre WAV ist hier eindeutig der billigere Weg.

---

## 4. Integration in den Bestand — die konkreten Bruchstellen

### 4.1 `FFmpegWorker.start()` prüft die Existenz der Eingabedatei

```python
if not os.path.exists(self.input_file):
    self._emit_finished(False, f"Eingabedatei existiert nicht: {self.input_file}")
    return
```

Für `bluray:/pfad` ist das **falsch** und der Worker startet nie.
**Vorgabe:** `input_file` bleibt der echte Pfad (Gerät, ISO-Datei oder Ordner); die
`bluray:`-URL bzw. `-f dvdvideo` stehen **nur in den Argumenten**. Kein Sonderfall im Worker.

Die Einfügung von `-progress -` sucht das **erste `-i`** und schiebt danach ein — mit
Vor-Input-Optionen funktioniert das unverändert. Argumentreihenfolge einhalten.

### 4.2 Queue-Integration braucht eine Erweiterung in `presets.py`

`presets.get_ffmpeg_args()` baut die Zeile fest als `["-y", …, "-i", input_file, …]`.
Es gibt **keinen Haken für Optionen vor dem Input** — ein Disc-Job kann so nicht durch
die normale Warteschlange laufen. Das ist der riskanteste Teil des ganzen Vorhabens.

**Vorgabe:**
* neuer Einstellungsschlüssel `settings["input_args"]` (Liste von Zeichenketten),
* in `get_ffmpeg_args()` unmittelbar **vor** `-i` eingesetzt,
* **nicht** in `presets.TRANSIENT_SETTING_KEYS` aufnehmen — sonst geht er beim
  Sitzungsspeichern verloren,
* leere/fehlende Liste verhält sich exakt wie heute (Regressionstest dafür schreiben).

### 4.3 Sitzungs-Persistenz

`_save_session_state()` serialisiert **nur** `input_file`, `output_dir`, `output_file`,
`settings`, `status`. Alles, was ein Disc-Job außerhalb von `settings` am Job hängen hat,
ist nach dem Neustart weg — der Job wird stillschweigend zu einem normalen Datei-Job
auf `/dev/sr0`.

**Vorgabe:** sämtliche Disc-Angaben (Quelle, Typ, Titelnummer, Stream-Auswahl) liegen
**in `settings`**. Beim Wiederherstellen: Quelle nicht mehr vorhanden → Status
„Bereit" behalten, aber vor dem Start prüfen und mit klarer Meldung abbrechen,
statt FFmpeg ins Leere laufen zu lassen.

### 4.4 `_prefetch_source_info()` darf Disc-Jobs nicht anfassen

Die Methode startet `ffprobe` **direkt auf `input_file`** (Timeout 15 s). Auf `/dev/sr0`
oder einem `VIDEO_TS`-Ordner ist das sinnlos und blockiert eine Viertelminute pro Job.
→ Für Jobs mit `settings["input_args"]` überspringen; Dauer und Maße kommen aus dem
Disc-Parser.

### 4.5 Drag & Drop — der heutige Zweig greift zuerst

```python
def dropEvent(self, event):
    for url in event.mimeData().urls():
        file_path = url.toLocalFile()
        if os.path.isfile(file_path):
            self._add_file_to_queue(file_path)
```

Eine ISO **ist** eine Datei und landet damit **heute schon** in der Queue. Ordner werden
stillschweigend ignoriert. Die Ripper-Erkennung muss deshalb **vor** dem
`os.path.isfile`-Zweig greifen, sonst passiert entweder nichts Neues oder beides.
Erkennung: Endung `.iso`/`.img` **und** ein Ordner, der `VIDEO_TS` oder `BDMV` heißt
oder enthält.

### 4.6 i18n — sonst bleibt der Dialog in allen Sprachen deutsch

`i18n.py` **schattiert die Qt-Klassen**. Der neue Dialog importiert seine Widgets
ausschließlich von dort:

```python
from i18n import (QDialog, QLabel, QPushButton, QCheckBox, QComboBox, QGroupBox,
                  QRadioButton, QLineEdit, QTextEdit, QProgressBar, QTableWidget,
                  QTableWidgetItem, QTabWidget, QMenu, QAction, QFileDialog,
                  QMessageBox, QWidget, tr)
```

Für Klassen **ohne** i18n-Hülle (z. B. `QSpinBox`, `QHeaderView`-Beschriftungen,
Tooltips über `setToolTip`) muss `tr(...)` explizit gerufen werden.

**Vertrag von `translations.py`**, den `test_i18n.py` erzwingt:
* `set(EN_US) == set(FR_FR)`, kein leerer Wert,
* **Format-Platzhalter identisch** zwischen Quellstring und beiden Übersetzungen,
* Schlüssel ist der **wörtliche deutsche Quelltext** inkl. Satzzeichen, „…",
  typografischer Anführungszeichen und `&&` in Menütexten.

**Zusätzlich ein Wächtertest:** Dialog in `en_US` und `fr_FR` aufbauen, danach
`i18n.missing_translations()` muss leer sein. **Diesen Wächter negativ gegenprüfen** —
einen Schlüssel absichtlich entfernen, sehen, dass der Test rot wird, dann zurück.
Ein Wächter, der nie rot war, prüft nichts.

---

## 5. Prüfstand

### 5.1 Vor dem ersten Handgriff

```bash
cp -a /home/domi/Projekte/linux-media-encoder /home/domi/Projekte/backups/linux-media-encoder-20260823-vor-ripper
```

Baseline festhalten: **137 Tests, OK.** Am Ende muss die Zahl ≥ 137 sein und alles grün.

### 5.2 Test-DVD selbst bauen — Pflicht, nicht optional

Ohne Laufwerk ist das der **einzige** Weg, den DVD-Pfad wirklich zu belegen.

```bash
sudo pacman -S --needed dvdauthor libisoburn lsdvd
```

```bash
ffmpeg -i test_input.mp4 -t 10 -target pal-dvd /tmp/lme-dvd/clip.mpg
dvdauthor -o /tmp/lme-dvd/dvdroot -t /tmp/lme-dvd/clip.mpg && dvdauthor -o /tmp/lme-dvd/dvdroot -T
xorriso -as mkisofs -dvd-video -o /tmp/lme-dvd/test.iso /tmp/lme-dvd/dvdroot
```

Damit sind belegbar: Ordner-Erkennung (`VIDEO_TS`), ISO-Erkennung, `lsdvd`-Parser,
Titel-/Kapitelanzeige, Remux nach MKV, Queue-Übergabe.
**Die echte `lsdvd -Oy`-Ausgabe dieser DVD gehört wörtlich als Fixture in den Test.**

### 5.3 Automatische Tests

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -v
```

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest test_optical_media test_i18n -v
```

**Harte Vorgabe: kein Test fasst Hardware an.** Kein `/dev/sr*`, kein Start von
`cdparanoia`, `ffmpeg` oder `dd`. Damit das überhaupt geht, müssen die
Erkennungsfunktionen ihre Wurzelverzeichnisse als Parameter annehmen
(`scan_drives(sysfs_root="/sys/block", dev_root="/dev")`), sonst sind sie nicht
testbar und Gemini schreibt am Ende Tests, die auf einem Rechner mit Laufwerk
anders ausgehen als auf diesem.

Abgedeckt sein müssen mindestens:
* Laufwerksscan gegen einen erfundenen `sysfs`-Baum in `tmp_path`,
* `cdparanoia -Q`-Parser gegen eine echte, wörtlich eingefangene Ausgabe (**stderr!**),
* `lsdvd -Oy`-Parser gegen die Fixture aus 5.2,
* Disc-Typ-Erkennung für `VIDEO_TS`, `BDMV`, Daten-ISO, leeres Laufwerk,
* **Befehlsgenerierung** als reine Funktionen (Argumentlisten vergleichen) — für
  DVD-Titel, DVD-Kapitelbereich, BD-Playlist, Audio-Track, ISO-Dump,
* die Regel „Untertitel gewählt ⇒ MKV",
* `get_ffmpeg_args()` **ohne** `input_args` erzeugt byteweise dieselbe Zeile wie heute,
* Wächtertest für fehlende Übersetzungen (negativ gegengeprüft).

### 5.4 Manuelle Abnahme — das Programm wirklich starten

Der Importtest unter `offscreen` findet keine Layoutfehler. Belegt werden muss:

1. `python3 main.py`, Ripper über Menü **und** Toolbar öffnen.
2. Denselben Dialog in `LME_LOCALE=en_US` und `LME_LOCALE=fr_FR` öffnen —
   Screenshot je Sprache, **kein deutscher Reststring**.
3. Test-ISO und `VIDEO_TS`-Ordner per Dialog **und** per Drag & Drop öffnen.
4. Einen Titel direkt rippen (MKV) und einen Titel in die Warteschlange geben,
   dort starten. Beide Zieldateien mit `ffprobe` gegenprüfen.
5. Dialog bei **leerem** Laufwerksangebot öffnen — es darf keine Ausnahme fliegen,
   und die Modi müssen sauber deaktiviert sein.

### 5.5 Paketbau

```bash
updpkgsums && makepkg -f
```

### 5.6 Was am Ende ehrlich als offen zu melden ist

* **Audio-CD-Pfad:** ohne Laufwerk nicht abnehmbar.
* **Blu-ray-Pfad:** ohne Material und ohne `libaacs` nicht abnehmbar.
* Beides gehört in den Abschlussbericht als *nicht abgenommen* — mit der Angabe,
  welcher konkrete Handgriff zur Abnahme fehlt.

---

## 6. Empfehlung zum Zuschnitt

Der Auftrag ist für einen Durchgang zu groß: drei neue Module, ein umfangreicher
Dialog, ein Eingriff in `presets.py`, drei Sprachen und der Paketbau. Erfahrungsgemäß
kippt dabei zuerst der Prüfstand, und danach ist nicht mehr auseinanderzuhalten,
welche Änderung ihn gekippt hat.

**Drei Pakete, jedes einzeln mit grünem Prüfstand und eigenem Commit:**

| Paket | Inhalt | Abnahme |
|---|---|---|
| **1** | `optical_media.py` + `test_optical_media.py` — reine Logik, Erkennung, Parser, Befehlsgenerierung. **Keine UI.** | Testsuite grün, Parser gegen echte Fixtures |
| **2** | `disc_ripper_dialog.py`, `disc_rip_worker.py` (nur `cdparanoia`/`dd`), Modus 2 + 3, i18n, Menü/Toolbar | Dialog in 3 Sprachen, Direkt-Rip der Test-DVD belegt |
| **3** | `presets.input_args`, Queue-Übergabe (Modus 1), Sitzung, Drag & Drop, README ×3, Version 1.10.0, PKGBUILD + `updpkgsums` | Queue-Job der Test-DVD läuft durch, `makepkg -f` grün |

Wird das in einem Zug umgesetzt, gilt dieselbe Vorgabe bloß strenger: nach jedem
Teilschritt die volle Suite laufen lassen, nicht erst am Ende.

---

## 6a. Nachprüfung der Umsetzung (Claude/Opus 5, 23.08.2026)

Umgesetzt wurde in einem Zug (Commit `330dbd4`, 153 Tests grün). Der Prüfstand war
grün, **drei der Parser waren es trotzdem nicht** — sie liefen gegen erfundene
Ausgabeformate, genau das, wovor Abschnitt 3.2 gewarnt hatte. `lsdvd`, `dvdauthor`
und `xorriso` wurden nie installiert, die Test-DVD aus 5.2 nie gebaut; die Fixtures
in `test_optical_media.py` waren Eigenerfindungen und haben den Fehler mitgetragen.

**Behoben:**

1. **`parse_lsdvd_output` las `t['video']['width'|'height'|'fps'|'aspect']`.**
   `lsdvd -Oy` legt diese Angaben **flach auf dem Track** ab; ein
   `video`-Wörterbuch gibt es nicht. Jeder Titel bekam damit stillschweigend
   720×576 @ 25 fps — bei einer NTSC-DVD (720×480 @ 29.97) schlicht falsch, ohne
   dass irgendetwas fehlschlug. Jetzt flach gelesen (verschachtelt bleibt
   Rückfall), `'16/9'` wird auf `'16:9'` normalisiert. Fixture auf das echte
   Format umgestellt, Wächter-Zusicherungen auf Maße/Bildrate ergänzt und
   **negativ gegengeprüft** (mit dem alten Zugriff wird der Test rot).

2. **`parse_bdinfo_output` parste ein Format, das `bd_info` nie ausgibt.**
   Gegenprobe an den Formatzeichenketten des installierten Programms: es kennt
   `Volume Identifier`, `AACS detected`, `HDMV titles` — aber **keine
   `Playlist:`-Zeilen mit Dauer, Kapitel-, Ton- und Untertitelangaben**. Die
   Torbedingung `"Playlist" in res.stdout` konnte nie wahr werden, der Parser war
   toter Code, und jede Blu-ray fiel auf einen Rückfall zurück, der **einen**
   Pseudo-Titel ohne Ton- und Untertitelspuren lieferte — die beworbene
   Playlist-/Multi-Audio-/PGS-Erkennung existierte praktisch nicht.
   Ersetzt durch: Playlist-Nummern aus `BDMV/PLAYLIST/*.mpls`, Inhalte je
   Playlist über `ffprobe -playlist N -i bluray:<pfad>`, Kurz-Playlists gefiltert
   (Verschleierung), Rückfall auf den Vorgabetitel bei Laufwerk/ISO. `bd_info`
   liefert jetzt nur noch das, was es wirklich kann: Datenträgername und
   AACS-Status — letzterer speist eine verständliche Fehlermeldung.

3. **ISO-Abbild ohne Größenangabe.** `IsoDumpWorker` wurde ohne
   `total_size_bytes` erzeugt → kein `count=` für `dd` (Lesefehler am Discende,
   siehe 3.6) und ein Fortschrittsbalken, der dauerhaft auf 0 % steht. Neu:
   `get_optical_media_size()` (`blockdev --getsize64`, Rückfall auf den
   ISO-9660-Primary-Volume-Descriptor), im Dialog übergeben.

4. **Nebenbefund:** `_inspect_iso_disc_type` gab für jede nicht erkannte ISO
   `DVD_VIDEO` zurück — damit landete auch ein Spiel- oder Installationsabbild im
   DVD-Titelparser. Jetzt `DATA_DISC`, Suchfenster von 1 auf 8 MB erweitert.

**Geprüft und in Ordnung:** Argumentreihenfolge und `input_args` in
`presets.py`, `bluray:`-URL nur in den Argumenten (der Existenzcheck des
`FFmpegWorker` greift also nicht ins Leere), Übergehen von `_prefetch_source_info`
bei Disc-Jobs, Drag-&-Drop-Reihenfolge, ISO-Modus für Audio-CDs gesperrt,
`cdparanoia`-Parser auf **stderr**, atomares Schreiben in beiden neuen Workern,
Laufzeitprüfung der FFmpeg-Fähigkeiten. Der i18n-Wächtertest wurde negativ
gegengeprüft und meldet fehlende Schlüssel tatsächlich.

**Prüfstand nach der Nachbesserung:** 158 Tests grün · `makepkg -f` erstellt
`linux-media-encoder 1.10.0-1` · Hauptfenster und Ripper-Dialog starten in
`de_DE`, `en_US` und `fr_FR` mit übersetzter Oberfläche.

**Weiterhin offen — nicht abgenommen:** Audio-CD-Pfad (kein Laufwerk),
Blu-ray-Pfad (kein Material, kein `libaacs`) und der DVD-Pfad am echten Medium
(Test-DVD aus 5.2 wurde nie gebaut, `lsdvd` ist nicht installiert — der
`lsdvd`-Weg lief also noch nie).

---

## 7. Unverändert übernommen aus Geminis Plan

Modulschnitt (`optical_media.py` / `disc_rip_worker.py` / `disc_ripper_dialog.py`),
Dialogaufbau (Laufwerksauswahl, Disc-Kopf, Titeltabelle mit Schnellknöpfen, Zielordner,
Fortschritt und Protokoll), die drei Rip-Modi, Zielordner-Vorschläge (`~/Musik` bzw.
`~/Videos`), Versionssprung auf **1.10.0**, Dokumentation in allen drei READMEs,
Commit und Push nach Projektregel 3.
