"""Regression checks for disc input identity and two-stage stream mapping."""
import os
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import optical_media
import presets
from mainwindow import MainWindow


def queue_window(job):
    return SimpleNamespace(
        jobs=[job], current_job_idx=0, is_running=True,
        console=Mock(), settings_store=Mock(), active_worker=None,
        _configured_staging_dir=lambda: "", _update_table_row=Mock(),
        _phase_status=lambda job, text: text, _on_job_selection_changed=Mock(),
        _on_worker_progress=Mock(), _on_worker_log=Mock(),
        _on_worker_status=Mock(), _on_worker_finished=Mock(),
        _on_disc_rip_stage_finished=Mock(),
    )


class DiscAuditTests(unittest.TestCase):
    def test_main_title_is_not_lost_beyond_playlist_limit(self):
        def probe(path, number):
            return optical_media.VideoTitleInfo(
                title_num=number if number is not None else -1,
                duration_sec=7200 if number is None else 10)
        with patch("optical_media.list_bluray_playlists", return_value=list(range(50))), \
             patch("optical_media.read_bdinfo_header", return_value={}), \
             patch("optical_media._probe_bluray_playlist", side_effect=probe):
            result = optical_media.scan_bluray_source("/disc")
        self.assertEqual(result.video_titles[result.main_title_idx].duration_sec, 7200)

    def test_playlist_zero_survives_stage_one(self):
        with tempfile.TemporaryDirectory() as root:
            job = dict(input_file=root, output_dir=root,
                       settings=dict(disc_type="bluray", title_num=0))
            win = queue_window(job)
            with patch("optical_media.choose_staging_dir", return_value=(root, [])), \
                 patch("mainwindow.FFmpegWorker") as worker:
                MainWindow._run_disc_rip_stage(win, job)
            args = worker.call_args.args[2]
            self.assertEqual(args[args.index("-playlist") + 1], "0")

    def test_selected_streams_are_renumbered_only_for_stage_two(self):
        with tempfile.TemporaryDirectory() as root:
            source = os.path.join(root, "stage.mkv")
            with open(source, "wb") as f:
                f.write(b"fixture")
            for selected in (0, 1, 3, -1):
                with self.subTest(selected=selected):
                    settings = dict(container="mkv", video_codec="copy", audio_codec="copy",
                                    disc_type="bluray", input_args=["-playlist", "0"],
                                    audio_stream_idx=selected, subtitle_stream_idx=selected,
                                    _staged_source=source)
                    job = dict(input_file=root, output_file=os.path.join(root, "out.mkv"),
                               settings=settings)
                    win = queue_window(job)
                    with patch("mainwindow.FFmpegWorker") as worker:
                        MainWindow._start_current_ffmpeg_job(win, job)
                    args = worker.call_args.args[2]
                    expected = "?" if selected == -1 else ":0?"
                    self.assertIn("0:a" + expected, args)
                    self.assertIn("0:s" + expected, args)
                    self.assertNotIn("-playlist", args)
                    self.assertEqual(settings["audio_stream_idx"], selected)
                    self.assertEqual(settings["subtitle_stream_idx"], selected)

    def test_bdmv_folder_is_normalized_for_direct_and_queue_rip(self):
        with tempfile.TemporaryDirectory() as root:
            bdmv = os.path.join(root, "BDMV")
            os.mkdir(bdmv)
            direct, _ = optical_media.build_bluray_rip_args(bdmv, playlist_num=0)
            queued = presets.get_ffmpeg_args(bdmv, "out.mkv", dict(
                disc_type="bluray", container="mkv", video_codec="copy", audio_codec="copy"))
            for args in (direct, queued):
                self.assertEqual(args[args.index("-i") + 1], "bluray:" + root)

    def test_real_two_stage_media_keeps_selected_audio_and_subtitle(self):
        with tempfile.TemporaryDirectory() as root:
            source, staged, final = (os.path.join(root, n) for n in ("in.mkv", "stage.mkv", "out.mkv"))
            sub = os.path.join(root, "sub.srt")
            with open(sub, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:01,000\nSelected subtitle\n")
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=64x64:d=1",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=880:duration=1", "-i", sub,
                "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s", "-map", "3:s",
                "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=deu",
                "-metadata:s:s:1", "language=deu", "-c:v", "ffv1", "-c:a", "flac",
                "-c:s", "srt", source], check=True, capture_output=True, timeout=20)
            args, _ = optical_media.build_bluray_rip_args(
                source, playlist_num=0, audio_stream_idx=1, subtitle_stream_idx=1,
                output_file=staged, remux_mkv=True, ignore_errors=False)
            # Optical transport is replaced by a generated file; all mapping
            # and both actual remux operations use production-generated args.
            args = args[:1] + args[3:]
            args[args.index("-i") + 1] = source
            subprocess.run(["ffmpeg", "-v", "error"] + args,
                           check=True, capture_output=True, timeout=20)
            job = dict(input_file=source, output_file=final, settings=dict(
                container="mkv", video_codec="copy", audio_codec="copy",
                disc_type="bluray", _staged_source=staged,
                audio_stream_idx=1, subtitle_stream_idx=1))
            with patch("mainwindow.FFmpegWorker") as worker:
                MainWindow._start_current_ffmpeg_job(queue_window(job), job)
            subprocess.run(["ffmpeg", "-v", "error"] + worker.call_args.args[2],
                           check=True, capture_output=True, timeout=20)
            data = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams",
                "-of", "json", final], check=True, capture_output=True, text=True, timeout=10).stdout)
            streams = data["streams"]
            self.assertEqual([s["codec_type"] for s in streams], ["video", "audio", "subtitle"])
            self.assertEqual([s["tags"]["language"] for s in streams[1:]], ["deu", "deu"])


