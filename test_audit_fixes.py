# -*- coding: utf-8 -*-
"""Regressionstests für die Audit-Fixes (Code-Audit 2026-07-05)."""

import os
import sys
import unittest

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

import presets
from ffmpeg_worker import FFmpegWorker
from mainwindow import MainWindow


class WorkerCrashExitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_crash_exit_is_reported_as_failure_even_with_exit_code_zero(self):
        # Bei CrashExit ist der Exit-Code laut Qt undefiniert und kann 0 sein –
        # das darf nie als Erfolg gemeldet werden.
        worker = FFmpegWorker("in.mp4", "out.mp4", [])
        results = []
        worker.finished.connect(lambda ok, msg: results.append((ok, msg)))
        worker._handle_finished(0, QProcess.ExitStatus.CrashExit)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0][0])

    def test_normal_exit_zero_is_success(self):
        worker = FFmpegWorker("in.mp4", "out.mp4", [])
        results = []
        worker.finished.connect(lambda ok, msg: results.append((ok, msg)))
        worker._handle_finished(0, QProcess.ExitStatus.NormalExit)
        self.assertTrue(results[0][0])


class PresetsAuditFixesTest(unittest.TestCase):
    def test_crf_mode_with_invalid_crf_falls_back_to_23(self):
        # Vorher: ungültiger CRF-Wert → weder -crf noch -b:v (stilles Encoder-Default)
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings.update({"encoding_mode": "crf", "crf": "kaputt", "video_bitrate": ""})
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertIn("-crf", args)
        self.assertEqual(args[args.index("-crf") + 1], "23")

    def test_crf_mode_accepts_float_values(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings.update({"encoding_mode": "crf", "crf": "23.5", "video_bitrate": ""})
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertIn("-crf", args)
        self.assertEqual(args[args.index("-crf") + 1], "23.5")

    def test_subtitles_filter_escapes_semicolon(self):
        # ';' trennt Filterketten im Filtergraph und muss escaped werden
        result = presets.build_subtitles_filter("/tmp/a;b.srt")
        self.assertIn("\\;", result)
        self.assertNotIn(";b", result.replace("\\;", ""))


class MainWindowAuditFixesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls._timer = QTimer()
        cls._timer.timeout.connect(cls._dismiss_dialogs)
        cls._timer.start(20)

    @staticmethod
    def _dismiss_dialogs():
        app = QApplication.instance()
        for w in list(app.topLevelWidgets()):
            if isinstance(w, QMessageBox):
                w.done(QMessageBox.StandardButton.Yes)

    def _window_with_job(self):
        window = MainWindow()
        window._add_file_to_queue(os.path.abspath("test_input.mp4"))
        self.app.processEvents()
        return window

    def test_format_switch_keeps_subtitle_settings(self):
        window = self._window_with_job()
        try:
            window.chk_subtitles.setChecked(True)
            window.edit_sub_file_path.setText("/tmp/meine_untertitel.srt")
            window.combo_sub_mode.setCurrentText("Hard-Untertitel (in Video einbrennen)")
            self.app.processEvents()

            window.combo_format.setCurrentText("HEVC / H.265 (MP4)")
            self.app.processEvents()

            settings = window.jobs[0]["settings"]
            self.assertTrue(settings.get("subtitles_enabled"))
            self.assertEqual(settings.get("subtitles_file_path"), "/tmp/meine_untertitel.srt")
            self.assertEqual(settings.get("subtitles_mode"), "Hard-Untertitel (in Video einbrennen)")
            self.assertTrue(window.chk_subtitles.isChecked())
        finally:
            window.close()

    def test_preset_switch_keeps_subtitle_settings(self):
        window = self._window_with_job()
        try:
            window.chk_subtitles.setChecked(True)
            window.edit_sub_file_path.setText("/tmp/meine_untertitel.srt")
            self.app.processEvents()

            window.combo_preset.setCurrentText("MP4 (H.265 / AAC) - Hocheffizient (CRF 23)")
            self.app.processEvents()

            settings = window.jobs[0]["settings"]
            self.assertTrue(settings.get("subtitles_enabled"))
            self.assertEqual(settings.get("subtitles_file_path"), "/tmp/meine_untertitel.srt")
        finally:
            window.close()

    def test_job_in_ai_pipeline_stage_is_locked(self):
        # Auch die KI-Phasen (nicht nur "Codiert...") müssen das Panel sperren
        window = self._window_with_job()
        try:
            window.jobs[0]["status"] = "KI-Transkription..."
            window._on_job_selection_changed()
            self.assertFalse(window.settings_widget.isEnabled())
            self.assertNotIn(0, window._editable_job_indexes())

            # _save_ui_settings_to_job darf den laufenden Job nicht anfassen
            container_before = window.jobs[0]["settings"].get("container")
            window.combo_format.blockSignals(True)
            window.combo_format.setCurrentText("Universal-Container (MKV)")
            window.combo_format.blockSignals(False)
            window._save_ui_settings_to_job()
            self.assertEqual(window.jobs[0]["settings"].get("container"), container_before)
        finally:
            window.jobs[0]["status"] = "Bereit"
            window.close()

    def test_duplicate_outputs_are_skipped_on_start(self):
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()
            # Beide Jobs zeigen auf dieselbe Standard-Ausgabedatei
            self.assertEqual(window.jobs[0]["output_file"], window.jobs[1]["output_file"])

            window._on_start_queue()
            self.assertEqual(window.jobs[1]["status"], "Fehlgeschlagen")
            window._on_stop_queue()
            self.app.processEvents()
        finally:
            window.close()

    def test_output_equals_other_jobs_input_is_blocked(self):
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            self.app.processEvents()
            window.jobs[0]["status"] = "Fertig"  # Job 0 nicht mehr "Bereit"
            job = window.jobs[1]
            job["output_file"] = window.jobs[0]["input_file"]

            window.is_running = True
            window.current_job_idx = 1
            window._start_current_ffmpeg_job(job)
            self.app.processEvents()

            self.assertIsNone(window.active_worker)
            self.assertEqual(job["status"], "Fehlgeschlagen")
            self.assertFalse(window.is_running)
        finally:
            window.close()

    def test_apply_to_all_does_not_copy_transient_keys(self):
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()
            window.queue_table.selectRow(0)
            window.jobs[0]["settings"]["temp_srt_path"] = "/tmp/nur_fuer_job0.srt"
            window.jobs[0]["settings"]["_subtitle_ai_stage"] = "translate"

            window._on_apply_settings_to_all_clicked()
            self.app.processEvents()

            other = window.jobs[1]["settings"]
            self.assertNotIn("temp_srt_path", other)
            self.assertNotIn("_subtitle_ai_stage", other)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
