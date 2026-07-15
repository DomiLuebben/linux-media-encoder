import os
import sys
import time
import unittest

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QApplication

import presets
from export_settings_dialog import ExportSettingsDialog


class ExportDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def _make_dialog(self):
        input_file = os.path.abspath("test_input.mp4")
        output_file = os.path.abspath("test_output.mp4")
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        return ExportSettingsDialog(input_file, output_file, settings)

    def _wait_for_probe(self, dialog, timeout=3.0):
        """ffprobe läuft jetzt asynchron — auf die Quell-Metadaten warten."""
        deadline = time.monotonic() + timeout
        while not dialog.source_info.get("width") and time.monotonic() < deadline:
            time.sleep(0.02)
            self.app.processEvents()

    def test_fit_mode_links_width_and_height_to_source_aspect(self):
        # Quelle test_input.mp4 ist 640x360 (16:9)
        dialog = self._make_dialog()
        try:
            self._wait_for_probe(dialog)
            dialog.combo_scale_mode.setCurrentText("Seitenverhältnis beibehalten")
            dialog.spin_width.setValue(320)
            self.assertEqual(dialog.spin_height.value(), 180)
            dialog.spin_height.setValue(90)
            self.assertEqual(dialog.spin_width.value(), 160)
        finally:
            dialog.reject()

    def test_stretch_mode_keeps_width_and_height_independent(self):
        dialog = self._make_dialog()
        try:
            dialog.combo_scale_mode.setCurrentText("Verzerren (exakte Größe)")
            dialog.spin_width.setValue(320)
            dialog.spin_height.setValue(999)
            self.assertEqual(dialog.spin_width.value(), 320)
            self.assertEqual(dialog.spin_height.value(), 999)
        finally:
            dialog.reject()

    def test_unchecked_video_export_yields_none_codec(self):
        # Regression: get_results las den Codec aus der ComboBox und ignorierte
        # die abgewaehlte "Video exportieren"-Checkbox komplett.
        dialog = self._make_dialog()
        try:
            dialog.chk_export_video.setChecked(False)
            _, settings = dialog.get_results()
            self.assertEqual(settings["video_codec"], "none")
            self.assertEqual(settings["encoding_mode"], "none")
        finally:
            dialog.reject()

    def test_unchecked_audio_export_yields_none_codec(self):
        dialog = self._make_dialog()
        try:
            dialog.chk_export_audio.setChecked(False)
            _, settings = dialog.get_results()
            self.assertEqual(settings["audio_codec"], "none")
            # Video bleibt unangetastet
            self.assertEqual(settings["video_codec"], "libx264")
        finally:
            dialog.reject()

    def test_format_switch_from_audio_only_reenables_video_checkbox(self):
        # Regression: Nach MP3 -> H.264 blieb die Video-Checkbox abgewaehlt,
        # obwohl der Export wieder Video enthielt.
        dialog = self._make_dialog()
        try:
            dialog.combo_format.setCurrentText("MP3 (Nur Audio)")
            self.app.processEvents()
            self.assertFalse(dialog.chk_export_video.isChecked())

            dialog.combo_format.setCurrentText("H.264 (MP4)")
            self.app.processEvents()
            self.assertTrue(dialog.chk_export_video.isChecked())
            _, settings = dialog.get_results()
            self.assertEqual(settings["video_codec"], "libx264")
        finally:
            dialog.reject()

    def test_quick_video_preset_from_audio_only_restores_video_settings(self):
        dialog = self._make_dialog()
        try:
            dialog.combo_format.setCurrentText("MP3 (Nur Audio)")
            self.app.processEvents()
            self.assertFalse(dialog.chk_export_video.isChecked())

            dialog.combo_preset.setCurrentText("YouTube 1080p HD")
            self.app.processEvents()

            output_file, settings = dialog.get_results()
            self.assertEqual(settings["container"], "mp4")
            self.assertEqual(settings["video_codec"], "libx264")
            self.assertEqual(settings["audio_codec"], "aac")
            self.assertEqual(settings["video_bitrate"], "16M")
            self.assertEqual(settings["fps"], "30")
            self.assertTrue(dialog.chk_export_video.isChecked())
            self.assertTrue(output_file.endswith(".mp4"))
        finally:
            dialog.reject()

    def test_webm_audio_toggle_restores_container_compatible_codec(self):
        settings = dict(presets.PRESETS["WebM (VP9 / Opus) - Web-optimiert"])
        dialog = ExportSettingsDialog(
            os.path.abspath("test_input.mp4"),
            os.path.abspath("test_output.webm"),
            settings,
        )
        try:
            self.assertEqual(dialog.combo_audiocodec.currentText(), "Opus")
            dialog.chk_export_audio.setChecked(False)
            self.app.processEvents()
            dialog.chk_export_audio.setChecked(True)
            self.app.processEvents()

            _, settings = dialog.get_results()
            self.assertEqual(settings["container"], "webm")
            self.assertEqual(settings["audio_codec"], "libopus")
            self.assertEqual(dialog.combo_audiocodec.currentText(), "Opus")
        finally:
            dialog.reject()

    def test_low_bitrate_roundtrips_without_ui_clamping(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings.update({
            "encoding_mode": "vbr",
            "crf": "",
            "video_bitrate": "33k",
            "audio_bitrate": "22k",
        })
        dialog = ExportSettingsDialog(
            os.path.abspath("test_input.mp4"),
            os.path.abspath("test_output.mp4"),
            settings,
        )
        try:
            self.assertAlmostEqual(dialog.spin_bitrate_val.value(), 0.033, places=3)
            self.assertEqual(dialog.spin_bitrate_val.decimals(), 3)

            _, result = dialog.get_results()
            self.assertEqual(result["video_bitrate"], "33k")
            self.assertEqual(result["audio_bitrate"], "22k")
            args = presets.get_ffmpeg_args(dialog.input_file, dialog.output_file, result)
            self.assertEqual(args[args.index("-b:v") + 1], "33k")
            self.assertEqual(args[args.index("-b:a") + 1], "22k")
        finally:
            dialog.reject()

    def test_retained_preview_process_is_released_after_finished_signal(self):
        dialog = self._make_dialog()
        proc = QProcess(dialog)
        try:
            dialog._retain_preview_process(proc)
            self.assertIn(proc, dialog._retained_procs)

            proc.start(sys.executable, ["-c", "pass"])
            self.assertTrue(proc.waitForFinished(2000))
            self.app.processEvents()

            self.assertNotIn(proc, dialog._retained_procs)
        finally:
            dialog.reject()


class PresetLabelTest(unittest.TestCase):
    def test_format_labels(self):
        self.assertEqual(presets.format_label({"container": "mp4", "video_codec": "libx264"}), "H.264")
        self.assertEqual(presets.format_label({"container": "mp4", "video_codec": "libx265"}), "HEVC")
        self.assertEqual(presets.format_label({"container": "webm", "video_codec": "libsvtav1"}), "AV1")
        self.assertEqual(presets.format_label({"container": "mkv", "video_codec": "copy"}), "MKV")
        self.assertEqual(
            presets.format_label({"container": "mp3", "video_codec": "none", "audio_codec": "libmp3lame"}),
            "MP3",
        )

    def test_preset_label_detects_known_preset_and_custom(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        self.assertEqual(presets.preset_label(settings), "MP4 (H.264 / AAC) - Standard 1080p")
        settings["custom_mode"] = True
        self.assertEqual(presets.preset_label(settings), "Benutzerdefiniert")


class TrimAndPresetsTest(unittest.TestCase):
    def test_timecode_formatting(self):
        # Format seconds as HH:MM:SS.mmm
        self.assertEqual(ExportSettingsDialog._format_timecode(0), "00:00:00.000")
        self.assertEqual(ExportSettingsDialog._format_timecode(65.5), "00:01:05.500")
        self.assertEqual(ExportSettingsDialog._format_timecode(3600.005), "01:00:00.005")
        self.assertEqual(ExportSettingsDialog._format_timecode(59.9999), "00:01:00.000")

    def test_timecode_parsing(self):
        # Parse different formats into seconds
        self.assertEqual(ExportSettingsDialog._parse_timecode("00:01:05.500"), 65.5)
        self.assertEqual(ExportSettingsDialog._parse_timecode("01:05.5"), 65.5)
        self.assertEqual(ExportSettingsDialog._parse_timecode("65.5"), 65.5)
        self.assertEqual(ExportSettingsDialog._parse_timecode("  00:00:10   "), 10.0)
        self.assertIsNone(ExportSettingsDialog._parse_timecode("invalid"))
        self.assertIsNone(ExportSettingsDialog._parse_timecode(""))
        # Negative Komponenten und zu viele Doppelpunkte sind ungültig
        self.assertIsNone(ExportSettingsDialog._parse_timecode("-5"))
        self.assertIsNone(ExportSettingsDialog._parse_timecode("5:-30"))
        self.assertIsNone(ExportSettingsDialog._parse_timecode("1:2:3:4"))

    def test_ffmpeg_args_copy_seeking(self):
        # Lossless copy cut: should place -ss and -t before -i
        settings = {
            "container": "mkv",
            "video_codec": "copy",
            "audio_codec": "copy",
            "trim_start": "5.0",
            "trim_end": "12.5"
        }
        args = presets.get_ffmpeg_args("input.mp4", "output.mkv", settings)
        
        # Verify sequence: ss and t should appear before -i
        idx_ss = args.index("-ss")
        idx_t = args.index("-t")
        idx_i = args.index("-i")
        
        self.assertTrue(idx_ss < idx_i)
        self.assertTrue(idx_t < idx_i)
        self.assertEqual(args[idx_ss + 1], "5.000")
        self.assertEqual(args[idx_t + 1], "7.500")
        # Verschobene Timestamps beim Copy-Cut normalisieren
        self.assertIn("-avoid_negative_ts", args)
        self.assertGreater(args.index("-avoid_negative_ts"), idx_i)

        # Re-encoding: -ss and -to should appear after -i
        settings_enc = {
            "container": "mp4",
            "video_codec": "libx264",
            "audio_codec": "aac",
            "trim_start": "5.0",
            "trim_end": "12.5"
        }
        args_enc = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings_enc)
        idx_ss_enc = args_enc.index("-ss")
        idx_to_enc = args_enc.index("-to")
        idx_i_enc = args_enc.index("-i")

        self.assertTrue(idx_i_enc < idx_ss_enc)
        self.assertTrue(idx_i_enc < idx_to_enc)
        self.assertNotIn("-avoid_negative_ts", args_enc)

    def test_video_copy_with_audio_encode_uses_input_seeking(self):
        # Output-Seeking mit -c:v copy würde mitten in die GOP schneiden
        # (Bildfehler bis zum nächsten Keyframe) — auch bei Audio-Re-Encode
        # oder ohne Audio muss deshalb Input-Seeking verwendet werden.
        for audio in ("aac", "none"):
            settings = {
                "container": "mp4",
                "video_codec": "copy",
                "audio_codec": audio,
                "trim_start": "5.0",
                "trim_end": "12.5",
            }
            args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
            self.assertLess(args.index("-ss"), args.index("-i"), f"audio={audio}")
            self.assertIn("-t", args, f"audio={audio}")
            self.assertNotIn("-to", args, f"audio={audio}")

    def test_audio_only_copy_uses_input_seeking(self):
        settings = {
            "container": "mkv",
            "video_codec": "none",
            "audio_codec": "copy",
            "trim_start": "3.0",
        }
        args = presets.get_ffmpeg_args("input.mp4", "output.mkv", settings)
        self.assertLess(args.index("-ss"), args.index("-i"))

    def test_trim_label(self):
        self.assertEqual(presets.trim_label({}), "")
        self.assertEqual(presets.trim_label({"trim_start": 5, "trim_end": 90}), "0:05–1:30")
        self.assertEqual(presets.trim_label({"trim_start": 5}), "0:05–Ende")
        self.assertEqual(presets.trim_label({"trim_end": 3700}), "0:00–1:01:40")
        # Ende vor Start wird von get_ffmpeg_args verworfen -> nur Start anzeigen
        self.assertEqual(presets.trim_label({"trim_start": 60, "trim_end": 10}), "1:00–Ende")
        self.assertEqual(presets.trim_label({"trim_start": 0, "trim_end": 0}), "")

    def test_bitrate_and_size_helpers(self):
        self.assertEqual(ExportSettingsDialog._bitrate_to_bps("8M"), 8e6)
        self.assertEqual(ExportSettingsDialog._bitrate_to_bps("192k"), 192e3)
        self.assertEqual(ExportSettingsDialog._bitrate_to_bps("800000"), 800000.0)
        self.assertIsNone(ExportSettingsDialog._bitrate_to_bps("Source / CRF"))
        self.assertIsNone(ExportSettingsDialog._bitrate_to_bps(""))
        self.assertEqual(ExportSettingsDialog._format_size(2_500_000), "2.5 MB")
        self.assertEqual(ExportSettingsDialog._format_size(1_250_000_000), "1.25 GB")
        self.assertEqual(ExportSettingsDialog._format_size(50_000), "50 kB")

    def test_copy_without_trim_has_no_seek_args(self):
        settings = {
            "container": "mkv",
            "video_codec": "copy",
            "audio_codec": "copy",
        }
        args = presets.get_ffmpeg_args("input.mp4", "output.mkv", settings)
        self.assertNotIn("-ss", args)
        self.assertNotIn("-t", args)
        self.assertNotIn("-avoid_negative_ts", args)


if __name__ == "__main__":
    unittest.main()
