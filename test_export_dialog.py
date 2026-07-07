import os
import sys
import time
import unittest

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


if __name__ == "__main__":
    unittest.main()
