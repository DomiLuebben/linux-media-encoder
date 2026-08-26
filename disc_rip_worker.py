# -*- coding: utf-8 -*-
"""
Asynchrone Worker für optische Ripping-Vorgänge (Audio-CD & ISO-Dump).
Für Video-DVDs und Blu-rays mit FFmpeg wird direkt der bestehende FFmpegWorker
genutzt, um Code-Duplikate zu vermeiden und atomare Dateisicherheit zu wahren.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any, List, Optional

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

import optical_media
from optical_media import AudioTrackInfo, build_audio_cd_rip_command, build_audio_encode_args, build_iso_dump_command


class AudioCdRipWorker(QObject):
    """
    Rippt ausgewählte Audio-CD-Tracks via cdparanoia und encodiert sie via FFmpeg
    inklusive Metadaten (Titel, Artist, Album, Tracknummer).
    """
    progress_updated = pyqtSignal(float, str, str)  # Prozent, Geschwindigkeit, verbleibend
    log_received = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        device_path: str,
        tracks: List[AudioTrackInfo],
        output_dir: str,
        codec: str = "flac",
        bitrate: str = "320k",
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.device_path = device_path
        self.tracks = tracks
        self.output_dir = output_dir
        self.codec = codec
        self.bitrate = bitrate

        self.current_track_idx = 0
        self.process: Optional[QProcess] = None
        self._is_cancelled = False
        self._current_step = "idle"  # "extract" oder "encode"
        self._tmp_wav_file = ""
        self._tmp_out_file = ""
        self._final_out_file = ""

    def start(self):
        """Startet den Ripping-Vorgang für den ersten Track."""
        if not self.tracks:
            self.finished.emit(False, "Keine Tracks zum Rippen ausgewählt.")
            return

        os.makedirs(self.output_dir, exist_ok=True)
        self.current_track_idx = 0
        self._is_cancelled = False
        self._rip_next_track()

    def stop(self):
        """Bricht den laufenden Ripping-Vorgang ab."""
        self._is_cancelled = True
        self.status_changed.emit("Breche Ripping ab...")
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()
            self.process.waitForFinished(1000)
        self._cleanup_temp_files()
        self.finished.emit(False, "Ripping abgebrochen.")

    def _cleanup_temp_files(self):
        """Löscht temporäre Staging-Dateien."""
        for path in (self._tmp_wav_file, self._tmp_out_file):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _rip_next_track(self):
        if self._is_cancelled:
            return

        if self.current_track_idx >= len(self.tracks):
            self.progress_updated.emit(100.0, "", "Fertig")
            self.finished.emit(True, f"Alle {len(self.tracks)} Audio-Tracks erfolgreich gerippt.")
            return

        track = self.tracks[self.current_track_idx]
        total_tracks = len(self.tracks)
        overall_pct = (self.current_track_idx / total_tracks) * 100.0
        self.progress_updated.emit(overall_pct, "", f"Track {track.track_num} von {total_tracks}")
        self.status_changed.emit(f"Extrahiere Track {track.track_num}: {track.title}...")

        # Temp WAV-Pfad
        uid = uuid.uuid4().hex[:8]
        self._tmp_wav_file = os.path.join(self.output_dir, f".lme_tmp_cdda_{track.track_num}_{uid}.wav")

        # Ziel-Dateiname vorbereiten. AAC und ALAC gehören nach M4A — früher
        # landete beides in einer .aac-Datei, ALAC sogar in .wav (der alte
        # Ausdruck kannte alac nicht).
        ext = optical_media.audio_file_extension(self.codec)
        safe_title = re.sub(r'[^\w\-_\. ]', '_', track.title or f"Track_{track.track_num:02d}").strip()
        final_filename = f"{track.track_num:02d} - {safe_title}.{ext}"
        self._final_out_file = os.path.join(self.output_dir, final_filename)
        self._tmp_out_file = os.path.join(self.output_dir, f".lme_tmp_enc_{track.track_num}_{uid}.{ext}")

        # Schritt 1: cdparanoia Extraktion
        self._current_step = "extract"
        cmd = build_audio_cd_rip_command(self.device_path, track.track_num, self._tmp_wav_file)

        self.process = QProcess(self)
        self.process.readyReadStandardError.connect(self._handle_process_stderr)
        self.process.finished.connect(self._handle_step_finished)
        self.log_received.emit(f"[cdparanoia] Starte Extraktion von Track {track.track_num}...")
        self.process.start(cmd[0], cmd[1:])

    def _start_encode_step(self):
        if self._is_cancelled:
            return

        track = self.tracks[self.current_track_idx]
        self._current_step = "encode"
        self.status_changed.emit(f"Codiert Track {track.track_num} nach {self.codec.upper()}...")

        args = build_audio_encode_args(
            tmp_wav_input=self._tmp_wav_file,
            output_file=self._tmp_out_file,
            codec=self.codec,
            bitrate=self.bitrate,
            track_info=track,
        )

        self.process = QProcess(self)
        self.process.readyReadStandardError.connect(self._handle_process_stderr)
        self.process.finished.connect(self._handle_step_finished)
        self.log_received.emit(f"[ffmpeg] Encodiere Track {track.track_num}...")
        self.process.start(args[0], args[1:])

    def _handle_process_stderr(self):
        if not self.process:
            return
        data = self.process.readAllStandardError().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            line_str = line.strip()
            if line_str:
                self.log_received.emit(line_str)

    def _handle_step_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        if self._is_cancelled:
            return

        if exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
            step_name = "Extraktion" if self._current_step == "extract" else "Codierung"
            self._cleanup_temp_files()
            self.finished.emit(False, f"Fehler bei {step_name} von Track {self.tracks[self.current_track_idx].track_num} (Exit Code {exit_code}).")
            return

        if self._current_step == "extract":
            # Extraktion fertig -> weiter mit Encodieren
            self._start_encode_step()
        elif self._current_step == "encode":
            # Codierung fertig -> Atomar verschieben & temporäres WAV löschen
            try:
                if os.path.exists(self._tmp_out_file):
                    os.replace(self._tmp_out_file, self._final_out_file)
            except OSError as e:
                self._cleanup_temp_files()
                self.finished.emit(False, f"Konnte Zieldatei nicht erstellen: {e}")
                return

            if os.path.exists(self._tmp_wav_file):
                try:
                    os.remove(self._tmp_wav_file)
                except OSError:
                    pass

            self.log_received.emit(f"Track {self.tracks[self.current_track_idx].track_num} fertig: {os.path.basename(self._final_out_file)}")
            self.current_track_idx += 1
            self._rip_next_track()


class IsoDumpWorker(QObject):
    """
    Erstellt ein 1:1 ISO-Abbild eines optischen Datenträgers via dd mit Fortschrittsüberwachung.
    """
    progress_updated = pyqtSignal(float, str, str)
    log_received = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        device_path: str,
        output_iso_path: str,
        total_size_bytes: int = 0,
        ignore_errors: bool = True,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.device_path = device_path
        self.output_iso_path = output_iso_path
        self.total_size_bytes = total_size_bytes
        self.ignore_errors = ignore_errors
        self.process: Optional[QProcess] = None
        self._is_cancelled = False

        out_dir = os.path.dirname(output_iso_path) or "."
        uid = uuid.uuid4().hex[:8]
        self._tmp_iso_path = os.path.join(out_dir, f".lme_tmp_dump_{uid}.iso")

    def start(self):
        """Startet den dd-Prozess."""
        self._is_cancelled = False
        out_dir = os.path.dirname(self.output_iso_path) or "."
        os.makedirs(out_dir, exist_ok=True)

        block_count = None
        if self.total_size_bytes > 0:
            block_count = self.total_size_bytes // 2048

        conv_options = "noerror,sync" if self.ignore_errors else ""
        cmd = build_iso_dump_command(
            self.device_path,
            self._tmp_iso_path,
            block_count=block_count,
            conv_options=conv_options,
        )
        self.status_changed.emit("Erstelle 1:1 ISO-Abbild...")
        self.log_received.emit(f"Führe aus: {' '.join(cmd)}")


        self.process = QProcess(self)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._handle_finished)
        self.process.start(cmd[0], cmd[1:])

    def stop(self):
        """Bricht den ISO-Dump ab."""
        self._is_cancelled = True
        self.status_changed.emit("Breche ISO-Dump ab...")
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()
            self.process.waitForFinished(1000)
        if os.path.exists(self._tmp_iso_path):
            try:
                os.remove(self._tmp_iso_path)
            except OSError:
                pass
        self.finished.emit(False, "ISO-Abbild-Erstellung abgebrochen.")

    def _handle_stderr(self):
        if not self.process:
            return
        data = self.process.readAllStandardError().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            self.log_received.emit(line_str)

            # dd status=progress Format: "123456789 bytes (123 MB, 117 MiB) copied, 5.01234 s, 24.6 MB/s"
            m = re.search(r"(\d+)\s+bytes.*?copied,?\s*([\d\.]+\s*s)?,?\s*([\d\.]+\s*[kMG]?B/s)?", line_str)
            if m:
                copied_bytes = int(m.group(1))
                speed = m.group(3) or ""
                pct = 0.0
                if self.total_size_bytes > 0:
                    pct = min(99.9, (copied_bytes / self.total_size_bytes) * 100.0)
                self.progress_updated.emit(pct, speed, f"{copied_bytes // (1024*1024)} MB kopiert")

    def _handle_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        if self._is_cancelled:
            return

        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            try:
                if os.path.exists(self._tmp_iso_path):
                    os.replace(self._tmp_iso_path, self.output_iso_path)
                self.progress_updated.emit(100.0, "", "Fertig")
                self.finished.emit(True, f"1:1 ISO-Abbild erfolgreich erstellt: {self.output_iso_path}")
            except OSError as e:
                self.finished.emit(False, f"Konnte ISO-Datei nicht speichern: {e}")
        else:
            if os.path.exists(self._tmp_iso_path):
                try:
                    os.remove(self._tmp_iso_path)
                except OSError:
                    pass
            self.finished.emit(False, f"Fehler bei ISO-Erstellung (dd Exit Code {exit_code}).")
