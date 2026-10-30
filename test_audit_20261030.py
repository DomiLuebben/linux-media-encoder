"""Runtime regressions for the October audit, without optical hardware."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from PyQt6.QtCore import QCoreApplication, QEvent, QProcess
from PyQt6.QtWidgets import QApplication

from export_settings_dialog import ExportSettingsDialog
from ffmpeg_worker import FFmpegWorker
from disc_rip_worker import AudioCdRipWorker, IsoDumpWorker
from disc_ripper_dialog import DiscRipperDialog
from optical_media import AudioTrackInfo
from mainwindow import MainWindow
import presets


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = str(Path("test_input.mp4").resolve())

    def wait_until(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            time.sleep(0.005)
        self.assertTrue(predicate(), "operation timed out")

    def dialog(self):
        # Real FFmpeg previews, independent of background metadata timing.
        with patch.object(ExportSettingsDialog, "_start_probe"):
            dialog = ExportSettingsDialog(self.source, str(self.root / "out.mp4"),
                                          dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"]))
        self.addCleanup(dialog.reject)
        return dialog

    def window(self):
        with patch.object(MainWindow, "_prefetch_source_info"):
            window = MainWindow()
        self.addCleanup(window.close)
        return window

    def test_empty_success_never_overwrites_existing_target(self):
        target = self.root / "out.mp4"
        target.write_bytes(b"previous good output")
        worker = FFmpegWorker(self.source, str(target), [])
        Path(worker.temp_output_file).touch()
        results = []
        worker.finished.connect(lambda ok, msg: results.append(ok))
        worker._handle_finished(0, QProcess.ExitStatus.NormalExit)
        self.assertEqual(results, [False])
        self.assertEqual(target.read_bytes(), b"previous good output")
        self.assertFalse(Path(worker.temp_output_file).exists())

    def test_late_success_after_cancel_cannot_publish(self):
        target = self.root / "out.mp4"
        target.write_bytes(b"original")
        worker = FFmpegWorker(self.source, str(target), [])
        worker._emit_finished(False, "cancelled")
        Path(worker.temp_output_file).write_bytes(b"late result")
        worker._handle_finished(0, QProcess.ExitStatus.NormalExit)
        self.assertEqual(target.read_bytes(), b"original")

    def test_start_is_nonblocking_and_cannot_launch_twice(self):
        worker = FFmpegWorker(self.source, str(self.root / "out.mkv"),
                              ["-y", "-re", "-i", self.source, "-c", "copy", str(self.root / "out.mkv")])
        self.addCleanup(worker.stop)
        with patch.object(QProcess, "waitForStarted", side_effect=AssertionError("GUI must not wait")):
            worker.start()
        first = worker.process
        worker.start()
        self.assertIs(worker.process, first)

    def test_stop_before_start_is_terminal(self):
        worker = FFmpegWorker(self.source, str(self.root / "out.mp4"), [])
        results = []
        worker.finished.connect(lambda ok, msg: results.append(ok))
        worker.stop()
        self.assertEqual(results, [False])
        worker.start()
        self.assertIsNone(worker.process)

    def test_remaining_time_cannot_be_negative(self):
        worker = FFmpegWorker(self.source, str(self.root / "out.mp4"), [], total_duration=1)
        progress = []
        worker.progress_updated.connect(lambda pct, speed, remaining: progress.append(remaining))
        worker._parse_progress_line("out_time_us=2000000")
        worker._parse_progress_line("speed=1.0x")
        worker._parse_progress_line("progress=continue")
        self.assertEqual(progress, ["0s"])

    def test_nonfinite_times_are_rejected(self):
        for text in ("inf", "Infinity", "nan", "1e999", "00:00:inf", "0:nan"):
            with self.subTest(text=text):
                self.assertIsNone(ExportSettingsDialog._parse_timecode(text))
        for value in (float("inf"), float("nan"), "1e999"):
            self.assertIsNone(presets.parse_seconds(value))

    def test_nonfinite_crf_falls_back_to_valid_quality(self):
        for value in ("nan", "inf", "1e999"):
            args = presets.get_ffmpeg_args(self.source, str(self.root / "out.mp4"),
                                          dict(video_codec="libx264", encoding_mode="crf", crf=value))
            self.assertEqual(args[args.index("-crf") + 1], "23")

    def test_preview_files_and_processes_are_bounded(self):
        dialog = self.dialog()
        for n in range(8):
            dialog._trigger_preview_update(seek_seconds=n / 20)
            self.wait_until(lambda: dialog._preview_proc is None)
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertLessEqual(len(dialog._preview_temp_files), 1)
        self.assertTrue(Path(dialog.preview_frame_path).is_file())
        self.assertLessEqual(len(dialog.findChildren(QProcess)), 1)

    def test_rejected_dialog_cannot_restart_debounced_preview(self):
        dialog = self.dialog()
        dialog._preview_debounce.start()
        dialog.reject()
        self.assertFalse(dialog._preview_debounce.isActive())
        dialog._trigger_preview_update()
        self.assertIsNone(dialog._preview_proc)
        self.assertEqual(dialog._preview_temp_files, set())

    def test_missing_ffmpeg_preview_leaves_no_staging_files(self):
        dialog = self.dialog()
        self.wait_until(lambda: dialog._preview_proc is None)
        with patch.dict(os.environ, {"PATH": str(self.root)}):
            dialog._trigger_preview_update()
            self.wait_until(lambda: dialog._preview_proc is None)
        self.assertLessEqual(len(dialog._preview_temp_files), 1)

    def test_odd_source_dimensions_encode_successfully(self):
        source = self.root / "odd.mkv"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc=size=65x49:rate=5", "-t", "0.2", "-c:v", "ffv1", str(source)],
                       check=True, capture_output=True, timeout=10)
        out = self.root / "even.mp4"
        args = presets.get_ffmpeg_args(str(source), str(out),
                                      dict(video_codec="libx264", audio_codec="none", scale_mode="source"))
        result = subprocess.run(["ffmpeg", "-v", "error", *args], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams",
                                                   "-of", "json", str(out)], timeout=10))
        self.assertEqual((info["streams"][0]["width"], info["streams"][0]["height"]), (64, 48))

    def test_unusable_rip_directory_reports_error_instead_of_raising(self):
        blocker = self.root / "not-a-directory"
        blocker.touch()
        for worker in (AudioCdRipWorker("/dev/test", [AudioTrackInfo(1, 1)], str(blocker)),
                       IsoDumpWorker("/dev/test", str(blocker / "out.iso"))):
            results = []
            worker.finished.connect(lambda ok, msg: results.append(ok))
            worker.start()
            self.assertEqual(results, [False])

    def test_rip_dialog_handles_unusable_directory(self):
        blocker = self.root / "not-a-directory"
        blocker.touch()
        dialog = SimpleNamespace(_inspection_task=None, current_source="/dev/test",
                                 edit_output_dir=SimpleNamespace(text=lambda: str(blocker)))
        with patch("disc_ripper_dialog.QMessageBox.warning") as warning:
            DiscRipperDialog._on_action_clicked(dialog)
        warning.assert_called_once()

    def test_completed_cd_processes_are_released_between_tracks(self):
        source = self.root / "audio.wav"
        with wave.open(str(source), "wb") as wav:
            wav.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
            wav.writeframes(b"\x00\x00" * 4410)
        worker = AudioCdRipWorker("/dev/test", [AudioTrackInfo(n, 0.1) for n in range(1, 4)], str(self.root))
        self.addCleanup(worker.stop)
        results = []
        worker.finished.connect(lambda ok, msg: results.append(ok))
        with patch("disc_rip_worker.build_audio_cd_rip_command", side_effect=lambda device, track, out:
                   ["cp", str(source), out]):
            worker.start()
            self.wait_until(lambda: bool(results))
        self.assertEqual(results, [True])
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(worker.findChildren(QProcess), [])

    def test_repeated_export_dialogs_are_released_by_main_window(self):
        window = self.window()
        with patch.object(window, "_prefetch_source_info"):
            window._add_file_to_queue(self.source)
        with patch.object(ExportSettingsDialog, "_start_probe"), \
             patch.object(ExportSettingsDialog, "exec", new=lambda dialog: (dialog.reject(), 0)[1]):
            for _ in range(6):
                window._open_export_settings_dialog_for_row(0)
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(window.findChildren(ExportSettingsDialog), [])

    def test_rip_workers_finish_once_when_stopped_repeatedly(self):
        for worker in (AudioCdRipWorker("/dev/test", [], str(self.root)),
                       IsoDumpWorker("/dev/test", str(self.root / "out.iso"))):
            results = []
            worker.finished.connect(lambda ok, msg: results.append(ok))
            worker.stop()
            worker.stop()
            self.assertEqual(results, [False])

    def test_cancelled_preview_files_are_removed_before_dialog_closes(self):
        dialog = self.dialog()
        for n in range(12):
            dialog._trigger_preview_update(seek_seconds=n / 100)
            self.app.processEvents()
        self.wait_until(lambda: dialog._preview_proc is None and not dialog._retained_procs)
        self.assertLessEqual(len(dialog._preview_temp_files), 1)

    def test_session_skips_malformed_entries(self):
        window = self.window()
        with patch.object(window.settings_store, "value", side_effect=lambda key, default=None:
                          json.dumps([None, 42, "bad", {"input_file": self.source, "settings": {}}])
                          if key == "queue_json" else default), \
             patch.object(window, "_prefetch_source_info"):
            window._restore_session_state()
        self.assertEqual(len(window.jobs), 1)

    def test_session_restores_bluray_protocol_and_normalizes_busy_status(self):
        window = self.window()
        entry = {"input_file": f"bluray:{self.root}", "output_file": str(self.root / "out.mkv"),
                 "settings": {"container": "mkv", "disc_type": "bluray"}, "status": "Codiert..."}
        with patch.object(window.settings_store, "value", side_effect=lambda key, default=None:
                          json.dumps([entry]) if key == "queue_json" else default), \
             patch.object(window, "_prefetch_source_info"):
            window._restore_session_state()
        self.assertEqual(len(window.jobs), 1)
        self.assertEqual(window.jobs[0]["status"], "Bereit")

    def test_probe_ignores_attached_cover_art(self):
        dialog = self.dialog()
        data = {"streams": [
            {"codec_type": "video", "width": 600, "height": 600, "disposition": {"attached_pic": 1}},
            {"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "h264"}]}
        info = dialog._parse_probe_json(json.dumps(data))
        self.assertEqual((info["width"], info["height"]), (1920, 1080))

    def test_many_probes_have_bounded_concurrency(self):
        from media_probe import submit_probe
        release = threading.Event()
        lock = threading.Lock()
        started, finished = [], []
        def work():
            with lock:
                started.append(1)
            release.wait(3)
            with lock:
                finished.append(1)
        try:
            for _ in range(60):
                submit_probe(work)
            self.wait_until(lambda: len(started) >= 4)
            time.sleep(0.05)
            self.assertEqual(len(started), 4)
        finally:
            release.set()
        self.wait_until(lambda: len(finished) == 60)


if __name__ == "__main__":
    unittest.main()
