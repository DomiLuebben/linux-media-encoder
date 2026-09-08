"""Runtime regressions for the 2026-09-08 audit; no optical drive required."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

from PyQt6.QtCore import QProcess
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QMessageBox

from disc_rip_worker import AudioCdRipWorker, IsoDumpWorker, audio_cd_output_filename
from mainwindow import MainWindow
from optical_media import AudioTrackInfo

SRT = "1\n00:00:00,000 --> 00:00:00,100\nHallo\n"


class AuditRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lme_audit_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.wav = self.root / "source.wav"
        with wave.open(str(self.wav), "wb") as wav:
            wav.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
            wav.writeframes(b"\x10\x00" * 8820)
        self.windows = []
        self.processes = []
        self.addCleanup(self.cleanup_ui)

    def cleanup_ui(self):
        for proc in self.processes:
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.kill()
                proc.waitForFinished(3000)
        for win in self.windows:
            win.is_running = False
            win.close()
        self.app.processEvents()

    def window(self):
        with patch.object(MainWindow, "_prefetch_source_info"):
            win = MainWindow()
            win._add_file_to_queue(str(self.wav))
        self.windows.append(win)
        win._notify = lambda *args, **kwargs: None
        win.current_job_idx = 0
        job = win.jobs[0]
        job["output_file"] = str(self.root / "out.flac")
        job["output_dir"] = str(self.root)
        return win, job

    def sleeper(self, win, wait=True):
        proc = QProcess(win)
        self.processes.append(proc)
        proc.start(sys.executable, ["-c", "import time; time.sleep(30)"])
        if wait:
            self.assertTrue(proc.waitForStarted(3000))
        return proc

    def wait_until(self, predicate):
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate(), "Asynchronous operation did not finish")

    def test_direct_audio_cd_rip_reaches_real_ffmpeg_and_keeps_tags(self):
        # Only the hardware boundary is replaced. The worker must generate and
        # launch the real encoder command, publish its result and remove WAVs.
        tracks = [AudioTrackInfo(track_num=n, duration_sec=0.2, title=f"Titel {n}",
                                 artist="Test", album="Audit") for n in (1, 2)]
        for codec, expected_codec in (("flac", "flac"), ("aac", "aac"),
                                      ("mp3", "mp3"), ("opus", "opus"),
                                      ("alac", "alac"), ("wav", "pcm_s16le")):
            with self.subTest(codec=codec):
                target = self.root / codec
                worker = AudioCdRipWorker("/dev/test", tracks, str(target), codec=codec)
                results = []
                worker.finished.connect(lambda ok, msg: results.append((ok, msg)))
                def fake_disc(device, track, output):
                    return [sys.executable, "-c",
                            "import shutil,sys; shutil.copyfile(sys.argv[1],sys.argv[2])",
                            str(self.wav), output]
                with patch("disc_rip_worker.build_audio_cd_rip_command", side_effect=fake_disc):
                    worker.start()
                    self.wait_until(lambda: bool(results))
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0][0], results)
                for track in tracks:
                    out = target / audio_cd_output_filename(track, codec)
                    probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams",
                                            "-show_format", "-of", "json", str(out)],
                                           capture_output=True, text=True, timeout=10, check=True)
                    data = json.loads(probe.stdout)
                    self.assertEqual(data["streams"][0]["codec_name"], expected_codec)
                    tags = {k.lower(): v for item in [data["format"], *data["streams"]]
                            for k, v in item.get("tags", {}).items()}
                    self.assertEqual(tags["title"], track.title)
                    self.assertEqual(tags["artist"], "Test")
                self.assertEqual(list(target.glob(".lme_tmp_*")), [])

    def test_direct_audio_cd_no_output_is_failure(self):
        worker = AudioCdRipWorker("/dev/test", [AudioTrackInfo(track_num=1, duration_sec=0.2)], str(self.root))
        worker._tmp_wav_file = str(self.wav)
        worker._tmp_out_file = str(self.root / "missing.flac")
        worker._final_out_file = str(self.root / "old.flac")
        Path(worker._final_out_file).write_bytes(b"original")
        worker._current_step = "encode"
        results = []
        worker.finished.connect(lambda ok, msg: results.append((ok, msg)))
        worker._handle_step_finished(0, QProcess.ExitStatus.NormalExit)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0][0], results)
        self.assertEqual(Path(worker._final_out_file).read_bytes(), b"original")

    def test_audio_cd_queue_respects_mp3_preset_and_trim(self):
        win, job = self.window()
        # A CD job after choosing the ordinary MP3 preset in the queue UI.
        job["settings"].update(disc_type="audio_cd", track_num=1,
                               track_title="Queue-Test")
        win._on_format_changed("MP3 (Nur Audio)")
        job["settings"].update(_extracted_wav=str(self.wav), trim_end=0.1)
        win.is_running = True
        job["status"] = "Bereit"
        win._start_current_ffmpeg_job(job)
        worker = win.active_worker
        self.assertIsNotNone(worker)
        self.wait_until(lambda: worker._finished_emitted)
        self.assertEqual(job["status"], "Fertig", job.get("error_tail"))
        data = json.loads(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
             job["output_file"]], text=True, timeout=10))
        self.assertEqual(data["streams"][0]["codec_name"], "mp3")
        self.assertEqual(data["format"]["tags"]["title"], "Queue-Test")
        self.assertLess(float(data["format"]["duration"]), 0.18)
        self.assertFalse(self.wav.exists())

    def test_close_stops_audio_cd_extraction(self):
        win, job = self.window()
        win.is_running = True
        job["status"] = "Liest Disc..."
        job["settings"]["_extracted_wav"] = str(self.root / "partial.wav")
        Path(job["settings"]["_extracted_wav"]).write_bytes(b"partial")
        win.cd_extract_process = self.sleeper(win)
        with patch("mainwindow.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            win.closeEvent(QCloseEvent())
        self.assertEqual(win.cd_extract_process.state(), QProcess.ProcessState.NotRunning)
        self.assertEqual(job["status"], "Abgebrochen")
        self.assertFalse((self.root / "partial.wav").exists())

    def test_stop_reaps_helpers_even_while_starting(self):
        for attr in ("sub_process", "sub_ai_process", "cd_extract_process"):
            for wait in (False, True):
                with self.subTest(helper=attr, started=wait):
                    win, job = self.window()
                    win.is_running = True
                    job["status"] = "Audio extrahieren..."
                    proc = self.sleeper(win, wait=wait)
                    setattr(win, attr, proc)
                    win._on_stop_queue()
                    self.assertEqual(proc.state(), QProcess.ProcessState.NotRunning)
                    self.assertEqual(job["status"], "Abgebrochen")

    def test_direct_rip_stop_reaps_a_starting_process(self):
        win, _ = self.window()
        workers = [AudioCdRipWorker("/dev/test", [], str(self.root)),
                   IsoDumpWorker("/dev/test", str(self.root / "disc.iso"))]
        for worker in workers:
            with self.subTest(worker=type(worker).__name__):
                worker.process = self.sleeper(win, wait=False)
                worker.stop()
                self.assertEqual(worker.process.state(), QProcess.ProcessState.NotRunning)

    def test_direct_fallback_preserves_requested_subtitle_generation(self):
        win, job = self.window()
        win.is_running = True
        job["settings"].update(disc_type="dvd_video", two_stage=True,
                               subtitles_enabled=True)
        with patch("optical_media.choose_staging_dir", return_value=(None, [])), \
             patch.object(win, "_run_subtitle_pipeline") as subtitles, \
             patch.object(win, "_start_current_ffmpeg_job") as encode:
            win._run_disc_rip_stage(job)
        subtitles.assert_called_once_with(job)
        encode.assert_not_called()

    def test_stop_cleans_staged_media_during_subtitle_phase(self):
        win, job = self.window()
        win.is_running = True
        job["status"] = "KI-Transkription..."
        for key in ("_staged_source", "temp_audio_path"):
            path = self.root / key
            path.write_bytes(b"temporary")
            job["settings"][key] = str(path)
        win.sub_ai_process = self.sleeper(win)
        win._on_stop_queue()
        self.assertFalse((self.root / "_staged_source").exists())
        self.assertFalse((self.root / "temp_audio_path").exists())

    def test_cancelled_stage_callback_cannot_start_a_restarted_job(self):
        win, job = self.window()
        win.is_running = True
        job["status"] = "Liest Disc..."
        with patch.object(win, "_start_current_ffmpeg_job") as encode:
            win._on_disc_rip_stage_finished(True, "done")
            win._on_stop_queue()
            job["status"] = "Bereit"
            with patch.object(win, "_process_next_job"):
                win._on_start_queue()
            self.app.processEvents()
            encode.assert_not_called()

    def test_duplicate_outputs_through_directory_symlink_are_rejected(self):
        win, job = self.window()
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        win._duplicate_job(0)
        win.jobs[1]["output_file"] = str(alias / "out.flac")
        with patch.object(win, "_process_next_job"):
            win._on_start_queue()
        self.assertEqual(win.jobs[1]["status"], "Fehlgeschlagen")

    def test_generated_external_subtitle_with_temp_like_name_is_preserved(self):
        win, job = self.window()
        job["output_file"] = str(self.root / "lme_temp_sub_movie.mp4")
        job["settings"]["subtitles_mode"] = "Nur externe .srt-Datei erzeugen"
        with patch.object(win, "_start_current_ffmpeg_job"):
            win._finish_subtitle_pipeline(job, SRT)
        subtitle = Path(job["settings"]["subtitles_file_path"])
        win._on_worker_finished(True, "done")
        self.assertTrue(subtitle.exists(), "User-facing subtitle was deleted as a temp file")
        self.assertEqual(subtitle.read_text(), SRT)

    def test_owned_temporary_subtitle_is_removed_after_encode(self):
        win, job = self.window()
        with patch.object(win, "_start_current_ffmpeg_job"):
            win._finish_subtitle_pipeline(job, SRT)
        subtitle = Path(job["settings"]["temp_srt_path"])
        self.assertTrue(subtitle.exists())
        win._on_worker_finished(True, "done")
        self.assertFalse(subtitle.exists())


if __name__ == "__main__":
    unittest.main()