class InspectionCancellationTests(unittest.TestCase):
    def test_cancel_terminates_and_reaps_running_probe(self):
        cancel = threading.Event()
        processes, errors = [], []
        real_popen = subprocess.Popen
        def spawn(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process
        def run():
            optical_media._inspection_context.cancel = cancel
            try:
                optical_media._run_inspection_command(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    capture_output=True, timeout=40)
            except optical_media.InspectionCancelled:
                errors.append("cancelled")
            finally:
                optical_media._inspection_context.cancel = None
        with patch("optical_media.subprocess.Popen", side_effect=spawn):
            thread = threading.Thread(target=run)
            thread.start()
            deadline = time.monotonic() + 2
            while not processes and time.monotonic() < deadline:
                time.sleep(0.01)
            cancel.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ["cancelled"])
        self.assertTrue(processes)
        self.assertIsNotNone(processes[0].returncode)

    def test_probe_timeout_still_terminates_process(self):
        optical_media._inspection_context.cancel = threading.Event()
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                optical_media._run_inspection_command(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    capture_output=True, timeout=0.05)
        finally:
            optical_media._inspection_context.cancel = None


class AsyncDiscDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_responsive_cancel_rescan_and_close(self):
        from disc_ripper_dialog import DiscRipperDialog
        from PyQt6.QtCore import QTimer
        started = threading.Event()
        def scan(path, cancel):
            started.set()
            cancel.wait(2)
            raise optical_media.InspectionCancelled()
        with patch("optical_media.scan_optical_drives", return_value=[]), \
             patch("optical_media.check_optical_environment", return_value=[]), \
             patch("optical_media.inspect_source", side_effect=scan):
            dialog = DiscRipperDialog(initial_source="/disc")
            try:
                self.assertTrue(started.wait(1))
                self.assertFalse(dialog.btn_action.isEnabled())
                self.assertFalse(dialog.source_group.isEnabled())
                self.assertEqual(dialog.prog_bar.maximum(), 0)
                heartbeat = []
                QTimer.singleShot(0, lambda: heartbeat.append(True))
                self.app.processEvents()
                self.assertTrue(heartbeat, "Qt must remain responsive during inspection")
                first = dialog._inspection_task
                dialog._on_stop_clicked()
                self.assertTrue(first["done"].wait(1))
                dialog._poll_inspection()
                self.assertIsNone(dialog.inspection_result)
                self.assertTrue(dialog.source_group.isEnabled())
                dialog._inspect_and_display_source("/other")
                second = dialog._inspection_task
                dialog.reject()
                self.assertTrue(second["cancel"].is_set())
                self.assertTrue(second["done"].wait(1))
                self.assertFalse(dialog._inspection_timer.isActive())
            finally:
                dialog.close()

    def test_superseded_result_cannot_overwrite_new_source(self):
        from disc_ripper_dialog import DiscRipperDialog
        release = threading.Event()
        def scan(path, cancel):
            if path == "/old":
                release.wait(2)
            return optical_media.DiscInspectionResult(
                source_path=path, disc_type=optical_media.DiscType.UNKNOWN, error=path)
        with patch("optical_media.scan_optical_drives", return_value=[]), \
             patch("optical_media.check_optical_environment", return_value=[]), \
             patch("optical_media.inspect_source", side_effect=scan):
            dialog = DiscRipperDialog(initial_source="/old")
            try:
                old = dialog._inspection_task
                dialog._inspect_and_display_source("/new")
                self.assertTrue(dialog._inspection_task["done"].wait(1))
                dialog._poll_inspection()
                release.set()
                self.assertTrue(old["done"].wait(1))
                self.app.processEvents()
                self.assertEqual(dialog.inspection_result.source_path, "/new")
            finally:
                release.set()
                dialog.close()


if __name__ == "__main__":
    unittest.main()
