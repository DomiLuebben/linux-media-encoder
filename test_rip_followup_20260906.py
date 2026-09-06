"""Nachpruefung der Ripping-Korrekturen vom 06.09.2026 (zweiter Durchgang).

Jeder Test hier deckt einen Befund ab, den die bestehende Suite trotz 263
gruener Tests nicht bemerkt hat.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication, QMessageBox

import optical_media as om
import presets
from mainwindow import MainWindow
from test_rip_deep import second_video_source


def _dialog():
    """Ripper-Dialog ohne Laufwerkssuche — sonst haengt der Test am echten System."""
    from disc_ripper_dialog import DiscRipperDialog
    with patch("optical_media.scan_optical_drives", return_value=[]), \
         patch("optical_media.check_optical_environment", return_value=[]):
        return DiscRipperDialog()


class TwoStagePersistenceTests(unittest.TestCase):
    """Der Schalter 'zweistufig' wurde beim Umschalten nicht mehr gespeichert:
    die QSettings-Zeile war in eine andere Methode hinter ein return gerutscht."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_toggling_two_stage_writes_the_setting(self):
        dialog = _dialog()
        try:
            with patch("disc_ripper_dialog.QSettings") as settings:
                dialog._on_two_stage_toggled(True)
            settings.return_value.setValue.assert_called_once_with("two_stage_rip", True)

            with patch("disc_ripper_dialog.QSettings") as settings:
                dialog._on_two_stage_toggled(False)
            settings.return_value.setValue.assert_called_once_with("two_stage_rip", False)
        finally:
            dialog.close()

    def test_confirm_rip_outputs_touches_no_settings(self):
        dialog = _dialog()
        try:
            with patch("disc_ripper_dialog.QSettings") as settings:
                self.assertTrue(dialog._confirm_rip_outputs(["/tmp/lme-does-not-exist.mkv"]))
            settings.return_value.setValue.assert_not_called()
        finally:
            dialog.close()


class ApplyToAllTests(unittest.TestCase):
    """Die Fehlertoleranz ist ein Kontrollkaestchen fuer jeden Job. Sie in die
    Disc-Identitaet aufzunehmen haette sie von 'auf alle anwenden' ausgesperrt."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_error_tolerance_is_copied_but_disc_identity_is_not(self):
        win = MainWindow()
        try:
            win._add_file_to_queue(os.path.abspath("test_input.mp4"))
            win._add_file_to_queue(second_video_source())
            win.jobs[0]["settings"].update(ignore_errors=True, title_num=3)
            win.jobs[1]["settings"].update(ignore_errors=False, title_num=9)
            win.queue_table.selectRow(0)
            with patch("mainwindow.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.Yes):
                win._on_apply_settings_to_all_clicked()
            self.assertTrue(win.jobs[1]["settings"]["ignore_errors"])
            self.assertEqual(win.jobs[1]["settings"]["title_num"], 9)
        finally:
            win.close()

    def test_preset_switch_keeps_error_tolerance(self):
        kept = presets.preserve_disc_settings(
            presets.PRESETS["H.265 MKV 1080p30"], {"ignore_errors": False, "title_num": 4})
        self.assertIs(kept["ignore_errors"], False)
        self.assertEqual(kept["title_num"], 4)

    def test_ignore_errors_is_not_treated_as_source_bound(self):
        self.assertNotIn("ignore_errors", presets.SOURCE_SETTING_KEYS)
        self.assertIn("title_num", presets.SOURCE_SETTING_KEYS)


class OutputNamingTests(unittest.TestCase):
    """Ein Datentraeger ohne verwertbares Label ergab den Dateinamen '.iso' —
    eine versteckte Datei, die der Nutzer im Zielordner nicht wiederfindet."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_unusable_label_falls_back_instead_of_hiding_the_file(self):
        dialog = _dialog()
        try:
            self.assertEqual(dialog._safe_disc_label("...", fallback="disc_backup"),
                             "disc_backup")
            self.assertEqual(dialog._safe_disc_label(None), "Disc")
            self.assertNotIn("/", dialog._safe_disc_label("../../etc/passwd"))
        finally:
            dialog.close()

    def test_iso_dump_uses_the_fallback_name(self):
        dialog = _dialog()
        try:
            dialog.current_source = "/dev/sr0"
            dialog.inspection_result = om.DiscInspectionResult(
                source_path="/dev/sr0", disc_type=om.DiscType.DATA_DISC, disc_label="///")
            with tempfile.TemporaryDirectory() as root, \
                 patch("disc_ripper_dialog.get_optical_media_size", return_value=0), \
                 patch("disc_ripper_dialog.IsoDumpWorker") as worker:
                dialog._start_iso_dump(root)
                target = worker.call_args.kwargs["output_iso_path"]
            self.assertEqual(os.path.basename(target), "disc_backup.iso")
        finally:
            dialog.close()


