import os
import sys
import time
import unittest

import presets


def wait_for_source_probe(app, job, timeout=3.0):
    """Wartet auf den asynchronen ffprobe-Prefetch eines Jobs (Daemon-Thread)."""
    deadline = time.monotonic() + timeout
    while "source_size" not in job and time.monotonic() < deadline:
        time.sleep(0.02)
        app.processEvents()


class ImageArgsTest(unittest.TestCase):
    def _args(self, container, **extra):
        settings = {"container": container, "audio_codec": "none", "match_source": True}
        settings.update(extra)
        return presets.get_ffmpeg_args("in.png", f"out.{container}", settings)

    def test_jpeg_quality_mapping(self):
        args = self._args("jpg", video_codec="mjpeg", image_quality=90)
        self.assertIn("mjpeg", args)
        self.assertIn("-q:v", args)
        # Qualitaet 90 -> q:v 5 (2=beste, 31=schlechteste)
        self.assertEqual(args[args.index("-q:v") + 1], "5")
        self.assertIn("-frames:v", args)
        self.assertIn("-an", args)

    def test_png_lossless_has_no_quality_flag(self):
        args = self._args("png", video_codec="png", image_quality=100)
        self.assertIn("png", args)
        self.assertNotIn("-q:v", args)
        self.assertNotIn("-quality", args)

    def test_webp_quality_and_lossless(self):
        args = self._args("webp", video_codec="libwebp", image_quality=80)
        self.assertEqual(args[args.index("-quality") + 1], "80")
        self.assertNotIn("-lossless", args)
        args = self._args("webp", video_codec="libwebp", image_quality=100)
        self.assertIn("-lossless", args)

    def test_avif_constant_quality(self):
        args = self._args("avif", video_codec="libaom-av1", image_quality=70)
        self.assertIn("libaom-av1", args)
        self.assertIn("-still-picture", args)
        # Konstante Qualitaet bei libaom braucht -b:v 0
        self.assertEqual(args[args.index("-b:v") + 1], "0")
        self.assertEqual(args[args.index("-crf") + 1], "19")

    def test_match_source_skips_scaling(self):
        args = self._args("jpg", video_codec="mjpeg", image_quality=90)
        self.assertNotIn("-vf", args)

    def test_explicit_size_scales_keeps_aspect_ratio_by_default(self):
        args = self._args("jpg", video_codec="mjpeg", image_quality=90,
                          match_source=False, width=640, height=480)
        self.assertEqual(args[args.index("-vf") + 1],
                         "scale=640:480:force_original_aspect_ratio=decrease")

    def test_scale_mode_fit_keeps_aspect_ratio(self):
        args = self._args("png", video_codec="png",
                          scale_mode="fit", width=800, height=600)
        self.assertEqual(args[args.index("-vf") + 1],
                         "scale=800:600:force_original_aspect_ratio=decrease")

    def test_scale_mode_stretch_scales_exactly(self):
        args = self._args("jpg", video_codec="mjpeg", image_quality=90,
                          scale_mode="stretch", width=640, height=480)
        self.assertEqual(args[args.index("-vf") + 1], "scale=640:480")

    def test_scale_mode_source_skips_scaling(self):
        args = self._args("webp", video_codec="libwebp", image_quality=80,
                          scale_mode="source", width=640, height=480)
        self.assertNotIn("-vf", args)

    def test_crop_filter_is_applied_before_scaling(self):
        args = self._args("jpg", video_codec="mjpeg", image_quality=90,
                          scale_mode="fit", width=640, height=480,
                          crop={"x": 10, "y": 20, "w": 300, "h": 200})
        self.assertEqual(
            args[args.index("-vf") + 1],
            "crop=300:200:10:20,scale=640:480:force_original_aspect_ratio=decrease",
        )

    def test_crop_without_scaling(self):
        args = self._args("png", video_codec="png",
                          crop={"x": 0, "y": 0, "w": 100, "h": 80})
        self.assertEqual(args[args.index("-vf") + 1], "crop=100:80:0:0")

    def test_invalid_crop_is_ignored(self):
        args = self._args("png", video_codec="png",
                          crop={"x": 0, "y": 0, "w": 0, "h": 80})
        self.assertNotIn("-vf", args)
        self.assertIsNone(presets.get_crop({"crop": "kaputt"}))
        self.assertIsNone(presets.get_crop({"crop": {"x": 1}}))
        # Negative Offsets werden auf 0 geclampt
        self.assertEqual(presets.get_crop({"crop": {"x": -5, "y": 3, "w": 10, "h": 10}}),
                         {"x": 0, "y": 3, "w": 10, "h": 10})

    def test_is_image_input(self):
        self.assertTrue(presets.is_image_input("/tmp/foo.PNG"))
        self.assertTrue(presets.is_image_input("bild.heic"))
        self.assertFalse(presets.is_image_input("film.mp4"))

    def test_format_labels_for_images(self):
        self.assertEqual(presets.format_label({"container": "jpg", "video_codec": "mjpeg"}), "JPEG")
        self.assertEqual(presets.format_label({"container": "avif", "video_codec": "libaom-av1"}), "AVIF")


class ImageQueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_png_input_defaults_to_jpeg_preset_and_quality_ui(self):
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            self.app.processEvents()
            job = window.jobs[0]
            self.assertEqual(job["settings"]["container"], "jpg")
            self.assertEqual(window.combo_format.currentText(), "JPEG (Bild)")
            self.assertEqual(window.chk_export_video.text(), "Bild")
            self.assertTrue(window.chk_export_audio.isHidden())
            self.assertEqual(window.settings_tabs.tabText(0), "Bild")
            self.assertEqual(window.left_mode_stack.currentWidget(), window.image_preview_group)
            self.assertEqual(window.settings_wrapper.title(), "Bildeinstellungen")
            preview_pixmap = window.image_preview_label.pixmap()
            self.assertIsNotNone(preview_pixmap)
            self.assertFalse(preview_pixmap.isNull())
            self.assertEqual(window.lbl_bitrate_val.text(), "Qualität (%):")
            self.assertEqual(int(window.spin_bitrate_val.value()), 90)
            # Untertitel-Tab fuer Bilder gesperrt
            self.assertFalse(window.settings_tabs.isTabEnabled(2))
            # Kein Untertitel-Pipeline-Lauf fuer Bilder
            self.assertFalse(window._job_needs_subtitle_generation(job))
        finally:
            window.close()

    def test_video_input_offers_no_image_formats(self):
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()
            options = [window.combo_format.itemText(i) for i in range(window.combo_format.count())]
            self.assertNotIn("JPEG (Bild)", options)
            self.assertIn("H.264 (MP4)", options)
            self.assertEqual(window.left_mode_stack.currentWidget(), window.queue_group)
            preset_options = [window.combo_preset.itemText(i) for i in range(window.combo_preset.count())]
            self.assertNotIn("JPEG (Bild) - Hohe Qualität", preset_options)
        finally:
            window.close()

    def test_image_input_offers_only_image_formats(self):
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            self.app.processEvents()
            options = [window.combo_format.itemText(i) for i in range(window.combo_format.count())]
            self.assertEqual(options, ["JPEG (Bild)", "PNG (Bild)", "WebP (Bild)", "AVIF (Bild)"])
            preset_options = [window.combo_preset.itemText(i) for i in range(window.combo_preset.count())]
            self.assertIn("WebP (Bild) - Hohe Qualität", preset_options)
            self.assertNotIn("MP4 (H.264 / AAC) - Standard 1080p", preset_options)
        finally:
            window.close()

    def test_selection_switch_swaps_format_options(self):
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()
            window.queue_table.selectRow(1)
            self.app.processEvents()
            options = [window.combo_format.itemText(i) for i in range(window.combo_format.count())]
            self.assertIn("H.264 (MP4)", options)
            self.assertNotIn("JPEG (Bild)", options)
            self.assertEqual(window.chk_export_video.text(), "Video")
            self.assertFalse(window.chk_export_audio.isHidden())
            self.assertEqual(window.settings_tabs.tabText(0), "Video")
            self.assertEqual(window.left_mode_stack.currentWidget(), window.queue_group)
            window.queue_table.selectRow(0)
            self.app.processEvents()
            options = [window.combo_format.itemText(i) for i in range(window.combo_format.count())]
            self.assertIn("JPEG (Bild)", options)
            self.assertNotIn("H.264 (MP4)", options)
            self.assertEqual(window.chk_export_video.text(), "Bild")
            self.assertTrue(window.chk_export_audio.isHidden())
            self.assertEqual(window.settings_tabs.tabText(0), "Bild")
            self.assertEqual(window.left_mode_stack.currentWidget(), window.image_preview_group)
        finally:
            window.close()

    def test_image_preview_view_can_return_to_queue(self):
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            self.app.processEvents()
            self.assertEqual(window.left_mode_stack.currentWidget(), window.image_preview_group)
            window.btn_show_queue_from_image.click()
            self.app.processEvents()
            self.assertEqual(window.left_mode_stack.currentWidget(), window.queue_group)
        finally:
            window.close()

    def test_export_dialog_filters_formats_by_source(self):
        from export_settings_dialog import ExportSettingsDialog
        settings = dict(presets.PRESETS["JPEG (Bild) - Hohe Qualität"])
        dialog = ExportSettingsDialog(os.path.abspath("test_input.png"), "/tmp/out.jpg", settings)
        try:
            options = [dialog.combo_format.itemText(i) for i in range(dialog.combo_format.count())]
            self.assertEqual(options, ["JPEG (Bild)", "PNG (Bild)", "WebP (Bild)", "AVIF (Bild)"])
            self.assertEqual(dialog.windowTitle(), "Bildeinstellungen")
            self.assertEqual(dialog.chk_export_video.text(), "Bild exportieren")
            self.assertTrue(dialog.chk_export_audio.isHidden())
            self.assertEqual(dialog.settings_tabs.tabText(0), "Bild")
        finally:
            dialog.reject()
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        dialog = ExportSettingsDialog(os.path.abspath("test_input.mp4"), "/tmp/out.mp4", settings)
        try:
            options = [dialog.combo_format.itemText(i) for i in range(dialog.combo_format.count())]
            self.assertNotIn("JPEG (Bild)", options)
        finally:
            dialog.reject()

    def test_apply_settings_to_all_skips_other_source_type(self):
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()
            window.queue_table.selectRow(0)  # Bild-Job als Quelle
            self.app.processEvents()
            window._on_apply_settings_to_all_clicked()
            self.app.processEvents()
            # Der Video-Job darf KEINE Bild-Settings bekommen haben
            self.assertNotIn(window.jobs[1]["settings"]["container"], presets.IMAGE_CONTAINERS)
        finally:
            window.close()

    def test_format_switch_to_webp_updates_job(self):
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            self.app.processEvents()
            window.combo_format.setCurrentText("WebP (Bild)")
            self.app.processEvents()
            job = window.jobs[0]
            self.assertEqual(job["settings"]["container"], "webp")
            self.assertEqual(job["settings"]["video_codec"], "libwebp")
            self.assertTrue(job["output_file"].endswith(".webp"))
        finally:
            window.close()


class CropLabelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def _make_label(self):
        from PyQt6.QtGui import QPixmap
        from crop_label import CropImageLabel
        label = CropImageLabel()
        label.resize(220, 120)
        pm = QPixmap(200, 100)
        pm.fill()
        label.setPixmap(pm)  # Anzeige 200x100, zentriert bei Offset (10, 10)
        label.set_source_size(400, 200)  # Quelle doppelt so groß wie Anzeige
        label.set_interactive(True)
        return label

    @staticmethod
    def _mouse_event(type_, x, y):
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QMouseEvent
        return QMouseEvent(type_, QPointF(x, y), Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)

    def _drag(self, label, x1, y1, x2, y2):
        from PyQt6.QtCore import QEvent
        label.mousePressEvent(self._mouse_event(QEvent.Type.MouseButtonPress, x1, y1))
        label.mouseMoveEvent(self._mouse_event(QEvent.Type.MouseMove, x2, y2))
        label.mouseReleaseEvent(self._mouse_event(QEvent.Type.MouseButtonRelease, x2, y2))

    def test_drag_maps_selection_to_source_pixels(self):
        label = self._make_label()
        received = []
        label.crop_changed.connect(received.append)

        self._drag(label, 30, 20, 110, 70)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], {"x": 40, "y": 20, "w": 162, "h": 102})
        self.assertEqual(label.crop(), received[0])

    def test_selection_is_clamped_to_image_area(self):
        label = self._make_label()
        received = []
        label.crop_changed.connect(received.append)

        # Drag endet weit außerhalb der Anzeige → Zuschnitt endet an der Bildkante
        self._drag(label, 30, 20, 500, 500)

        self.assertEqual(len(received), 1)
        crop = received[0]
        self.assertLessEqual(crop["x"] + crop["w"], 400)
        self.assertLessEqual(crop["y"] + crop["h"], 200)

    def test_tiny_drag_is_treated_as_click(self):
        label = self._make_label()
        received = []
        label.crop_changed.connect(received.append)

        self._drag(label, 50, 50, 52, 51)

        self.assertEqual(received, [])
        self.assertIsNone(label.crop())

    def test_drag_inside_selection_moves_crop(self):
        label = self._make_label()
        label.set_crop({"x": 40, "y": 20, "w": 160, "h": 100})
        received = []
        label.crop_changed.connect(received.append)

        # Start in der Auswahl (Widget ~30..110 / 20..70), 20/10 px nach rechts unten
        self._drag(label, 60, 40, 80, 50)

        self.assertEqual(len(received), 1)
        # 20/10 Widget-px = 40/20 Quell-px; Größe bleibt unverändert
        self.assertEqual(received[0], {"x": 80, "y": 40, "w": 160, "h": 100})
        self.assertEqual(label.crop(), received[0])

    def test_move_is_clamped_to_image_bounds(self):
        label = self._make_label()
        label.set_crop({"x": 40, "y": 20, "w": 160, "h": 100})
        received = []
        label.crop_changed.connect(received.append)

        # Weit nach links oben ziehen → Zuschnitt stoppt an der Bildkante
        self._drag(label, 60, 40, -300, -300)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], {"x": 0, "y": 0, "w": 160, "h": 100})

    def test_click_inside_selection_keeps_crop(self):
        label = self._make_label()
        crop = {"x": 40, "y": 20, "w": 160, "h": 100}
        label.set_crop(crop)
        received = []
        label.crop_changed.connect(received.append)

        self._drag(label, 60, 40, 60, 40)

        self.assertEqual(received, [])
        self.assertEqual(label.crop(), crop)

    def test_drag_outside_selection_draws_new_crop(self):
        label = self._make_label()
        label.set_crop({"x": 0, "y": 0, "w": 40, "h": 40})  # Widget: 10..30 / 10..30
        received = []
        label.crop_changed.connect(received.append)

        self._drag(label, 100, 50, 160, 90)

        self.assertEqual(len(received), 1)
        self.assertNotEqual(received[0]["w"], 40)

    def test_paint_during_tiny_draw_does_not_crash(self):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QPaintEvent
        label = self._make_label()

        # Auswahl noch kleiner als MIN_CROP_PX → _selection_to_source liefert None,
        # paintEvent darf dabei nicht crashen (Regression: UnboundLocalError bei text)
        label.mousePressEvent(self._mouse_event(QEvent.Type.MouseButtonPress, 50, 50))
        label.mouseMoveEvent(self._mouse_event(QEvent.Type.MouseMove, 53, 52))
        label.paintEvent(QPaintEvent(label.rect()))
        label.mouseReleaseEvent(self._mouse_event(QEvent.Type.MouseButtonRelease, 53, 52))

    def test_non_interactive_label_ignores_mouse(self):
        label = self._make_label()
        label.set_interactive(False)
        received = []
        label.crop_changed.connect(received.append)

        self._drag(label, 30, 20, 110, 70)

        self.assertEqual(received, [])


class CropQueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_crop_lands_in_job_settings_and_command(self):
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            self.app.processEvents()

            window._on_image_crop_changed({"x": 4, "y": 6, "w": 120, "h": 90})
            job = window.jobs[0]
            self.assertEqual(job["settings"]["crop"], {"x": 4, "y": 6, "w": 120, "h": 90})
            self.assertIn("crop=120:90:4:6", window.edit_cmd_preview.toPlainText())
            self.assertTrue(window.btn_reset_crop.isEnabled())

            # Format-Wechsel behält den Zuschnitt
            window.combo_format.setCurrentText("WebP (Bild)")
            self.app.processEvents()
            self.assertEqual(window.jobs[0]["settings"].get("crop"),
                             {"x": 4, "y": 6, "w": 120, "h": 90})

            # Aufheben entfernt Zuschnitt aus Settings und Kommando
            window.btn_reset_crop.click()
            self.app.processEvents()
            self.assertNotIn("crop", window.jobs[0]["settings"])
            self.assertNotIn("crop=", window.edit_cmd_preview.toPlainText())
            self.assertFalse(window.btn_reset_crop.isEnabled())
        finally:
            window.close()

    def test_fit_mode_links_size_spins_in_mainwindow(self):
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.png"))  # 320x240
            self.app.processEvents()
            # Quellmaße kommen jetzt asynchron — erst auf den Prefetch warten
            wait_for_source_probe(self.app, window.jobs[0])

            window.combo_scale_mode.setCurrentText("Seitenverhältnis beibehalten")
            self.app.processEvents()
            window.spin_width.setValue(200)
            self.assertEqual(window.spin_height.value(), 150)
            window.spin_height.setValue(120)
            self.assertEqual(window.spin_width.value(), 160)
            job = window.jobs[0]
            self.assertEqual(job["settings"]["width"], 160)
            self.assertEqual(job["settings"]["height"], 120)

            # Zuschnitt bestimmt das Seitenverhältnis, sobald gesetzt
            window._on_image_crop_changed({"x": 0, "y": 0, "w": 100, "h": 50})
            window.spin_width.setValue(200)
            self.assertEqual(window.spin_height.value(), 100)

            # Verzerren entkoppelt die Felder wieder
            window.combo_scale_mode.setCurrentText("Verzerren (exakte Größe)")
            self.app.processEvents()
            window.spin_width.setValue(300)
            self.assertEqual(window.spin_height.value(), 100)
        finally:
            window.close()

    def test_apply_to_all_does_not_copy_crop(self):
        from mainwindow import MainWindow
        from PyQt6.QtWidgets import QMessageBox
        from unittest.mock import patch
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            window._add_file_to_queue(os.path.abspath("test_input.png"))
            self.app.processEvents()
            window.queue_table.selectRow(0)
            self.app.processEvents()
            window._on_image_crop_changed({"x": 0, "y": 0, "w": 50, "h": 50})

            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Yes):
                window._on_apply_settings_to_all_clicked()
            self.app.processEvents()

            self.assertIn("crop", window.jobs[0]["settings"])
            self.assertNotIn("crop", window.jobs[1]["settings"])
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
