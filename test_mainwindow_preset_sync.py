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


if __name__ == "__main__":
    unittest.main()
