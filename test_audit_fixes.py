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


class RipAudit20260826Test(unittest.TestCase):
    """Regressionstests zu den drei Befunden des Gesamtaudits vom 26.08.2026."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    # --- Befund 1: 'Alle Spuren' (Index -1) ---

    def test_dvd_rip_args_all_streams_maps_optional_not_negative_index(self):
        from optical_media import build_dvd_rip_args

        args, out = build_dvd_rip_args(
            source_path="/dev/sr0", title_num=1,
            audio_stream_idx=-1, subtitle_stream_idx=-1,
            output_file="/tmp/film.mkv", remux_mkv=True,
        )
        self.assertIn("0:a?", args)   # alle Tonspuren, optional
        self.assertIn("0:s?", args)   # alle Untertitel, optional
        self.assertNotIn("0:a:-1", args)
        self.assertNotIn("0:s:-1", args)
        self.assertTrue(out.endswith(".mkv"))

    def test_bluray_rip_args_all_streams_maps_optional_not_negative_index(self):
        from optical_media import build_bluray_rip_args

        args, out = build_bluray_rip_args(
            source_path="/dev/sr0", playlist_num=5,
            audio_stream_idx=-1, subtitle_stream_idx=-1,
            output_file="/tmp/film.mkv", remux_mkv=True,
        )
        self.assertIn("0:a?", args)
        self.assertIn("0:s?", args)
        self.assertNotIn("0:a:-1", args)
        self.assertNotIn("0:s:-1", args)

    def test_rip_args_still_map_explicit_stream_index(self):
        from optical_media import build_bluray_rip_args

        args, _ = build_bluray_rip_args(
            source_path="/media/bd", playlist_num=1,
            audio_stream_idx=2, subtitle_stream_idx=0,
            output_file="/tmp/film.mkv",
        )
        self.assertIn("0:a:2", args)
        self.assertIn("0:s:0", args)

    # --- Befund 2: Audio-CD-Formatauswahl vollständig ---

    def test_codec_key_helper_covers_every_combobox_entry(self):
        from optical_media import audio_codec_key_from_label

        cases = {
            "FLAC (Verlustfrei)": "flac",
            "WAV (Unkomprimiert)": "wav",
            "MP3 (320 kbps)": "mp3",
            "AAC (256 kbps)": "aac",     # früher: still WAV im Queue-Zweig
            "Opus (160 kbps)": "opus",   # früher: WAV im Queue-Zweig
            "ALAC": "alac",              # früher: überall WAV
            "": "wav",
        }
        for label, expected in cases.items():
            self.assertEqual(audio_codec_key_from_label(label), expected, label)

    def test_audio_extension_aac_and_alac_belong_to_m4a(self):
        from optical_media import audio_file_extension

        self.assertEqual(audio_file_extension("aac"), "m4a")
        self.assertEqual(audio_file_extension("alac"), "m4a")
        self.assertEqual(audio_file_extension("flac"), "flac")
        self.assertEqual(audio_file_extension("mp3"), "mp3")
        self.assertEqual(audio_file_extension("opus"), "opus")
        self.assertEqual(audio_file_extension("wav"), "wav")

    def test_queue_job_for_aac_cd_uses_aac_and_m4a(self):
        """AAC-Auswahl darf nicht mehr als WAV-Job in die Queue landen."""
        import optical_media
        from disc_ripper_dialog import DiscRipperDialog
        sys.path.insert(0, os.path.dirname(__file__))
        from test_optical_media import LSDVD_OY_FIXTURE, parse_lsdvd_output  # noqa: F401

        mock_cd = optical_media.DiscInspectionResult(
            source_path="/dev/sr0",
            disc_type=optical_media.DiscType.AUDIO_CD,
            disc_label="Testalbum",
            total_duration_sec=300.0,
            audio_tracks=[
                optical_media.AudioTrackInfo(track_num=1, duration_sec=150.0, title="Eins"),
                optical_media.AudioTrackInfo(track_num=2, duration_sec=150.0, title="Zwei"),
            ],
        )

        with patch("optical_media.scan_optical_drives", return_value=[]), \
             patch("optical_media.inspect_source", return_value=mock_cd), \
             patch("disc_ripper_dialog.QMessageBox.information"):
            dialog = DiscRipperDialog(initial_source="/dev/sr0")
            try:
                dialog.edit_output_dir.setText("/tmp/cd_out")
                index = dialog.combo_cd_codec.findText("AAC (256 kbps)")
                self.assertGreaterEqual(index, 0)
                dialog.combo_cd_codec.setCurrentIndex(index)

                received = []
                dialog.jobs_queued.connect(lambda jobs: received.extend(jobs))
                dialog._on_action_clicked()

                self.assertEqual(len(received), 2)
                job = received[0]
                self.assertTrue(job["output_file"].endswith(".m4a"))
                settings = job["settings"]
                self.assertEqual(settings["audio_codec"], "aac")
                self.assertEqual(settings["container"], "m4a")
                self.assertEqual(settings["audio_bitrate"], "256k")
                self.assertEqual(settings["video_codec"], "none")
            finally:
                dialog.close()

    def test_direct_worker_receives_alac_codec_key(self):
        """Der Direkt-Rip-Zweig muss ALAC durchreichen statt es auf WAV zu kappen."""
        import optical_media
        from disc_ripper_dialog import DiscRipperDialog
        from disc_rip_worker import AudioCdRipWorker

        captured = {}

        class FakeWorker(AudioCdRipWorker):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                captured["codec"] = self.codec
                raise SystemExit  # nicht wirklich starten

        mock_cd = optical_media.DiscInspectionResult(
            source_path="/dev/sr0",
            disc_type=optical_media.DiscType.AUDIO_CD,
            disc_label="Testalbum",
            total_duration_sec=150.0,
            audio_tracks=[optical_media.AudioTrackInfo(track_num=1, duration_sec=150.0, title="Eins")],
        )

        with patch("optical_media.scan_optical_drives", return_value=[]), \
             patch("optical_media.inspect_source", return_value=mock_cd), \
             patch.object(DiscRipperDialog, "_start_iso_dump"):
            dialog = DiscRipperDialog(initial_source="/dev/sr0")
            try:
                index = dialog.combo_cd_codec.findText("ALAC")
                self.assertGreaterEqual(index, 0)
                dialog.combo_cd_codec.setCurrentIndex(index)
                dialog.radio_mode_direct.setChecked(True)
                dialog.edit_output_dir.setText("/tmp/cd_out")

                with patch("disc_ripper_dialog.AudioCdRipWorker", FakeWorker):
                    with self.assertRaises(SystemExit):
                        dialog._start_direct_rip([0], "/tmp/cd_out")

                self.assertEqual(captured["codec"], "alac")
            finally:
                dialog.close()

    def test_encode_args_support_alac_and_aac(self):
        from optical_media import build_audio_encode_args, AudioTrackInfo

        track = AudioTrackInfo(track_num=7, duration_sec=100.0, title="T", artist="A", album="B")
        args_alac = build_audio_encode_args("in.wav", "out.m4a", codec="alac", track_info=track)
        self.assertEqual(args_alac[args_alac.index("-c:a") + 1], "alac")

        args_aac = build_audio_encode_args("in.wav", "out.m4a", codec="aac", bitrate="256k", track_info=track)
        self.assertEqual(args_aac[args_aac.index("-c:a") + 1], "aac")
        self.assertEqual(args_aac[args_aac.index("-b:a") + 1], "256k")

    # --- Befund 3: ignore_errors in Stufe 1 des zweistufigen Rips ---

    def test_two_stage_disc_stage_passes_ignore_errors_false_to_builder(self):
        """Bei abgewählter Fehlertoleranz darf Stufe 1 keine tolerant-Flags bauen."""
        import mainwindow
        from mainwindow import MainWindow
        import optical_media

        job = {
            "input_file": "/dev/sr0",
            "output_dir": "/tmp/out",
            "output_file": "/tmp/out/film.mp4",
            "settings": {
                "disc_type": "bluray",
                "two_stage": True,
                "ignore_errors": False,
                "title_num": 1,
                "source_duration": 600.0,
            },
            "status": "Bereit",
            "progress": 0.0,
        }
        captured = {}

        def fake_builder(source_path, playlist_num, **kwargs):
            captured.update(kwargs)
            return ["-y"], "/tmp/staged.mkv"

        win = MainWindow.__new__(MainWindow)  # ohne komplette UI-Initialisierung
        win.jobs = [job]
        win.current_job_idx = 0
        win.console = type("C", (), {"append": lambda self, text: None})()
        win.settings_store = type("S", (), {"value": staticmethod(lambda *_a, **_k: "")})()
        win.active_worker = None
        win.is_running = True
        win.tr = lambda text, **kw: text
        win._update_table_row = lambda idx: None
        win._phase_status = lambda job, text: text

        builder_name = "build_bluray_rip_args"
        with patch.object(optical_media, builder_name, side_effect=fake_builder), \
             patch("mainwindow.FFmpegWorker") as fake_worker:
            fake_worker.return_value.start = lambda: None
            win._run_disc_rip_stage(job)

        self.assertFalse(captured.get("ignore_errors", True),
                         "Stufe 1 muss die abgewählte Fehlertoleranz übernehmen")

    # --- Zusätzliche Nachprüfungen: Bitraten, cdparanoia-Fehlerbehandlung & Audio-CD Lifecycle ---

    def test_audio_bitrate_helper_matches_all_combobox_entries(self):
        from optical_media import audio_bitrate_from_label

        cases = {
            "MP3 (320 kbps)": "320k",
            "AAC (256 kbps)": "256k",
            "Opus (160 kbps)": "160k",
            "FLAC (Verlustfrei)": "",
            "WAV (Unkomprimiert)": "",
            "ALAC": "",
            "mp3": "320k",
            "aac": "256k",
            "opus": "160k",
            "flac": "",
            "alac": "",
        }
        for label, expected in cases.items():
            self.assertEqual(audio_bitrate_from_label(label), expected, label)

    def test_direct_rip_passes_correct_bitrate_for_aac_and_opus(self):
        """Direkt-Rip darf AAC nicht mehr auf 320k überschreiben, sondern muss 256k/160k nutzen."""
        import optical_media
        from disc_ripper_dialog import DiscRipperDialog
        from disc_rip_worker import AudioCdRipWorker

        captured = {}

        class FakeWorker(AudioCdRipWorker):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                captured["codec"] = self.codec
                captured["bitrate"] = self.bitrate
                raise SystemExit

        mock_cd = optical_media.DiscInspectionResult(
            source_path="/dev/sr0",
            disc_type=optical_media.DiscType.AUDIO_CD,
            disc_label="Testalbum",
            total_duration_sec=150.0,
            audio_tracks=[optical_media.AudioTrackInfo(track_num=1, duration_sec=150.0, title="Eins")],
        )

        with patch("optical_media.scan_optical_drives", return_value=[]), \
             patch("optical_media.inspect_source", return_value=mock_cd):
            dialog = DiscRipperDialog(initial_source="/dev/sr0")
            try:
                dialog.radio_mode_direct.setChecked(True)
                dialog.edit_output_dir.setText("/tmp/cd_out")

                # Test AAC (256 kbps)
                idx_aac = dialog.combo_cd_codec.findText("AAC (256 kbps)")
                self.assertGreaterEqual(idx_aac, 0)
                dialog.combo_cd_codec.setCurrentIndex(idx_aac)

                with patch("disc_ripper_dialog.AudioCdRipWorker", FakeWorker):
                    with self.assertRaises(SystemExit):
                        dialog._start_direct_rip([0], "/tmp/cd_out")
                self.assertEqual(captured["codec"], "aac")
                self.assertEqual(captured["bitrate"], "256k")

                # Test Opus (160 kbps)
                idx_opus = dialog.combo_cd_codec.findText("Opus (160 kbps)")
                self.assertGreaterEqual(idx_opus, 0)
                dialog.combo_cd_codec.setCurrentIndex(idx_opus)

                with patch("disc_ripper_dialog.AudioCdRipWorker", FakeWorker):
                    with self.assertRaises(SystemExit):
                        dialog._start_direct_rip([0], "/tmp/cd_out")
                self.assertEqual(captured["codec"], "opus")
                self.assertEqual(captured["bitrate"], "160k")
            finally:
                dialog.close()

    def test_audio_cd_extract_failed_to_start_fails_gracefully(self):
        """Wenn cdparanoia nicht gestartet werden kann, darf die Warteschlange nicht hängenbleiben."""
        from PyQt6.QtCore import QProcess
        from mainwindow import MainWindow

        job = {
            "input_file": "/dev/sr0",
            "output_dir": "/tmp/out",
            "output_file": "/tmp/out/01 - Test.flac",
            "settings": {
                "disc_type": "audio_cd",
                "track_num": 1,
                "audio_codec": "flac",
                "_extracted_wav": "/tmp/nonexistent_temp.wav",
            },
            "status": "Bereit",
            "progress": 0.0,
        }

        win = MainWindow.__new__(MainWindow)
        win.jobs = [job]
        win.current_job_idx = 0
        win.is_running = True
        win.console = type("C", (), {"append": lambda self, text: None})()
        win._run_done = 0
        win._update_table_row = lambda idx: None
        win._process_next_job = lambda: None
        win.tr = lambda text, **kw: text

        # Fehler beim Starten simulieren
        win._on_audio_cd_extract_error(QProcess.ProcessError.FailedToStart)

        self.assertEqual(job["status"], "Fehlgeschlagen")
        self.assertIn("cdparanoia", job.get("error_tail", ""))

    def test_audio_cd_queue_full_pipeline_extract_encode_cleanup(self):
        """End-to-End-Test: CDDA-Extraktion -> FFmpeg-Encoding -> Aufräumen der Zwischendatei."""
        import tempfile
        from mainwindow import MainWindow

        # Erstelle echte Dummy-WAV-Datei (> 44 Bytes)
        fd, temp_wav = tempfile.mkstemp(prefix="test_cdda_", suffix=".wav")
        os.write(fd, b"RIFF" + b"\x00" * 100)
        os.close(fd)

        job = {
            "input_file": "/dev/sr0",
            "output_dir": "/tmp/out",
            "output_file": "/tmp/out/01 - Track.m4a",
            "settings": {
                "disc_type": "audio_cd",
                "track_num": 1,
                "track_title": "Track Title",
                "track_artist": "Artist",
                "track_album": "Album",
                "audio_codec": "aac",
                "audio_bitrate": "256k",
                "_extracted_wav": temp_wav,
            },
            "status": "Bereit",
            "progress": 0.0,
        }

        win = MainWindow.__new__(MainWindow)
        win.jobs = [job]
        win.current_job_idx = 0
        win.is_running = True
        win.console = type("C", (), {"append": lambda self, text: None})()
        win._update_table_row = lambda idx: None
        win._on_job_selection_changed = lambda: None
        win.tr = lambda text, **kw: text

        captured_ffmpeg_args = []

        class FakeFFmpegWorker:
            def __init__(self, input_file, output_file, args, *a, **kw):
                captured_ffmpeg_args.extend(args)
                self.progress_updated = type("S", (), {"connect": lambda self, fn: None})()
                self.status_changed = type("S", (), {"connect": lambda self, fn: None})()
                self.log_received = type("S", (), {"connect": lambda self, fn: None})()
                self.finished = type("S", (), {"connect": lambda self, fn: None})()

            def start(self):
                pass

        with patch("mainwindow.FFmpegWorker", FakeFFmpegWorker):
            win._start_current_ffmpeg_job(job)

        # Prüfe, dass FFmpegWorker mit den Metadaten und dem temporären WAV aufgerufen wurde
        self.assertIn("-i", captured_ffmpeg_args)
        self.assertIn(temp_wav, captured_ffmpeg_args)
        self.assertIn("aac", captured_ffmpeg_args)
        self.assertIn("256k", captured_ffmpeg_args)
        self.assertIn("title=Track Title", captured_ffmpeg_args)

        # Simuliere Abschluss des Workers -> Zwischendatei muss gelöscht werden
        self.assertTrue(os.path.exists(temp_wav))
        win._cleanup_staged_source(job)
        self.assertFalse(os.path.exists(temp_wav), "Temporäre WAV-Datei muss aufgeräumt werden")

    def test_audio_cd_rip_worker_failed_to_start(self):
        """AudioCdRipWorker muss FailedToStart abfangen und finished(False) emittieren."""
        from PyQt6.QtCore import QProcess
        from disc_rip_worker import AudioCdRipWorker
        import optical_media

        worker = AudioCdRipWorker(
            device_path="/dev/sr0",
            tracks=[optical_media.AudioTrackInfo(track_num=1, duration_sec=60.0)],
            output_dir="/tmp/out",
            codec="aac",
        )
        worker._current_step = "extract"

        emitted = []
        worker.finished.connect(lambda ok, msg: emitted.append((ok, msg)))
        worker._handle_process_error(QProcess.ProcessError.FailedToStart)

        self.assertEqual(len(emitted), 1)
        self.assertFalse(emitted[0][0])
        self.assertIn("cdparanoia", emitted[0][1])

    def test_iso_dump_worker_failed_to_start(self):
        """IsoDumpWorker muss FailedToStart abfangen und finished(False) emittieren."""
        from PyQt6.QtCore import QProcess
        from disc_rip_worker import IsoDumpWorker

        worker = IsoDumpWorker(
            device_path="/dev/sr0",
            output_iso_path="/tmp/out.iso",
        )

        emitted = []
        worker.finished.connect(lambda ok, msg: emitted.append((ok, msg)))
        worker._handle_process_error(QProcess.ProcessError.FailedToStart)

        self.assertEqual(len(emitted), 1)
        self.assertFalse(emitted[0][0])
        self.assertIn("dd", emitted[0][1])

if __name__ == "__main__":
    unittest.main()

