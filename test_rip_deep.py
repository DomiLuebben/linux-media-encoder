"""Regression tests for DVD probing and disc settings across export operations."""
import os
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
import optical_media as om
import presets
from mainwindow import MainWindow
from export_settings_dialog import ExportSettingsDialog
from test_optical_media import LSDVD_OY_FIXTURE

def second_video_source():
    """Zweite Videoquelle fuer Warteschlangentests. Frueher zeigte das auf
    test_input_lme.mp4 -- eine Encoder-Ausgabe, die .gitignore erfasst und die
    im frischen Klon gar nicht existiert."""
    import shutil, tempfile
    handle, path = tempfile.mkstemp(prefix='lme_test_second_', suffix='.mp4')
    os.close(handle)
    shutil.copyfile(os.path.abspath('test_input.mp4'), path)
    return path


DISC = dict(disc_type='dvd_video', input_args=['-f','dvdvideo','-title','2'],
            title_num=2, audio_stream_idx=1, subtitle_stream_idx=0,
            source_width=720, source_height=576, source_duration=1800,
            two_stage=True, ignore_errors=False)

class DvdProbeTests(unittest.TestCase):
    def test_lsdvd_indices_are_zero_based_and_chapters_have_offsets(self):
        title=om.parse_lsdvd_output(LSDVD_OY_FIXTURE).video_titles[0]
        self.assertEqual([s.stream_idx for s in title.audio_streams], [0,1])
        self.assertEqual([s.stream_idx for s in title.subtitle_streams], [0,1])
        self.assertEqual([c.start_sec for c in title.chapters], [0,1800,3600])

    def test_lsdvd_requests_streams_and_chapters(self):
        import subprocess
        with patch('optical_media._run_inspection_command', return_value=subprocess.CompletedProcess([],0,LSDVD_OY_FIXTURE,'')) as run:
            om.scan_dvd_source('/dvd')
        self.assertIn('-x', run.call_args_list[0].args[0])

class DiscSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_main_presets_and_format_preserve_disc_identity(self):
        win=MainWindow()
        try:
            win._add_file_to_queue(os.path.abspath('test_input.mp4'))
            job=win.jobs[0]
            for method,value in ((win._on_preset_changed,'H.265 MKV 1080p30'),
                                 (win._on_preset_changed,'Stream-Kopie (Verlustfrei)'),
                                 (win._on_format_changed,'MKV (H.265 / AAC)')):
                job['settings'].update(DISC)
                method(value)
                for key,val in DISC.items():
                    self.assertEqual(job['settings'].get(key),val,key)
        finally:
            win.close()

    def test_export_preset_preserves_disc_identity(self):
        settings=dict(presets.PRESETS['MP4 (H.264 / AAC) - Standard 1080p'], **DISC)
        with patch.object(ExportSettingsDialog,'_start_probe'), patch.object(ExportSettingsDialog,'_trigger_preview_update'):
            dialog=ExportSettingsDialog(os.path.abspath('test_input.mp4'),'out.mkv',settings)
            try:
                for label in ('H.265 MKV 1080p30','Stream-Kopie (Verlustfrei)'):
                    dialog._on_preset_changed(label)
                    for key,val in DISC.items():
                        self.assertEqual(dialog.settings.get(key),val,key)
            finally:
                dialog.close()

class RipLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_apply_all_does_not_copy_disc_title_to_another_source(self):
        from PyQt6.QtWidgets import QMessageBox
        win=MainWindow()
        try:
            win._add_file_to_queue(os.path.abspath('test_input.mp4'))
            win._add_file_to_queue(second_video_source())
            win.jobs[0]['settings'].update(DISC)
            other=dict(DISC,title_num=7,input_args=['-f','dvdvideo','-title','7'])
            win.jobs[1]['settings'].update(other)
            win.queue_table.selectRow(0)
            with patch('mainwindow.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
                win._on_apply_settings_to_all_clicked()
            for key,value in other.items():
                self.assertEqual(win.jobs[1]['settings'][key],value,key)
        finally:
            win.close()

    def test_probe_uses_disc_transport_and_selected_title(self):
        import subprocess
        from unittest.mock import Mock
        with patch.object(ExportSettingsDialog,'_start_probe'), patch.object(ExportSettingsDialog,'_trigger_preview_update'):
            dialog=ExportSettingsDialog(os.path.abspath('test_input.mp4'),'out.mkv',dict(container='mkv',**DISC))
        try:
            def thread(*args,**kwargs):
                return Mock(start=kwargs['target'])
            with patch('threading.Thread',side_effect=thread), patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,'{}','')) as run:
                ExportSettingsDialog._start_probe(dialog)
            args=run.call_args.args[0]
            self.assertIn('dvdvideo',args)
            self.assertEqual(args[args.index('-title')+1],'2')
        finally:
            dialog.close()

    def test_close_stops_active_direct_rip_and_locks_source(self):
        from disc_ripper_dialog import DiscRipperDialog
        from unittest.mock import Mock
        with patch('optical_media.scan_optical_drives',return_value=[]),patch('optical_media.check_optical_environment',return_value=[]):
            dialog=DiscRipperDialog()
        worker=Mock()
        dialog.active_worker=worker
        dialog._set_ui_ripping_state(True)
        self.assertFalse(dialog.source_group.isEnabled())
        dialog.reject()
        worker.stop.assert_called_once()
        self.assertFalse(dialog._is_ripping)
        dialog.close()

    def test_direct_rip_refuses_duplicate_names_and_declined_overwrite(self):
        import tempfile
        from pathlib import Path
        from disc_ripper_dialog import DiscRipperDialog
        from PyQt6.QtWidgets import QMessageBox
        with patch('optical_media.scan_optical_drives',return_value=[]),patch('optical_media.check_optical_environment',return_value=[]):
            dialog=DiscRipperDialog()
        try:
            with patch('disc_ripper_dialog.QMessageBox.warning'):
                self.assertFalse(dialog._confirm_rip_outputs(['/tmp/x.mkv','/tmp/x.mkv']))
            with tempfile.TemporaryDirectory() as root:
                p=Path(root)/'saved.mkv';p.write_bytes(b'original')
                with patch('disc_ripper_dialog.QMessageBox.question',return_value=QMessageBox.StandardButton.No):
                    self.assertFalse(dialog._confirm_rip_outputs([str(p)]))
                self.assertEqual(p.read_bytes(),b'original')
            self.assertNotIn('/',dialog._safe_disc_label('../../other/disc'))
        finally:
            dialog.close()

    def test_incomplete_iso_does_not_replace_existing_output(self):
        import tempfile
        from pathlib import Path
        from disc_rip_worker import IsoDumpWorker
        from PyQt6.QtCore import QProcess
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'disc.iso';out.write_bytes(b'original')
            worker=IsoDumpWorker('/dev/sr0',str(out),total_size_bytes=4096)
            Path(worker._tmp_iso_path).write_bytes(b'x'*2048)
            results=[]
            worker.finished.connect(lambda ok,msg:results.append(ok))
            worker._handle_finished(0,QProcess.ExitStatus.NormalExit)
            self.assertEqual(results,[False])
            self.assertEqual(out.read_bytes(),b'original')
            self.assertFalse(Path(worker._tmp_iso_path).exists())

    def test_stage_two_runs_requested_subtitle_generation(self):
        from test_disc_audit_20260906 import queue_window
        from unittest.mock import Mock
        job=dict(settings={})
        win=queue_window(job)
        win._job_needs_subtitle_generation=Mock(return_value=True)
        win._run_subtitle_pipeline=Mock()
        win._start_current_ffmpeg_job=Mock()
        MainWindow._start_prepared_disc_job(win,job)
        win._run_subtitle_pipeline.assert_called_once_with(job)
        win._start_current_ffmpeg_job.assert_not_called()

    def test_generated_subtitle_audio_reads_correct_dvd_title(self):
        from test_disc_audit_20260906 import queue_window
        from unittest.mock import Mock
        job=dict(input_file='/dvd', settings=dict(DISC))
        win=queue_window(job)
        win._on_subtitle_audio_extracted=Mock()
        win._on_subtitle_process_failed_to_start=Mock()
        try:
            with patch('mainwindow.QProcess') as process:
                MainWindow._run_subtitle_pipeline(win,job)
            args=process.return_value.start.call_args.args[1]
            self.assertIn('dvdvideo',args)
            self.assertEqual(args[args.index('-title')+1],'2')
            self.assertIn('0:a:1?',args)
        finally:
            os.unlink(job['settings']['temp_audio_path'])
