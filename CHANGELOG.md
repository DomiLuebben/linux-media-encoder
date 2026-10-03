# Changelog — Linux Media Encoder

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
