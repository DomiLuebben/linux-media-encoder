# -*- coding: utf-8 -*-
"""
Untertitel-Editor (Subtitle Editor) Dialog für den Linux Media Encoder.
Führt die Transkription/Übersetzung asynchron via agy/Antigravity aus und
erlaubt dem Benutzer, die automatisch erzeugten Untertitel (SRT) zu prüfen.
"""

import os
import tempfile
from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QProgressBar, QMessageBox
)

import subtitle_utils


class SubtitleEditorDialog(QDialog):
    def __init__(self, input_file, output_file, source_lang, target_lang, parent=None, auto_start=True):
        super().__init__(parent)
        self.setWindowTitle("KI-Untertitel prüfen")
        self.setMinimumSize(600, 500)
        self.setModal(True)
        
        self.input_file = input_file
        self.output_file = output_file
        self.source_lang = source_lang
        self.target_lang = target_lang
        
        self.temp_audio_path = None
        self.sub_process = None
        self.sub_ai_process = None
        self.ai_stage = "transcribe"
        self.source_srt_content = ""
        self.srt_content = ""
        self.saved_srt_path = None
        
        self._init_ui()
        if auto_start:
            self._start_pipeline()
        else:
            self.progress_bar.setVisible(False)
            self.lbl_status.setText("Bereit.")
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Info label
        self.lbl_info = QLabel(f"Video: {os.path.basename(self.input_file)}")
        self.lbl_info.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.lbl_info)
        
        # Status message
        self.lbl_status = QLabel("Bereite Audio-Extraktion vor...")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminate
        self.progress_bar.setFixedHeight(8)
        layout.addWidget(self.progress_bar)
        
        # Large text editor
        self.txt_editor = QTextEdit()
        self.txt_editor.setPlaceholderText("Die automatisch erzeugten SRT-Untertitel erscheinen hier...")
        self.txt_editor.setEnabled(False) # Disabled during transcription
        layout.addWidget(self.txt_editor)
        
        # Bottom controls
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_save = QPushButton("Untertitel übernehmen")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._on_save_subtitles)
        
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)
        
    def _start_pipeline(self):
        """Phase 1: Audiospur extrahieren."""
        if not self.input_file or not os.path.exists(self.input_file):
            self.lbl_status.setText("Fehler: Eingabedatei existiert nicht.")
            self.progress_bar.setVisible(False)
            return
            
        # mkstemp statt vorhersagbarem Namen in /tmp (Symlink-Angriffe);
        # ffmpeg -y überschreibt die angelegte leere Datei.
        fd, self.temp_audio_path = tempfile.mkstemp(prefix="lme_editor_audio_", suffix=".mp3")
        os.close(fd)
        
        self.sub_process = QProcess(self)
        self.sub_process.finished.connect(self._on_audio_extracted)
        self.sub_process.errorOccurred.connect(self._on_process_failed_to_start)

        # Extract as mono 16kHz MP3
        args = ["-y", "-i", self.input_file, "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", self.temp_audio_path]
        self.lbl_status.setText("Extrahiere Audiospur (mono, 16kHz)...")
        self.sub_process.start("ffmpeg", args)
        
    def _on_audio_extracted(self, exit_code, exit_status):
        """Phase 2: Audiospur an agy / Antigravity übergeben."""
        if exit_code != 0 or not os.path.exists(self.temp_audio_path) or os.path.getsize(self.temp_audio_path) == 0:
            self.lbl_status.setText("Fehler: Audio-Extraktion fehlgeschlagen.")
            self.progress_bar.setVisible(False)
            self._cleanup_temp_files()
            return
            
        self.lbl_status.setText("Audio extrahiert. Starte KI-Transkription...")
        
        prompt = subtitle_utils.build_transcription_prompt(self.temp_audio_path, self.source_lang)
        self.ai_stage = "transcribe"
        self._start_ai_process(prompt)

    def _start_ai_process(self, prompt):
        cli_cmd = subtitle_utils.choose_ai_cli()
        self.sub_ai_process = QProcess(self)
        self.sub_ai_process.finished.connect(self._on_ai_finished)
        self.sub_ai_process.errorOccurred.connect(self._on_process_failed_to_start)
        self.sub_ai_process.start(cli_cmd, subtitle_utils.build_ai_args(cli_cmd, prompt))
        if cli_cmd in ("agy", "antigravity-cli"):
            self.sub_ai_process.write(prompt.encode('utf-8'))
            self.sub_ai_process.closeWriteChannel()

    def _on_process_failed_to_start(self, error):
        """ffmpeg/KI-CLI fehlt: 'finished' feuert nie — Dialog nicht hängen lassen."""
        if error != QProcess.ProcessError.FailedToStart:
            return
        self.progress_bar.setVisible(False)
        self._cleanup_temp_files()
        self.lbl_status.setText(
            "Fehler: Hilfsprogramm nicht gefunden (ffmpeg bzw. KI-CLI nicht installiert?)."
        )

    def _on_ai_finished(self, exit_code, exit_status):
        if exit_code != 0:
            err = self.sub_ai_process.readAllStandardError().data().decode("utf-8", errors="replace").strip()
            self._cleanup_temp_files()
            self.progress_bar.setVisible(False)
            if self.ai_stage == "translate" and self.source_srt_content:
                self.lbl_status.setText(
                    f"KI-Übersetzung fehlgeschlagen, verwende Original-Transkription: {err}"
                )
                self._finish_srt(self.source_srt_content)
            else:
                self.lbl_status.setText(f"Fehler bei KI-Transkription: {err}")
            return
            
        output = self.sub_ai_process.readAllStandardOutput().data().decode("utf-8", errors="replace").strip()
        
        if self.ai_stage == "transcribe":
            self._cleanup_temp_files()
            try:
                self.source_srt_content = subtitle_utils.normalize_srt(output)
            except ValueError as e:
                self.progress_bar.setVisible(False)
                self.lbl_status.setText(f"Fehler: KI hat keine validen SRT-Untertitel geliefert ({e}).")
                return

            if self.target_lang != subtitle_utils.NO_TRANSLATION:
                self.ai_stage = "translate"
                self.lbl_status.setText(
                    "Transkription abgeschlossen. Übersetze Text und erhalte Timecodes..."
                )
                prompt = subtitle_utils.build_translation_prompt(self.source_srt_content, self.target_lang)
                self._start_ai_process(prompt)
                return

            self.progress_bar.setVisible(False)
            self._finish_srt(self.source_srt_content)
            return

        try:
            translated_srt = subtitle_utils.merge_translated_text_with_source_timecodes(
                self.source_srt_content,
                output,
            )
        except ValueError as e:
            translated_srt = self.source_srt_content
            self.lbl_status.setText(
                f"Übersetzung hatte eine ungültige SRT-Struktur; Timecodes bleiben erhalten. ({e})"
            )

        self.progress_bar.setVisible(False)
        self._finish_srt(translated_srt)

    def _finish_srt(self, srt_content):
        self.srt_content = srt_content
        self.lbl_status.setText("Transkription erfolgreich abgeschlossen. Untertitel können jetzt bearbeitet werden.")
        self.txt_editor.setText(self.srt_content)
        self.txt_editor.setEnabled(True)
        self.btn_save.setEnabled(True)

    def _default_srt_path(self):
        default_dir = os.path.dirname(self.output_file) if self.output_file else os.path.expanduser("~")
        default_base = os.path.splitext(os.path.basename(self.output_file if self.output_file else self.input_file))[0]
        return os.path.join(default_dir, f"{default_base}.srt")

    def _on_save_subtitles(self):
        edited_content = self.txt_editor.toPlainText().strip()
        if not edited_content:
            QMessageBox.warning(self, "Leere Untertitel", "Die Untertitel dürfen nicht leer sein.")
            return

        file_path = self._default_srt_path()
        # Vorhandene .srt nicht stillschweigend überschreiben
        if os.path.exists(file_path):
            reply = QMessageBox.question(
                self, "Datei überschreiben?",
                f"Die Datei existiert bereits:\n{file_path}\n\nÜberschreiben?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                from PyQt6.QtWidgets import QFileDialog
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "Untertitel speichern unter", file_path,
                    "SubRip Untertitel (*.srt)"
                )
                if not file_path:
                    return
        try:
            normalized = subtitle_utils.normalize_srt(edited_content)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(normalized)
            self.saved_srt_path = file_path
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Schreibfehler", f"Die Datei konnte nicht gespeichert werden:\n{e}")
                
    def get_saved_srt_path(self):
        return self.saved_srt_path
        
    def _cleanup_temp_files(self):
        if self.temp_audio_path and os.path.exists(self.temp_audio_path):
            try:
                os.remove(self.temp_audio_path)
            except OSError:
                pass
            self.temp_audio_path = None
            
    def reject(self):
        if self.sub_process:
            try:
                self.sub_process.finished.disconnect()
                self.sub_process.errorOccurred.disconnect()
            except (TypeError, RuntimeError):
                pass
            if self.sub_process.state() != QProcess.ProcessState.NotRunning:
                self.sub_process.kill()
                self.sub_process.waitForFinished(1000)
        if self.sub_ai_process:
            try:
                self.sub_ai_process.finished.disconnect()
                self.sub_ai_process.errorOccurred.disconnect()
            except (TypeError, RuntimeError):
                pass
            if self.sub_ai_process.state() != QProcess.ProcessState.NotRunning:
                self.sub_ai_process.kill()
                self.sub_ai_process.waitForFinished(1000)
        self._cleanup_temp_files()
        super().reject()