class AudioCdOverwriteTests(unittest.TestCase):
    """Video- und ISO-Rip fragen vor dem Ueberschreiben, der CD-Direkt-Rip nicht."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _cd_dialog(self, dialog):
        dialog.current_source = "/dev/sr0"
        dialog.inspection_result = om.DiscInspectionResult(
            source_path="/dev/sr0", disc_type=om.DiscType.AUDIO_CD,
            audio_tracks=[om.AudioTrackInfo(track_num=1, duration_sec=200, title="Lied")])
        return dialog

    def test_declining_the_overwrite_keeps_the_existing_file(self):
        from disc_rip_worker import audio_cd_output_filename
        dialog = self._cd_dialog(_dialog())
        try:
            track = dialog.inspection_result.audio_tracks[0]
            codec = om.audio_codec_key_from_label(dialog.combo_cd_codec.currentText())
            with tempfile.TemporaryDirectory() as root:
                existing = Path(root) / audio_cd_output_filename(track, codec)
                existing.write_bytes(b"original")
                with patch("disc_ripper_dialog.QMessageBox.question",
                           return_value=QMessageBox.StandardButton.No), \
                     patch("disc_ripper_dialog.AudioCdRipWorker") as worker:
                    dialog._start_direct_rip([0], root)
                worker.assert_not_called()
                self.assertEqual(existing.read_bytes(), b"original")
            self.assertFalse(dialog._is_ripping)
        finally:
            dialog.close()

    def test_worker_and_dialog_agree_on_the_filename(self):
        """Ein eigener Namensbau im Dialog wuerde die Pruefung wertlos machen."""
        from disc_rip_worker import AudioCdRipWorker, audio_cd_output_filename
        track = om.AudioTrackInfo(track_num=3, duration_sec=200, title="Mein: Lied")
        with tempfile.TemporaryDirectory() as root:
            worker = AudioCdRipWorker("/dev/sr0", [track], root, codec="flac", bitrate="")
            with patch.object(worker, "process", None), patch("disc_rip_worker.QProcess"):
                worker.current_track_idx = 0
                worker._rip_next_track()
            self.assertEqual(os.path.basename(worker._final_out_file),
                             audio_cd_output_filename(track, "flac"))


class TitleStreamProbeTests(unittest.TestCase):
    """An echter Hardware gemessen: lsdvd meldet fuer den Hauptfilm 6 Untertitel,
    FFmpeg 12 -- Position 4 ist bei lsdvd deutsch, bei FFmpeg englisch. Faellt die
    Abfrage auf lsdvd zurueck, rippt der Nutzer stillschweigend die falsche Sprache."""

    @classmethod
    def setUpClass(cls):
        # Ohne QApplication stuerzt jedes Widget dieser Klasse mit einem
        # Speicherauszug ab. Fehlte sie, lief die Klasse nur dann durch, wenn
        # zufaellig eine andere Testklasse vorher eine angelegt hatte.
        cls.app = QApplication.instance() or QApplication([])

    def test_cold_drive_timeout_is_retried_before_giving_up(self):
        calls = []

        def probe(path, max_titles=99, title_numbers=None, timeout=10):
            calls.append(timeout)
            result = om.DiscInspectionResult(source_path=path, disc_type=om.DiscType.DVD_VIDEO)
            if len(calls) > 1:                       # zweiter Versuch, Laufwerk dreht
                result.video_titles = [om.VideoTitleInfo(title_num=1, duration_sec=60)]
            return result

        with patch("optical_media.probe_dvd_titles_ffprobe", side_effect=probe):
            got = om._probe_dvd_title_streams("/dev/sr0", 1)
        self.assertIsNotNone(got, "nach dem Anlaufen des Laufwerks aufgegeben")
        self.assertEqual(calls, [om.DVD_TITLE_PROBE_TIMEOUT, om.DVD_TITLE_PROBE_RETRY_TIMEOUT])
        self.assertGreater(om.DVD_TITLE_PROBE_TIMEOUT, 10,
                           "10 s reichen am kalten Laufwerk gemessen nicht")

    def test_unconfirmed_streams_are_reported_instead_of_silently_kept(self):
        from test_optical_media import LSDVD_OY_FIXTURE
        run = subprocess.CompletedProcess([], 0, LSDVD_OY_FIXTURE, "")
        with patch("optical_media._run_inspection_command", return_value=run), \
             patch("optical_media._probe_dvd_title_streams", return_value=None):
            result = om.scan_dvd_source("/dev/sr0")
        self.assertTrue(result.video_titles, "Titel duerfen nicht verloren gehen")
        self.assertTrue(result.warning, "stiller Rueckfall auf lsdvds Spurreihenfolge")
        self.assertIn("abweichen", result.warning)
        # Als error getarnt waere die Warnung schaedlich: der Dialog leert dann
        # die Tabelle und sperrt den Aktionsknopf -- die Disc waere unrippbar.
        self.assertIsNone(result.error)

    def test_warning_keeps_the_disc_rippable_and_is_shown(self):
        """Die Warnung darf die Titeltabelle nicht leeren."""
        dialog = _dialog()
        try:
            dialog.current_source = "/dev/sr0"
            dialog.inspection_result = om.DiscInspectionResult(
                source_path="/dev/sr0", disc_type=om.DiscType.DVD_VIDEO,
                disc_label="TESTDISC", warning="Spurliste für Titel 1 unbestätigt.",
                video_titles=[om.VideoTitleInfo(title_num=1, duration_sec=3600)])
            dialog._display_inspection_result()
            self.assertEqual(dialog.table_titles.rowCount(), 1, "Titel ausgeblendet")
            self.assertTrue(dialog.btn_action.isEnabled(), "Aktionsknopf gesperrt")
            # isVisible() ist bei einem nie gezeigten Dialog immer False —
            # isVisibleTo() prueft, ob das Label beim Anzeigen sichtbar waere.
            self.assertTrue(dialog.lbl_warn_encryption.isVisibleTo(dialog))
            self.assertIn("unbestätigt", dialog.lbl_warn_encryption.text())
        finally:
            dialog.close()

    def test_confirmed_streams_replace_the_lsdvd_order(self):
        from test_optical_media import LSDVD_OY_FIXTURE
        run = subprocess.CompletedProcess([], 0, LSDVD_OY_FIXTURE, "")
        actual = om.VideoTitleInfo(
            title_num=1, duration_sec=60,
            subtitle_streams=[om.SubtitleStreamInfo(stream_idx=i, langcode="ger")
                              for i in range(12)])
        with patch("optical_media._run_inspection_command", return_value=run), \
             patch("optical_media._probe_dvd_title_streams", return_value=actual):
            result = om.scan_dvd_source("/dev/sr0")
        self.assertIsNone(result.error)
        self.assertEqual(len(result.video_titles[0].subtitle_streams), 12)


class FruitlessProbeTests(unittest.TestCase):
    """Eine Quelle ohne lesbaren Titel durfte 99-mal in den 10-Sekunden-Ablauf
    laufen — bis zu 16 Minuten mit stehendem Fortschrittsbalken."""

    def test_probe_gives_up_instead_of_scanning_all_titles(self):
        clock = [0.0]

        def slow_miss(*args, **kwargs):
            clock[0] += 10.0  # jeder Versuch laeuft in den Zeitablauf
            return subprocess.CompletedProcess([], 1, "", "")

        with patch("optical_media._run_inspection_command", side_effect=slow_miss) as run, \
             patch("optical_media.time.monotonic", side_effect=lambda: clock[0]):
            result = om.probe_dvd_titles_ffprobe("/not-a-dvd")

        self.assertLess(run.call_count, 10, "Suche lief trotz Fehlschlaegen weiter")
        self.assertEqual(result.video_titles, [])
        self.assertTrue(result.error)

    def test_cheap_misses_before_the_first_title_are_still_tolerated(self):
        """Titel 1 darf fehlschlagen, ohne dass die Suche aufgibt."""
        fixture = Path("work/rip-deep-20260906/ffprobe.json")
        if not fixture.exists():
            self.skipTest("ffprobe-Fixture aus dem Auditlauf nicht vorhanden")
        payload = fixture.read_text()
        calls = []

        def probe(args, **kwargs):
            calls.append(args)
            code = 1 if len(calls) <= 2 else 0
            return subprocess.CompletedProcess(args, code, payload if code == 0 else "", "")

        with patch("optical_media._run_inspection_command", side_effect=probe):
            result = om.probe_dvd_titles_ffprobe("/dvd")
        self.assertTrue(result.video_titles, "Titel nach zwei billigen Fehlschlaegen verloren")


if __name__ == "__main__":
    unittest.main()
