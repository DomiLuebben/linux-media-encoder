# Changelog — Linux Media Encoder

## [1.12.5] — 2026-10-04

### Behoben
- **Die Oberfläche fror ein, sobald alle Jobs abgearbeitet waren**
  (Dominik: „der einfriert sobald die Jobs abgearbeitet sind")
  - **Ursache, am laufenden Verhalten gemessen statt im Code vermutet:**
    Genau an dieser Stelle — dem Ende der Warteschlangen-Verarbeitung —
    wird die Abschluss-Benachrichtigung verschickt. Deren D-Bus-Weg war
    **blockierend**: Die Oberfläche stand still, bis der Notification-Daemon
    antwortete. Gemessen mit einem Heartbeat-Timer am echten Code: **exakt
    dessen Antwortzeit** — ein hängender Daemon ergab 6 s Stillstand pro
    Queue-Durchlauf, im Extremfall bis zum D-Bus-Timeout.
  - **Es waren zwei blockierende Stellen, nicht eine.** Ein bloßes Umstellen
    des Aufrufs auf einen asynchronen (`asyncCall`) hätte nur die zweite
    behoben: **schon die Konstruktion** von `QDBusInterface` mit anschließendem
    `isValid()` löst eine synchrone, runde Introspektion aus und blockiert
    genauso (nachgewiesen: 6011 ms). Beide standen im gemessenen Weg.
  - **Behoben:** Die gesamte D-Bus-Arbeit läuft jetzt in einem eigenen
    Thread (`_NotifyWorker` + `_run_notify_async`). Der Aufrufer kehrt sofort
    zurück. Nach der Behebung gemessen: **51–56 ms** statt 6000 ms, in allen
    vier Fällen (langsamer Daemon, kein Daemon, fehlendes QtDBus-Modul,
    realer Aufruf).
  - **Zweiter Fehler, dabei gefunden und behoben:** `finished_failed` hat
    **null** Parameter, der Rückfall-Slot wurde aber direkt an
    `_notify_via_notify_send(title, body)` gehängt — Qt kann eine solche
    Verbindung nicht herstellen und **beendet den Prozess mit einem Fatal**.
    Jetzt verbindet ein parameterloser `_fallback()`, der seine Daten aus dem
    umschliessenden Scope holt.

### Prüfstand
- **Neuer Test `test_queue_freeze.py` (5 Prüfungen)**, mit **beidseitigem
  Mutationsnachweis** — ein Wächter, der nicht anschlägt, bewacht nichts:
  - **Mutation A** (ursprünglicher blockierender Aufruf wiederhergestellt):
    Test schlägt an, meldet **5001 ms**.
  - **Mutation B** (2-Parameter-Slot an ein 0-Parameter-Signal):
    Test reproduziert den **Prozessabbruch (Exit 134)**.
  - Ohne beide Fehler: **5/5 grün in 5,3 s**.
  - Erfasst werden außerdem: das Ende des Benachrichtigungs-Threads (sonst
    Fensterabbau mit Fehler) und dass der Rückfall die **richtigen Daten**
    weiterreicht.
- **`bash scripts/verify-all.sh`: 299 Tests grün**, dazu jeder der 17
  Testmodule einzeln im eigenen Prozess, `py_compile` und `manual_ui_check.py`.
  Laufzeit 81 s, Exit 0.
- **Wegwerf-Messungen** (`/tmp/opencode/`): Event-Loop-Lücken am Queue-Ende
  über einen 50-ms-Heartbeat, isolierte Thread-Tests, Fensterabbau während
  laufender Benachrichtigung.

### Selbstverschulden, offen dokumentiert
- **Der erste Wächter war blind.** Er maß die Blockade über einen
  Heartbeat-Timer und meldete „grün", obwohl der echte Fehler aktiv war:
  das Messbudget endete, bevor die blockierende Aktion abgeschlossen war,
  und die Lücke daher nie erfasst wurde. Drei Mutationsproben blieben
  zunächst ebenfalls grün. Erst die **direkte Messung der Aufrufzeit**
  (`_measure_call_time`) hat den Fehler sichtbar gemacht. Genau die
  Merkregel aus den V2-Audits: eine Pruefung, die ins Leere laufen kann,
  gilt als nicht geliefert.
- **Zwei Testfehler haben den Prozess abbrechen lassen** und waren keine
  Programmfehler: eine D-Bus-Attrappe, die ein `QObject` nachbildet (Qt
  zerstört solche beim Thread-Ende), und ein Wegwerfskript, das globale
  Attrappen über `close()` hinweg bestehen ließ. Beide Attrappen sind jetzt
  bewusst **keine** `QObject`-Erben.

### Nicht geprüft
- **Kein Hörtest am echten Desktop.** Der Freeze ist am Code gemessen, über
  die Event-Schleife — das ist der Oberflächen-Stillstand, den Dominik
  beschrieben hat, aber nicht am Bildschirm selbst gesehen.
- **Nicht auf anderen Distributionen** (nur Arch/CachyOS auf diesem Rechner).
- Ein 6-Sekunden-Hänger, der von einem hängenden Notification-Daemon
  **verursacht** wird, ist damit umgangen (kein Warten mehr). Der
  Notification-Daemon selbst wird dabei nicht behandelt.

## [1.12.4] — 2026-09-28

### Behoben
- **HEVC/H.265 ignorierte die eingestellte Bitrate — Ergebnisse immer über 300 MB
  (Dominik: „egal wie klein ich die Bitrate einstelle es ist immer über 300 MB groß,
  es scheint nicht zu funktionieren")**
  - **Ursache, an der Quelle nachgemessen statt vermutet:** Die Formatvorgabe
    `"HEVC / H.265 (MP4)"` in `presets.py` war die **einzige** Videoformat-Vorgabe mit
    leerer `video_bitrate` **und** gesetztem `crf: "23"`. Daraus folgte zweierlei:
    1. Beim Wechsel auf HEVC wurde die vom Benutzer gewählte Bitrate ersetzt
       (`video_bitrate='1M'` → `''`, Regler springt auf 23).
    2. Ohne Bitrate und mit CRF entscheidet `get_ffmpeg_args()` in der Ableitung auf
       **Qualitätssteuerung**. Dort ist der Regler **invertiert**: ein kleinerer Wert
       bedeutet bessere Qualität und damit eine **größere** Datei. Wer „die Bitrate
       kleiner stellt", macht das Ergebnis größer.
  - **Was nachgemessen wurde, um Fehlalarme auszuschließen:**
    - Der Argumentbauer ist korrekt: es entsteht `-c:v libx265 -b:v <Wert>`.
    - libx265 respektiert die Vorgabe auch — an echten, mit ffmpeg erzeugten Dateien
      gemessen: 8 Mbit/s auf 120 s ⇒ 114 MB, 2 Mbit/s ⇒ 28 MB.
    - Beide Oberflächen (Hauptfenster-Queue und Exportdialog) reichen den Reglerwert
      korrekt durch: nach 1,0 Mbps steht dort `-b:v 1M` bei ffmpeg.
  - **Behoben:** HEVC erhält `video_bitrate: "8M"`, `crf: ""` und ein ausdrückliches
    `encoding_mode: "vbr"` — wie H.264 (8M), VP9 (4M) und AV1 (4M). Ebenso die beiden
    NVENC-Vorgaben (HEVC und AV1). Nach dem Formatwechsel auf HEVC steht der Regler
    damit auf „Zielbitrate (Mbps)" statt auf „Qualitätsfaktor (CRF)".
  - **Ausdrückliche CRF-Wahl bleibt erhalten:** Wer „CRF (Qualitätsbasiert)" wählt,
    bekommt weiterhin die Qualitätsstufe — nur eben mit korrekt beschriftetem Regler.

### Prüfstand
- **Neuer Test `test_hevc_bitrate.py`** (4 Prüfungen) an den **echten** Vorgaben, nicht an
  einer Nachbildung. Er hält die Fehlerklasse fest: kein Format darf leere Zielbitrate
  bei gesetzter Qualitätsstufe haben. H.264, VP9, AV1, MOV und MKV setzen
  `encoding_mode` alle nicht und waren nie betroffen — deshalb prüft der Wächter nicht
  auf dessen Anwesenheit, sondern auf die Invariante, die wirklich gilt.
- **Mutationsnachweis:** HEVC zurück auf `crf: "23"` ⇒ 3 Fehlschläge; CRF und Bitrate
  gleichzeitig ⇒ 1 Fehlschlag. Eine dritte Probe (nur `encoding_mode` entfernt, Bitrate
  bleibt) bleibt grün — das ist korrekt, mit Bitrate und ohne CRF leitet der Code ohnehin
  auf `vbr` ab.
- **`bash scripts/verify-all.sh`: 588 Tests in 16 Modulen grün**, dazu `py_compile`,
  `unittest discover` und `manual_ui_check.py`.

### Unverändert
- Der Formatwechsel verwirft weiterhin eine gesetzte Bitrate (Vorgabe wird 8M, nicht die
  eigene Wahl). Das gilt für alle Formate gleich und ist Absicht („Vorgabenwechsel: alles,
  was nicht zur Vorgabe gehört, bleibt nicht stehen").
- Disc-Ripping, Blu-ray/DVD-Analyse, Untertitel und alle anderen Pfade wurden nicht
  angefasst.
