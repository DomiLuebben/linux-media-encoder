import tempfile
import os
import sys
import unittest

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QTimer

from mainwindow import MainWindow


class QueueBehaviorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        # Modale QMessageBoxen automatisch mit "Yes"/"Ok" schließen
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

    def test_output_equals_input_is_blocked(self):
        # Ausgabe == Quelle darf KEINEN Encode starten (Datenverlust-Schutz)
        window = self._window_with_job()
        try:
            job = window.jobs[0]
            job["output_file"] = job["input_file"]
            window.is_running = True
            window.current_job_idx = 0
            window._start_current_ffmpeg_job(job)
            self.app.processEvents()
            self.assertIsNone(window.active_worker)
            self.assertEqual(job["status"], "Fehlgeschlagen")
            self.assertFalse(window.is_running)  # Queue sauber beendet, keine Rekursion
        finally:
            window.close()

    def test_failed_job_not_repicked_during_run(self):
        # Ein bereits fehlgeschlagener Job wird im laufenden Durchlauf nicht
        # erneut ausgewählt (sonst Endlosschleife).
        window = self._window_with_job()
        try:
            window.jobs[0]["status"] = "Fehlgeschlagen"
            window.is_running = True
            window._process_next_job()
            self.app.processEvents()
            self.assertEqual(window.current_job_idx, -1)
            self.assertFalse(window.is_running)
        finally:
            window.close()

    def test_settings_panel_locked_without_job(self):
        # Ohne geladene/ausgewählte Datei muss das Einstellungs-Panel gesperrt
        # sein, sonst lassen sich Format/Vorgabe ohne Job-Sync verstellen.
        window = MainWindow()
        try:
            self.assertFalse(window.settings_widget.isEnabled())
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()
            self.assertTrue(window.settings_widget.isEnabled())
            # Format -> HEVC synchronisiert den Codec, sobald ein Job da ist
            window.combo_format.setCurrentText("HEVC / H.265 (MP4)")
            self.app.processEvents()
            self.assertEqual(window.combo_vcodec.currentText(), "libx265")
            # Letzten Job entfernen -> Panel wieder gesperrt
            window.queue_table.selectRow(0)
            window._on_remove_selected_clicked()
            self.app.processEvents()
            self.assertFalse(window.settings_widget.isEnabled())
        finally:
            window.close()

    def test_start_resets_failed_to_ready(self):
        # Beim Start eines neuen Laufs werden fehlgeschlagene Jobs erneut bereitgestellt
        window = self._window_with_job()
        try:
            window.jobs[0]["status"] = "Fehlgeschlagen"
            window._on_start_queue()
            # Job wurde reaktiviert und sofort in Verarbeitung genommen
            self.assertNotEqual(window.jobs[0]["status"], "Fehlgeschlagen")
            window._on_stop_queue()
            self.app.processEvents()
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()


