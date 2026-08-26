# AUDIT — LINUX MEDIA ENCODER GESAMT (ox-alpha, 26.08.2026)

Vollaudit des Projekts `~/Projekte/linux-media-encoder`, nicht nur des Blu-ray-Rip-Features.
Anlass: Dominiks Bitte nach einem kompletten Audit nach dem Ripper-Ausbau (1.8 → 1.11.0).

## Ausgangsstand, selbst nachgemacht

- **Version:** 1.11.0 an beiden Stellen konsistent (`version.py` und PKGBUILD `pkgver=1.11.0-1`).
- **Git:** sauber, HEAD `7b97ddb` = `origin/main` (Video-Vorschau mit Auto-Crop), davor `10ec699` (Fehlertoleranz-Flags).
- **Tests: 228/228 grün** — selbst ausgeführt (`QT_QPA_PLATFORM=offscreen python3 -m unittest discover`), 18,5 s. Die gemeldete Zahl stimmt. Hinweis: **pytest ist auf diesem System nicht installiert**, die Suiten sind unittest-basiert; ein earlierer Loop über `pytest` lief deshalb ins Leere.
- **PKGBUILD-Integrität:** alle 21 SHA-256-Summen gegen den tatsächlichen Dateistand geprüft — **alle OK**. Das Paket kann so gebaut werden.

## 🔴 Befund 1 (major) — „Alle Audiospuren / Alle Untertitel" wählt im Direkt-Rip nur die LETZTE Spur

Die Titel-Tabelle bietet „Alle Audiospuren" und „Alle Untertitel" mit dem Datenwert **-1** an. Der Queue-Weg wertet das in `presets.get_ffmpeg_args()` korrekt aus (`audio_idx == -1 → -map 0:a?`). Die Builder für den **Direkt-Rip** tun es nicht:

```python
# optical_media.py — build_dvd_rip_args() / build_bluray_rip_args()
if audio_stream_idx is not None:
    args += ["-map", f"0:a:{audio_stream_idx}"]
```

Gegenprobe (ausgeführt): `build_*_rip_args(..., audio_stream_idx=-1, subtitle_stream_idx=-1)` erzeugt **`-map 0:a:-1`** und **`-map 0:s:-1`**. FFmpeg liest negative Indizes als „letzte Spur dieser Art" — wer „alle" wählt, bekommt genau eine Spur (die letzte), stillschweigend. Betrifft DVD **und** Blu-ray, im Dialog-Direktweg **und** im zweistufigen Stufe-1-Remux der Warteschlange (dieselben Builder). Die bestehenden Tests prüfen die Builder nie mit -1 — deshalb ist das durchgerutscht.

**Behebung (einfach):** in beiden Buildern `-1` wie in `get_ffmpeg_args()` behandeln (`0:a?`/`0:s?`), plus Testfälle mit -1.

## 🔴 Befund 2 (major) — Audio-CD-Formatwahl: AAC/Opus/ALAC fallen still auf WAV

Die ComboBox bietet sechs Formate: FLAC, WAV, MP3 (320k), AAC (256k), Opus (160k), ALAC.

- **Queue-Zweig** (`_queue_selected_jobs`) kennt nur drei: `codec_key = "flac" if "flac" … else ("mp3" … else "wav")`. AAC-, Opus- und ALAC-Wahl wird **stillschweigend zu WAV** (unkomprimiert, riesige Dateien).
- **Direkt-Zweig** kennt flac/mp3/opus/aac/wav — **ALAC fehlt auch hier**: ALAC-Wahl wird zu WAV. `build_audio_encode_args()` unterstützt `alac` längst; der Wert erreicht sie nur nie.

Der direkte Weg meldet Erfolg — niemand merkt, dass ein anderes Format herauskam. Gegenprobe gegen den Quelltext bestätigt beide Zweige.

