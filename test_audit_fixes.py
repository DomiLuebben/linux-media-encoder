# -*- coding: utf-8 -*-
"""Regressionstests für die Audit-Fixes (Code-Audit 2026-07-05)."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

import presets
from ffmpeg_worker import FFmpegWorker
from mainwindow import MainWindow
from subtitle_editor_dialog import SubtitleEditorDialog
import subtitle_utils


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
        try:
            with open(worker.temp_output_file, "w") as f:
                f.write("mock")
        except OSError:
            pass
        results = []
        worker.finished.connect(lambda ok, msg: results.append((ok, msg)))
        worker._handle_finished(0, QProcess.ExitStatus.NormalExit)
        self.assertTrue(results[0][0])
        if os.path.exists("out.mp4"):
            try:
                os.remove("out.mp4")
            except OSError:
                pass


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

    def test_mainwindow_queue_delete_shifts_current_job_idx(self):
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()

            # Pretend job 2 is active
            window.current_job_idx = 2
            window.is_running = True

            # Delete job 0 (which is before job 2)
            window.queue_table.selectRow(0)
            window._on_remove_selected_clicked()
            self.app.processEvents()

            # current_job_idx should shift from 2 to 1!
            self.assertEqual(window.current_job_idx, 1)
        finally:
            window.close()

    def test_mainwindow_low_bitrate_roundtrips_without_clamping(self):
        window = self._window_with_job()
        try:
            job = window.jobs[0]
            job["settings"].update({
                "encoding_mode": "vbr",
                "crf": "",
                "video_bitrate": "33k",
                "audio_bitrate": "22k",
            })
            window._load_job_settings_to_ui(job)

            self.assertAlmostEqual(window.spin_bitrate_val.value(), 0.033, places=3)
            self.assertEqual(window.spin_bitrate_val.decimals(), 3)

            window._save_ui_settings_to_job()
            self.assertEqual(job["settings"]["video_bitrate"], "33k")
            self.assertEqual(job["settings"]["audio_bitrate"], "22k")
        finally:
            window.close()


class WorkerAtomicFileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_worker_temp_file_renamed_on_success_and_removed_on_failure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            in_file = os.path.join(tmpdir, "in.mp4")
            out_file = os.path.join(tmpdir, "out.mp4")
            with open(in_file, "w", encoding="utf-8") as f:
                f.write("source")

            worker = FFmpegWorker(in_file, out_file, ["-i", in_file, out_file])
            worker2 = FFmpegWorker(in_file, out_file, ["-i", in_file, out_file])
            self.assertTrue(worker.temp_output_file.startswith(os.path.join(tmpdir, ".lme_tmp_")))
            self.assertEqual(os.path.splitext(worker.temp_output_file)[1], ".mp4")
            self.assertNotEqual(worker.temp_output_file, worker2.temp_output_file)

            # Fehler/Abbruch darf eine bereits vorhandene Zieldatei nicht
            # beschädigen und muss nur die partielle Staging-Datei entfernen.
            with open(out_file, "w", encoding="utf-8") as f:
                f.write("original")
            with open(worker.temp_output_file, "w", encoding="utf-8") as f:
                f.write("partial")
            worker._handle_finished(1, QProcess.ExitStatus.NormalExit)
            with open(out_file, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "original")
            self.assertFalse(os.path.exists(worker.temp_output_file))

            # Erfolg ersetzt das alte Ziel atomar durch das vollständige Staging.
            with open(worker2.temp_output_file, "w", encoding="utf-8") as f:
                f.write("encoded")
            worker2._handle_finished(0, QProcess.ExitStatus.NormalExit)
            with open(out_file, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "encoded")
            self.assertFalse(os.path.exists(worker2.temp_output_file))


class IntelligentBitrateCalculatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_low_bitrate_calculation_does_not_overshoot(self):
        from intelligent_dialog import IntelligentBitrateDialog
        # duration = 3600 seconds, size = 25 MB
        # available bitrate will be around 55 kbps.
        # The fix should allocate 22 kbps audio and 33 kbps video.
        dialog = IntelligentBitrateDialog(duration_sec=3600, codec="h264", parent=None)
        try:
            dialog.spin_size.setValue(25)
            dialog._calculate_formula()

            self.assertEqual(dialog.result_audio_bitrate_kbps, "22k")
            self.assertEqual(dialog.result_video_bitrate_mbps, 0.033)
            available_kbps = 25 * 1024 * 1024 * 8 / 3600 * 0.95 / 1000
            allocated_kbps = (
                dialog.result_video_bitrate_mbps * 1000
                + int(dialog.result_audio_bitrate_kbps.removesuffix("k"))
            )
            self.assertLessEqual(allocated_kbps, available_kbps)
        finally:
            dialog.close()

    def test_threshold_bitrate_calculation_does_not_overshoot(self):
        from intelligent_dialog import IntelligentBitrateDialog

        # Rund 110 kbit/s treffen den früher fehlerhaften Bereich, in dem
        # 96k Audio plus erzwungene 50k Video mehr als das Budget ergaben.
        dialog = IntelligentBitrateDialog(duration_sec=3600, codec="h264", parent=None)
        try:
            dialog.spin_size.setValue(50)
            dialog._calculate_formula()
            available_kbps = 50 * 1024 * 1024 * 8 / 3600 * 0.95 / 1000
            allocated_kbps = (
                dialog.result_video_bitrate_mbps * 1000
                + int(dialog.result_audio_bitrate_kbps.removesuffix("k"))
            )
            self.assertLessEqual(allocated_kbps, available_kbps)
        finally:
            dialog.close()

    def test_impossible_target_size_is_rejected(self):
        from intelligent_dialog import IntelligentBitrateDialog

        dialog = IntelligentBitrateDialog(duration_sec=1_000_000, codec="h264", parent=None)
        try:
            dialog.spin_size.setValue(1)
            dialog._calculate_formula()
            ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
            self.assertFalse(ok_button.isEnabled())
            self.assertIn("Zielgröße zu klein", dialog.lbl_status.text())
        finally:
            dialog.close()


class SubtitleOverwriteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_invalid_srt_does_not_truncate_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "video.mp4")
            srt_file = os.path.join(tmpdir, "video.srt")
            with open(srt_file, "w", encoding="utf-8") as f:
                f.write("ORIGINAL")

            dialog = SubtitleEditorDialog(
                input_file="unused.mp4",
                output_file=output_file,
                source_lang=subtitle_utils.AUTO_LANGUAGE,
                target_lang=subtitle_utils.NO_TRANSLATION,
                auto_start=False,
            )
            try:
                dialog.txt_editor.setPlainText("keine gültige SRT-Datei")
                with (
                    patch.object(
                        QMessageBox,
                        "question",
                        return_value=QMessageBox.StandardButton.Yes,
                    ),
                    patch.object(QMessageBox, "critical"),
                ):
                    dialog._on_save_subtitles()

                with open(srt_file, "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), "ORIGINAL")
                self.assertIsNone(dialog.get_saved_srt_path())
            finally:
                dialog.close()

if __name__ == "__main__":
    unittest.main()