class DiscTwoStageQueueTest(unittest.TestCase):
    """Disc-Jobs laufen zweistufig: erst verlustfrei lesen, dann konvertieren."""

    @classmethod
    def setUpClass(cls):
        from PyQt6 import QtWidgets
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    def _disc_job(self, staged=None):
        settings = {
            "container": "mp4",
            "input_args": ["-playlist", "3"],
            "disc_type": "bluray",
            "title_num": 3,
            "two_stage": True,
        }
        if staged is not None:
            settings["_staged_source"] = staged
        return {
            "input_file": "/dev/sr0",
            "output_dir": "/tmp",
            "output_file": "/tmp/film.mp4",
            "settings": settings,
            "status": "Bereit",
        }

    def test_disc_job_needs_the_rip_stage_first(self):
        from mainwindow import MainWindow
        window = MainWindow()
        self.assertTrue(window._job_needs_disc_rip(self._disc_job()))

    def test_stage_is_skipped_once_the_staged_file_exists(self):
        from mainwindow import MainWindow
        window = MainWindow()
        with tempfile.NamedTemporaryFile(suffix=".mkv") as handle:
            self.assertFalse(window._job_needs_disc_rip(self._disc_job(handle.name)))

    def test_a_vanished_staged_file_triggers_the_rip_again(self):
        # Nach einem Neustart zeigt ein alter Pfad ins Leere -- dann muss
        # erneut gelesen werden statt stillschweigend nichts zu tun.
        from mainwindow import MainWindow
        window = MainWindow()
        self.assertTrue(window._job_needs_disc_rip(self._disc_job("/gibt/es/nicht.mkv")))

    def test_direct_conversion_is_the_default_and_skips_the_stage(self):
        # Ohne ausdrueckliche Wahl wird direkt von der Disc konvertiert:
        # gemessen setzt das Laufwerk die Grenze, nicht die CPU.
        from mainwindow import MainWindow
        window = MainWindow()
        job = self._disc_job()
        job["settings"]["two_stage"] = False
        self.assertFalse(window._job_needs_disc_rip(job))
        del job["settings"]["two_stage"]
        self.assertFalse(window._job_needs_disc_rip(job))

    def test_ordinary_file_jobs_are_untouched(self):
        from mainwindow import MainWindow
        window = MainWindow()
        job = {"input_file": "/tmp/a.mp4", "settings": {"container": "mp4"}}
        self.assertFalse(window._job_needs_disc_rip(job))

    def test_staged_path_never_survives_a_session(self):
        # Ein Pfad aus dem letzten Lauf wuerde Stufe 1 faelschlich ueberspringen.
        import presets
        self.assertIn("_staged_source", presets.TRANSIENT_SETTING_KEYS)

    def test_second_stage_drops_every_disc_option(self):
        import presets
        settings = {
            "container": "mp4", "video_codec": "libx264", "audio_codec": "aac",
            "input_args": ["-playlist", "3"], "disc_type": "bluray",
        }
        wirksam = {k: v for k, v in settings.items() if k not in ("input_args", "disc_type")}
        args = presets.get_ffmpeg_args("/var/tmp/stage.mkv", "/tmp/film.mp4", wirksam)
        zeile = " ".join(args)
        self.assertNotIn("-playlist", zeile)
        self.assertNotIn("bluray:", zeile)
        self.assertIn("/var/tmp/stage.mkv", zeile)

    def test_worker_status_ignores_initializing_message(self):
        # "Initialisiere FFmpeg..." soll den aussagekräftigen Status nicht überschreiben
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()
            window.current_job_idx = 0
            job = window.jobs[0]
            job["status"] = "Codiert..."
            window._on_worker_status("Initialisiere FFmpeg...")
            self.assertEqual(job["status"], "Codiert...")
        finally:
            window.close()

    def test_worker_status_accepts_abort_message(self):
        # "Breche ab..." soll den Status gezielt überschreiben
        from mainwindow import MainWindow
        window = MainWindow()
        try:
            window._add_file_to_queue(os.path.abspath("test_input.mp4"))
            self.app.processEvents()
            window.current_job_idx = 0
            job = window.jobs[0]
            job["status"] = "Codiert..."
            window._on_worker_status("Breche ab...")
            self.assertEqual(job["status"], "Breche ab...")
        finally:
            window.close()

    def test_phase_status_formatting(self):
        from mainwindow import MainWindow
        from i18n import tr
        window = MainWindow()
        try:
            # Ohne Phase -> gegebener Text bleibt erhalten
            self.assertEqual(window._phase_status({}, "Codiert..."), "Codiert...")
            # Phase rip -> Stufenbezeichnung + "..."
            self.assertEqual(window._phase_status({"_phase": "rip"}, "Liest Disc..."), f"{tr('Stufe 1/2 · Liest Disc')}...")
            # Phase encode -> Stufenbezeichnung + "..."
            self.assertEqual(window._phase_status({"_phase": "encode"}, "Codiert..."), f"{tr('Stufe 2/2 · Konvertiert')}...")
        finally:
            window.close()


