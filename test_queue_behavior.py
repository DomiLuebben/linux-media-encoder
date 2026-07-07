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
