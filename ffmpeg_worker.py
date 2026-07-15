# -*- coding: utf-8 -*-
"""
FFmpeg Worker-Klasse für den Linux Media Encoder.
Verwaltet den asynchronen FFmpeg-Prozess mittels QProcess,
parst den Fortschritt und leitet Logs an die GUI weiter.
"""

import re
import os
import uuid
from PyQt6.QtCore import QObject, QProcess, pyqtSignal

class FFmpegWorker(QObject):
    # Signale für die GUI
    progress_updated = pyqtSignal(float, str, str)  # Prozent, Geschwindigkeit, verbleibende Zeit
    log_received = pyqtSignal(str)                  # Konsolenzeile
    status_changed = pyqtSignal(str)                # Textueller Status
    finished = pyqtSignal(bool, str)                # Erfolg (True/False), Fehlermeldung/Erfolgsmeldung

    def __init__(self, input_file, output_file, ffmpeg_args, total_duration=None):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.ffmpeg_args = ffmpeg_args
        self.process = None
        # Erwartete Ausgabedauer kann vorgegeben werden (z. B. bei Trim kürzer
        # als die Quelle) — sonst wird sie aus dem FFmpeg-Header geparst.
        self.total_duration_sec = float(total_duration) if total_duration else 0.0
        self._duration_fixed = bool(total_duration)

        # Eindeutige Temp-Ausgabedatei im selben Verzeichnis: So bleibt
        # os.replace() atomar, ohne dass parallele/abgestürzte Worker denselben
        # vorhersehbaren Staging-Pfad verwenden. Die echte Dateiendung bleibt
        # erhalten, damit FFmpeg das Ausgabeformat weiterhin erkennen kann.
        output_dir = os.path.dirname(self.output_file)
        output_ext = os.path.splitext(os.path.basename(self.output_file))[1]
        temp_name = f".lme_tmp_{uuid.uuid4().hex}{output_ext}"
        self.temp_output_file = os.path.join(output_dir, temp_name)

        # Regex für Metadaten-Dauer (aus Stderr): "Duration: 00:02:15.33,"
        self.duration_regex = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2})")
        # Regex für die out_time-Zeile aus -progress: "out_time=00:00:01.234567"
        self.out_time_regex = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.(\d+)")

        # Puffer für unvollständige Zeilen
        self.stdout_buffer = ""
        self.stderr_buffer = ""

        # Laufende Fortschrittswerte
        self._current_speed = "0.0x"
        self._current_time_us = 0

        # Schutz gegen doppelt gesendete finished-Signale (z. B. Abbruch + Prozessende)
        self._finished_emitted = False

    def _emit_finished(self, success, message):
        """Sendet das finished-Signal genau einmal."""
        if self._finished_emitted:
            return
        self._finished_emitted = True
        if not success:
            # Clean up temp file on failure/cancellation
            if hasattr(self, "temp_output_file") and os.path.exists(self.temp_output_file):
                try:
                    os.remove(self.temp_output_file)
                except OSError:
                    pass
        self.finished.emit(success, message)

    def start(self):
        """Startet den FFmpeg-Prozess."""
        if not os.path.exists(self.input_file):
            self._emit_finished(False, f"Eingabedatei existiert nicht: {self.input_file}")
            return

        self.process = QProcess(self)
        
        # Replace output_file (usually the last argument) with temp_output_file
        modified_args = list(self.ffmpeg_args)
        if modified_args and modified_args[-1] == self.output_file:
            modified_args[-1] = self.temp_output_file
        else:
            modified_args = [self.temp_output_file if arg == self.output_file else arg for arg in modified_args]

        # Wir fügen '-progress -' an den Anfang der FFmpeg-Argumente ein, 
        # damit FFmpeg Fortschrittsinformationen im Schlüssel-Wert-Format an stdout sendet.
        # So trennen wir Logs (stderr) von strukturierten Fortschritten (stdout).
        full_args = []
        # Argumente durchsuchen und '-progress -' nach dem Input, aber vor dem Output einfügen
        # Einfacher ist es, es direkt nach '-i <input>' einzufügen
        input_idx = -1
        for i, arg in enumerate(modified_args):
            if arg == "-i":
                input_idx = i + 2
                break
        
        if input_idx != -1 and input_idx < len(modified_args):
            full_args = modified_args[:input_idx] + ["-progress", "-"] + modified_args[input_idx:]
        else:
            # Fallback
            full_args = ["-progress", "-"] + modified_args

        self.status_changed.emit("Initialisiere FFmpeg...")
        
        # QProcess Signale verbinden
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._handle_finished)
        self.process.errorOccurred.connect(self._handle_error)

        # FFmpeg starten
        # Wir gehen davon aus, dass 'ffmpeg' im System-Pfad liegt
        self.process.start("ffmpeg", full_args)

        if not self.process.waitForStarted(3000):
            self._emit_finished(False, "FFmpeg konnte nicht gestartet werden. Ist es installiert?")

    def _handle_error(self, error):
        """Fängt Prozess-Start-Fehler ab (z. B. ffmpeg nicht im PATH)."""
        if error == QProcess.ProcessError.FailedToStart:
            self._emit_finished(False, "FFmpeg wurde nicht gefunden. Bitte installiere FFmpeg und stelle sicher, dass es im PATH liegt.")

    def stop(self):
        """Bricht den laufenden FFmpeg-Prozess ab."""
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.status_changed.emit("Breche ab...")
            # Den regulären finished-Handler trennen, damit das Prozessende
            # nicht ein zweites (widersprüchliches) finished-Signal auslöst.
            try:
                self.process.finished.disconnect(self._handle_finished)
            except (TypeError, RuntimeError):
                pass
            # FFmpeg reagiert auf ein 'q' auf stdin für einen sauberen Abbruch
            self.process.write(b"q\n")
            if not self.process.waitForFinished(2000):
                self.process.kill()
                self.process.waitForFinished(1000)
            self._emit_finished(False, "Prozess abgebrochen.")

    def _handle_stdout(self):
        """Liest Fortschrittsinformationen von stdout."""
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self.stdout_buffer += data
        
        while "\n" in self.stdout_buffer:
            line, self.stdout_buffer = self.stdout_buffer.split("\n", 1)
            line = line.strip()
            self._parse_progress_line(line)

    def _handle_stderr(self):
        """Liest FFmpeg-Konsolenoutput von stderr und sucht nach der Dauer."""
        data = self.process.readAllStandardError().data().decode("utf-8", errors="replace")
        self.stderr_buffer += data
        
        while "\n" in self.stderr_buffer:
            line, self.stderr_buffer = self.stderr_buffer.split("\n", 1)
            self.log_received.emit(line)
            
            # Dauer parsen, falls noch nicht geschehen (und nicht vorgegeben)
            if self.total_duration_sec == 0.0 and not self._duration_fixed:
                match = self.duration_regex.search(line)
                if match:
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    seconds = int(match.group(3))
                    centiseconds = int(match.group(4))
                    self.total_duration_sec = (hours * 3600) + (minutes * 60) + seconds + (centiseconds / 100.0)
                    self.log_received.emit(f"[LME INFO] Mediendauer erkannt: {hours:02d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d} ({self.total_duration_sec}s)")

    def _parse_progress_line(self, line):
        """Parst Schlüssel-Wert-Zeilen von FFmpeg -progress."""
        if "=" not in line:
            return
            
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key == "speed":
            if value and value != "N/A":
                self._current_speed = value
        elif key in ("out_time_us", "out_time_ms"):
            # out_time_us und out_time_ms liefern beide Mikrosekunden.
            try:
                self._current_time_us = int(value)
            except ValueError:
                pass
        elif key == "out_time":
            # Robuster Fallback: "out_time=00:00:01.234567"
            m = self.out_time_regex.search(value)
            if m:
                frac = m.group(4)
                frac_sec = int(frac) / (10 ** len(frac))
                secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + frac_sec
                self._current_time_us = int(secs * 1_000_000)
        elif key == "progress":
            # progress=continue oder progress=end bedeutet, dass ein Durchgang fertig bzw. mittendrin ist
            current_sec = self._current_time_us / 1000000.0
            
            if self.total_duration_sec > 0:
                percent = (current_sec / self.total_duration_sec) * 100.0
                percent = min(100.0, max(0.0, percent))
                
                # Verbleibende Zeit berechnen
                # speed extrahieren (z. B. "1.43x" -> 1.43)
                speed_factor = 1.0
                speed_match = re.search(r"([\d\.]+)", self._current_speed)
                if speed_match:
                    try:
                        speed_factor = float(speed_match.group(1))
                    except ValueError:
                        pass
                
                remaining_sec = 0.0
                if speed_factor > 0:
                    remaining_sec = (self.total_duration_sec - current_sec) / speed_factor
                
                # Formatierung der verbleibenden Zeit
                rem_h = int(remaining_sec // 3600)
                rem_m = int((remaining_sec % 3600) // 60)
                rem_s = int(remaining_sec % 60)
                
                if rem_h > 0:
                    time_str = f"{rem_h}h {rem_m}m {rem_s}s"
                elif rem_m > 0:
                    time_str = f"{rem_m}m {rem_s}s"
                else:
                    time_str = f"{rem_s}s"
                    
                if value == "end":
                    percent = 100.0
                    time_str = "Fertig"
                    
                self.progress_updated.emit(percent, self._current_speed, time_str)
            else:
                # Dauer unbekannt (z. B. Live-Streaming oder defekter Header)
                self.progress_updated.emit(0.0, self._current_speed, "Unbekannt")

    def _handle_finished(self, exit_code, exit_status):
        """Callback für das Prozessende."""
        # Bei CrashExit (Segfault, OOM-Kill) ist exit_code laut Qt-Doku undefiniert
        # und kann 0 sein — ohne diese Prüfung würde ein Absturz als Erfolg gemeldet.
        if exit_status != QProcess.ExitStatus.NormalExit:
            self._emit_finished(False, "Konvertierung fehlgeschlagen (FFmpeg-Prozess abgestürzt).")
        elif exit_code == 0:
            try:
                os.replace(self.temp_output_file, self.output_file)
                self.progress_updated.emit(100.0, "0.0x", "Fertig")
                self._emit_finished(True, "Erfolgreich konvertiert.")
            except Exception as e:
                self._emit_finished(False, f"Fehler beim Speichern der Zieldatei: {e}")
        else:
            # Fehlercode oder Abbruch
            self._emit_finished(False, f"Konvertierung fehlgeschlagen (Exit-Code: {exit_code}).")
