"""FFmpegWorker: Argumentaufbau, stderr-Zeilenlogik und echter Lauf."""

import os
import shutil
import sys
import tempfile
import unittest

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from ffmpeg_worker import FFmpegWorker


class _FakeData:
    def __init__(self, text):
        self._text = text

    def data(self):
        return self._text.encode("utf-8")


class _FakeProcess:
    def __init__(self, stderr=""):
        self._stderr = stderr

    def readAllStandardError(self):
        text, self._stderr = self._stderr, ""
        return _FakeData(text)

    def readAllStandardOutput(self):
        return _FakeData("")


class FFmpegWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.abspath("test_input.mp4")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, args, output):
        worker = FFmpegWorker(self.src, output, args)
        logs, result = [], {}
        loop = QEventLoop()
        worker.log_received.connect(logs.append)

        def done(ok, msg):
            result.update(ok=ok, msg=msg)
            loop.quit()

        worker.finished.connect(done)
        QTimer.singleShot(60000, loop.quit)
        worker.start()
        if "ok" not in result:
            loop.exec()
        return worker, logs, result

    def test_progress_args_are_global_and_inputs_stay_together(self):
        out = os.path.join(self.tmp, "o.mp4")
        srt = os.path.join(self.tmp, "s.srt")
        with open(srt, "w", encoding="utf-8") as fh:
            fh.write("1\n00:00:00,000 --> 00:00:01,000\nHallo\n")
        args = ["-y", "-i", self.src, "-i", srt, "-map", "0:v", "-map", "1:s", "-c:v", "libx264",
                "-c:s", "mov_text", out]
        worker, _, result = self._run(args, out)
        self.assertTrue(result["ok"], result)
        sent = worker.process.arguments()
        self.assertEqual(sent[:4], ["-y", "-progress", "-", "-nostats"])
        i = sent.index("-i")
        self.assertEqual(sent[i:i + 4], ["-i", self.src, "-i", srt])  # Multi-Input nicht getrennt
        self.assertTrue(os.path.exists(out))
        self.assertEqual(
            [n for n in os.listdir(self.tmp) if n.startswith(".lme_tmp_")], []
        )

    def test_args_without_leading_y_get_progress_in_front(self):
        out = os.path.join(self.tmp, "o.mp4")
        worker, _, result = self._run(["-i", self.src, "-c:v", "libx264", "-y", out], out)
        self.assertTrue(result["ok"], result)
        self.assertEqual(worker.process.arguments()[:3], ["-progress", "-", "-nostats"])

    def test_missing_bluray_source_is_reported_with_original_name(self):
        worker = FFmpegWorker("bluray:/does/not/exist", "/tmp/x.mkv", ["-y", "/tmp/x.mkv"])
        result = []
        worker.finished.connect(lambda ok, msg: result.append((ok, msg)))
        worker.start()
        self.assertFalse(result[0][0])
        self.assertIn("bluray:/does/not/exist", result[0][1])

    def test_bluray_prefix_is_stripped_for_existence_check(self):
        # Existierendes Verzeichnis mit Präfix darf nicht an der Vorprüfung scheitern
        # (ffmpeg selbst scheitert dann an der Nicht-Disc, aber erst NACH dem Start).
        worker = FFmpegWorker(f"bluray:{self.tmp}", os.path.join(self.tmp, "x.mkv"),
                              ["-y", "-i", f"bluray:{self.tmp}", os.path.join(self.tmp, "x.mkv")])
        result = []
        worker.finished.connect(lambda ok, msg: result.append((ok, msg)))
        worker.start()
        loop = QEventLoop()
        QTimer.singleShot(5000, loop.quit)
        worker.finished.connect(lambda *_: loop.quit())
        if not result:
            loop.exec()
        self.assertTrue(result)
        self.assertNotIn("existiert nicht", result[0][1])

    def test_stderr_status_lines_split_on_carriage_return(self):
        worker = FFmpegWorker(self.src, os.path.join(self.tmp, "o.mp4"), [])
        worker.process = _FakeProcess("frame=1 fps=0\rframe=2 fps=9\rError: kaputt\nrest")
        logs = []
        worker.log_received.connect(logs.append)
        worker._handle_stderr()
        self.assertEqual(logs, ["frame=1 fps=0", "frame=2 fps=9", "Error: kaputt"])
        self.assertEqual(worker.stderr_buffer, "rest")

    def test_unterminated_last_stderr_line_is_flushed_on_finish(self):
        worker = FFmpegWorker(self.src, os.path.join(self.tmp, "o.mp4"), [])
        worker.process = _FakeProcess("Conversion failed!")
        logs, result = [], []
        worker.log_received.connect(logs.append)
        worker.finished.connect(lambda ok, msg: result.append(ok))
        from PyQt6.QtCore import QProcess
        worker._handle_finished(1, QProcess.ExitStatus.NormalExit)
        self.assertIn("Conversion failed!", logs)
        self.assertEqual(result, [False])

    def test_no_giant_stats_line_in_log_of_real_run(self):
        out = os.path.join(self.tmp, "o.mp4")
        _, logs, result = self._run(["-y", "-i", self.src, "-c:v", "libx264", out], out)
        self.assertTrue(result["ok"], result)
        self.assertFalse([l for l in logs if l.count("frame=") > 1], logs)


if __name__ == "__main__":
    unittest.main()