**Behebung:** Codec-Ermittlung in EINEN Helfer ziehen (beide Zweige nutzen ihn), inkl. `alac`; sonst driftet das beim nächsten Format wieder auseinander.

## 🟠 Befund 3 (minor) — Die Fehlertoleranz-Checkbox wirkt nicht auf Stufe 1 des zweistufigen Rips

`_run_disc_rip_stage()` ruft `build_dvd_rip_args()` / `build_bluray_rip_args()` **ohne** `ignore_errors=` — die Builder haben Vorgabe `True`. Wer die Fehlertoleranz bewusst ABWählt (um saubere Abbilder von intakten Discs zu bekommen und echte Lesefehler gemeldet zu kriegen), kriegt im zweistufigen Weg trotzdem `conv=noerror,sync` bzw. `-err_detect ignore_err`. Der Direktweg respektiert die Checkbox korrekt. Gegenprobe: kein einziger Aufruf in `_run_disc_rip_stage` übergibt die Einstellung, obwohl sie im Job steckt.

## 🟡 Kleinere Beobachtungen (nicht dringend)

1. **Disc-Inspektion blockiert die Oberfläche:** `inspect_source()` läuft synchron im GUI-Thread (`QApplication.setOverrideCursor` rettet nur den Cursor). Bei Blu-rays werden bis zu 40 Playlists sequenziell per ffprobe gelesen (je Timeout 20 s) — eine volle BD kann die GUI minutenlang einfrieren. Ein QThread/QProgressDialog wäre der saubere Weg; solange es nur beim Einlegen einer Disc passiert, ist es UX, nicht Korrektheit.
2. **dd ohne `iflag=fullblock`:** bei `conv=noerror,sync` können Teilblöcke mit Nullen aufgefüllt statt voll gelesen werden — für ein 1:1-Abbild theoretisch relevant, praktisch bei Blockgeräten selten. Ein Blick wert.
3. `_inspect_iso_disc_type()` liest bis zu 8 MB pro ISO in den Speicher — harmlos, aber unnötig groß; die Signaturprüfung käme mit deutlich weniger aus.
4. Alte Paketdateien (`linux-media-encoder-1.8.x–1.11.0.pkg.tar.zst`) liegen unversioniert im Projektordner — gehören nicht ins Git, stehen dort aber auch nicht in `.gitignore`-Konflikt. Kosmetik.
5. `scan_audio_cd()` leitet cdparanoia-STDOUT auf STDERR um und parst dann STDOUT — funktioniert, ist aber verwirrend kommentiert (TOC kommt via Umleitung, nicht „auf STDERR").

## Geprüft und in Ordnung — nicht erneut aufrollen

- **Befehlsausführung/Sicherheit:** alle subprocess-/QProcess-Aufrufe mit Argumentlisten, nirgends `shell=True`; Gerätepfade kommen aus der sysfs/udev-Erkennung, Dateinamen werden gefiltert; der Installer baut keine AUR-Pakete (bewusst, mit Begründung im Quelltext) und nutzt pkexec/polkit mit vorheriger Sperrdatei-Prüfung.
- **Temporäre Dateien:** überall UUID-Namen + atomares `os.replace` (AudioCdRipWorker, IsoDumpWorker, FFmpegWorker); Cleanup bei Abbruch/Fehler vorhanden; die Zwischendatei des zweistufigen Rips wird bei Erfolg UND Misserfolg geräumt (`_on_worker_finished` → `_cleanup_staged_source`).
- **Zwischenspeicher-Auswahl:** `/tmp` bewusst zuletzt (tmpfs-Risiko ist im Kommentar dokumentiert), Platzschätzung mit Fallback-Bitraten, Rückfall auf direkte Konvertierung ohne Platz statt Abbruch — richtig entschieden.
- **Blu-ray-Pfad:** Playlist-Verschleierung (Kurz-Playlists) wird gefiltert, nur wenn etwas übrig bleibt; AACS/BD+-Status wird ausgewertet und verständlich gemeldet; `bd_info` nur für Kopfdaten, Playlists über ffprobe `bluray:` — die Trennung ist im Kommentar begründet und stimmt mit libblurays Fähigkeiten überein.
- **ISO-Erkennung:** Spiel-/Installations-ISOs fallen nicht mehr in den DVD-Parser (Fix dokumentiert und durch Test gedeckt).
- **Fortschritt bei Disc-Jobs:** Titeldauer wird vorgegeben, Kopfbereich-Fallen umgangen (Commit `4923d63`); FFmpegWorker unterscheidet CrashExit von Exit-Code 0.
- **Quell-/Ziel-Schutz:** Ausgabe == Quelle einer Queue-Datei wird abgefangen, bevor FFmpeg mit `-y` zerstören kann.
- **i18n:** dynamisch zusammengesetzte Texte sind als `LocalizedString` markiert, damit der Schlüsselcheck keine Phantom-Fehlen meldet — Muster konsequent durchgehalten.
- **Versionspflege:** 1.11.0 an beiden Stellen synchron; PKGBUILD deckt exakt die vorhandenen Dateien ab.

## Prüfstand (alles selbst ausgeführt)

| Prüfung | Ergebnis |
| --- | --- |
| unittest discover (10 Suiten) | **228/228 OK** |
| PKGBUILD SHA-256 (21 Dateien) | **alle OK** |
| version.py ↔ PKGBUILD | 1.11.0 / 1.11.0-1 konsistent |
| git status | sauber (HEAD `7b97ddb` = origin/main) |
| Gegenproben Befund 1/2/3 | je rot gegen den Ist-Stand bestätigt |

## Behebung & Freigabe (1.11.2)

Alle drei ursprünglichen Befunde sowie die Punkte der Nachprüfung wurden behoben und durch 15 neue Regressionstests abgesichert:
1. **Befund 1 behoben:** `build_dvd_rip_args()` & `build_bluray_rip_args()` mappen `-1` auf `0:a?`/`0:s?` und behalten Stream-Indizes für `>= 0` bei.
2. **Befund 2 behoben:** Gemeinsame Codec-Ermittlung `audio_codec_key_from_label()`, Endungshelfer `audio_file_extension()` und Bitraten-Ermittlung `audio_bitrate_from_label()` in `optical_media.py`. Volle Unterstützung für FLAC, WAV, MP3 (320k), AAC (256k), Opus (160k) und ALAC in beiden Zweigen (Queue & Direkt-Rip).
3. **Befund 3 behoben:** `_run_disc_rip_stage()` reicht `ignore_errors` explizit an die Rip-Builder weiter.
4. **Nachprüfung behoben:** `mainwindow.py` fängt via `_on_audio_cd_extract_error` das `errorOccurred`-Signal von `cdparanoia` (z.B. bei fehlendem Paket / `FailedToStart`) ab, räumt Temp-Dateien auf und markiert den Job als fehlgeschlagen, statt hängenzubleiben. `AudioCdRipWorker` und `IsoDumpWorker` verbinden `errorOccurred` ebenfalls. Voller End-to-End-Lifecycle-Test für Audio-CD in der Queue (Extraktion → Encodierung → Staging-Cleanup) hinzugefügt.

### Prüfstand nach Behebung
| Prüfung | Ergebnis |
| --- | --- |
| unittest discover (10 Suiten) | **243/243 OK** |
| PKGBUILD SHA-256 (21 Dateien) | **alle 21 OK** |
| version.py ↔ PKGBUILD | 1.11.2 / 1.11.2-1 konsistent |
| Paketbau (makepkg -f) | `linux-media-encoder-1.11.2-1-any.pkg.tar.zst` (SHA-256 `f365f7e930f7d11e37363e548a211dc1d0e3f3c4e641fcf71989583068f667e1`) erfolgreich gebaut |
