import os
import sys
import unittest

from PyQt6.QtWidgets import QApplication

from mainwindow import MainWindow


class MainWindowPresetSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_crf_preset_updates_visible_detail_controls(self):
        window = MainWindow()
        try:
            input_file = os.path.abspath("test_input.mp4")
            window._add_file_to_queue(input_file)
            self.app.processEvents()

            window.combo_preset.setCurrentText("Schnell 1080p30 (MP4 H.264)")
            self.app.processEvents()

            job = window.jobs[window.queue_table.currentRow()]
            self.assertEqual(window.combo_preset.currentText(), "Schnell 1080p30 (MP4 H.264)")
            self.assertEqual(window.combo_encoding.currentText(), "CRF (Qualitätsbasiert)")
            self.assertEqual(window.lbl_bitrate_val.text(), "Qualitätsfaktor (CRF):")
            self.assertEqual(window.spin_bitrate_val.value(), 22.0)
            self.assertEqual(job["settings"]["encoding_mode"], "crf")
            self.assertEqual(job["settings"]["crf"], "22")
        finally:
            window.close()

    def test_h265_crf_preset_does_not_get_overwritten(self):
        # Regression: bei libx265-Presets hob _sync_video_codec_combobox die
        # Signalsperre auf, wodurch combo_vcodec.setCurrentText mitten im Laden
        # ein vorzeitiges _save_ui_settings_to_job mit Default-Werten (VBR 8M)
        # auslöste und das CRF des Presets überschrieb.
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()

            window.combo_preset.setCurrentText("H.265 MKV 1080p30")
            self.app.processEvents()

            job = window.jobs[window.queue_table.currentRow()]
            self.assertEqual(window.combo_encoding.currentText(), "CRF (Qualitätsbasiert)")
            self.assertEqual(window.lbl_bitrate_val.text(), "Qualitätsfaktor (CRF):")
            self.assertEqual(window.spin_bitrate_val.value(), 22.0)
            # Job-Settings dürfen nicht auf VBR 8M zurückfallen
            self.assertEqual(job["settings"]["crf"], "22")
            self.assertEqual(job["settings"].get("video_bitrate", ""), "")
            self.assertNotEqual(job["settings"].get("encoding_mode"), "vbr")
        finally:
            window.close()

    def test_quick_video_preset_from_audio_only_restores_video_settings(self):
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()

            window.combo_format.setCurrentText("MP3 (Nur Audio)")
            self.app.processEvents()
            self.assertEqual(window.jobs[0]["settings"]["container"], "mp3")
            self.assertEqual(window.jobs[0]["settings"]["video_codec"], "none")

            window.combo_preset.setCurrentText("YouTube 1080p HD")
            self.app.processEvents()

            settings = window.jobs[0]["settings"]
            self.assertEqual(settings["container"], "mp4")
            self.assertEqual(settings["video_codec"], "libx264")
            self.assertEqual(settings["audio_codec"], "aac")
            self.assertEqual(settings["video_bitrate"], "16M")
            self.assertEqual(settings["fps"], "30")
            self.assertTrue(window.chk_export_video.isChecked())
            self.assertTrue(window.jobs[0]["output_file"].endswith(".mp4"))
        finally:
            window.close()

    def test_quick_hocheffizient_selects_h265_crf(self):
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()

            window.combo_preset.setCurrentText("Hocheffizient (CRF 23)")
            self.app.processEvents()

            settings = window.jobs[0]["settings"]
            self.assertEqual(settings["video_codec"], "libx265")
            self.assertEqual(settings["encoding_mode"], "crf")
            self.assertEqual(settings["crf"], "23")
            self.assertEqual(window.combo_vcodec.currentText(), "libx265")
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
