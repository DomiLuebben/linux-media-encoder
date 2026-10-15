"""Mehrfachauswahl und Entf-Taste in der Renderliste (Warteschlange)."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from mainwindow import MainWindow


class QueueMultiSelectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.window = MainWindow()
        self.window.resize(1400, 800)
        self.window.show()
        for i in range(6):
            path = os.path.join(self._tmp, f"clip{i}.mp4")
            shutil.copy(os.path.abspath("test_input.mp4"), path)
            self.window._add_file_to_queue(path)
        self.app.processEvents()
        self.table = self.window.queue_table

    def tearDown(self):
        self.window.close()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _pos(self, row, col):
        return self.table.visualRect(self.table.model().index(row, col)).center()

    def _selected(self):
        return [i.row() for i in self.table.selectionModel().selectedRows()]

    def _click(self, row, col, modifier=Qt.KeyboardModifier.NoModifier):
        QTest.mouseClick(self.table.viewport(), Qt.MouseButton.LeftButton, modifier, self._pos(row, col))
        self.app.processEvents()

    def test_shift_click_on_link_columns_selects_range_without_dialog(self):
        # Format-/Vorgabe-/Ausgabe-Spalten öffnen per Klick Dialoge; mit
        # Umschalt/Strg dienen sie der Auswahl und dürfen nichts öffnen.
        self._click(0, 0)
        with patch.object(self.window, "_open_export_settings_dialog_for_row") as export, \
                patch.object(self.window, "_choose_output_file_for_row") as choose:
            for col in (1, 2, 3):
                self._click(0, 0)
                self._click(4, col, Qt.KeyboardModifier.ShiftModifier)
                self.assertEqual(self._selected(), [0, 1, 2, 3, 4])
            self._click(5, 2, Qt.KeyboardModifier.ControlModifier)
            self.assertEqual(self._selected(), [0, 1, 2, 3, 4, 5])
            export.assert_not_called()
            choose.assert_not_called()

    def test_plain_click_on_format_column_still_opens_dialog(self):
        with patch.object(self.window, "_open_export_settings_dialog_for_row") as export:
            self._click(2, 1)
            export.assert_called_once_with(2)

    def test_delete_key_removes_all_selected_jobs(self):
        self._click(1, 0)
        self._click(3, 0, Qt.KeyboardModifier.ShiftModifier)
        names = [os.path.basename(j["input_file"]) for j in self.window.jobs]
        self.assertEqual(self._selected(), [1, 2, 3])
        QTest.keyClick(self.table, Qt.Key.Key_Delete)
        self.app.processEvents()
        self.assertEqual(
            [os.path.basename(j["input_file"]) for j in self.window.jobs],
            [names[0], names[4], names[5]],
        )
        self.assertEqual(self.table.rowCount(), 3)
        # Nachrückende Zeile ist markiert → direkt weiter mit Entf möglich
        self.assertEqual(self._selected(), [1])

    def test_ctrl_a_then_delete_empties_queue_and_locks_panel(self):
        self.table.setFocus()
        QTest.keyClick(self.table, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self._selected(), [0, 1, 2, 3, 4, 5])
        QTest.keyClick(self.table, Qt.Key.Key_Delete)
        self.app.processEvents()
        self.assertEqual(self.window.jobs, [])
        self.assertEqual(self.table.rowCount(), 0)
        self.assertFalse(self.window.settings_widget.isEnabled())

    def test_delete_is_ignored_while_queue_runs(self):
        self._click(0, 0)
        self._click(2, 0, Qt.KeyboardModifier.ShiftModifier)
        self.window.is_running = True
        try:
            QTest.keyClick(self.table, Qt.Key.Key_Delete)
            self.app.processEvents()
            self.assertEqual(len(self.window.jobs), 6)
            self.assertEqual(self.table.rowCount(), 6)
        finally:
            self.window.is_running = False

    def test_busy_jobs_survive_delete(self):
        self.window.jobs[2]["status"] = "Codiert..."
        self._click(1, 0)
        self._click(3, 0, Qt.KeyboardModifier.ShiftModifier)
        with patch("mainwindow.QMessageBox.warning"):
            QTest.keyClick(self.table, Qt.Key.Key_Delete)
        self.app.processEvents()
        self.assertEqual(len(self.window.jobs), 4)
        self.assertEqual(self.window.jobs[1]["status"], "Codiert...")

    def test_deleting_many_rows_loads_settings_once(self):
        self._click(0, 0)
        self._click(4, 0, Qt.KeyboardModifier.ShiftModifier)
        with patch.object(self.window, "_load_job_settings_to_ui") as load:
            QTest.keyClick(self.table, Qt.Key.Key_Delete)
            self.app.processEvents()
        self.assertLessEqual(load.call_count, 1)

    def test_context_menu_keeps_multi_selection(self):
        self._click(0, 0)
        self._click(3, 0, Qt.KeyboardModifier.ShiftModifier)
        captured = {}

        def fake_exec(menu, *args, **kwargs):
            captured["selected"] = self._selected()
            captured["texts"] = [a.text() for a in menu.actions() if a.text()]
            return None

        with patch("mainwindow.QMenu.exec", fake_exec):
            self.window._on_queue_context_menu(self._pos(2, 0))
        self.assertEqual(captured["selected"], [0, 1, 2, 3])
        self.assertTrue(any("4" in t and "entfernen" in t for t in captured["texts"]))


if __name__ == "__main__":
    unittest.main()
