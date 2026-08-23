# -*- coding: utf-8 -*-
"""Unit-Tests für das optische Medien- & Disc-Ripper-Modul (optical_media.py)."""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import optical_media
from optical_media import (
    DiscType,
    OpticalDriveInfo,
    AudioTrackInfo,
    AudioStreamInfo,
    SubtitleStreamInfo,
    ChapterInfo,
    VideoTitleInfo,
    DiscInspectionResult,
    scan_optical_drives,
    detect_disc_type,
    parse_cdparanoia_toc,
    parse_cd_text,
    parse_lsdvd_output,
    parse_bdinfo_output,
    build_dvd_rip_args,
    build_bluray_rip_args,
    build_audio_cd_rip_command,
    build_audio_encode_args,
    build_iso_dump_command,
    check_dvd_encryption_support,
    check_bluray_encryption_support,
    check_ffmpeg_optical_capabilities,
)


CDPARANOIA_STDERR_FIXTURE = """cdparanoia III release 10.2 (September 11, 2008)

Table of contents (audio tracks only):
track        length               begin        copy pre ch
===========================================================
  1.    19515 [04:20.15]          150 [00:02.00]    no   no  2
  2.    18225 [04:03.00]        19665 [04:22.15]    no   no  2
  3.    23400 [05:12.00]        37890 [08:25.15]    no   no  2
  4.    15675 [03:29.00]        61290 [13:37.15]    no   no  2
  5.    21000 [04:40.00]        76965 [17:06.15]    no   no  2
TOTAL   97815 [21:44.15] (audio only)
"""

CD_INFO_FIXTURE = """cd-info version 2.3.0 x86_64-pc-linux-gnu
CD-ROM Track List (1 - 5)
  #: MSF       LSN    Type      Green? Copy?
  1: 00:02:00  000000 audio     no     no   
  2: 04:22:15  019515 audio     no     no   
  3: 08:25:15  037740 audio     no     no   
  4: 13:37:15  061140 audio     no     no   
  5: 17:06:15  076815 audio     no     no   
170: 21:46:15  097815 leadout (21:44:15 raw 97815 sectors)
CD-TEXT for Disc:
	TITLE: Best of Linux Audio
	PERFORMER: Open Source Orchestra
	SONGWRITER: Various
CD-TEXT for Track  1:
	TITLE: Symphony No. 1 in C Major
	PERFORMER: Open Source Orchestra
CD-TEXT for Track  2:
	TITLE: Concerto for Kernel and Userspace
	PERFORMER: Open Source Orchestra
CD-TEXT for Track  3:
	TITLE: Suite for PipeWire and ALSA
	PERFORMER: Open Source Orchestra
CD-TEXT for Track  4:
	TITLE: Overture to Open Source
	PERFORMER: Open Source Orchestra
CD-TEXT for Track  5:
	TITLE: Finale: Return Code Zero
	PERFORMER: Open Source Orchestra
"""

LSDVD_OY_FIXTURE = """lsdvd = {
    'device': '/dev/sr0',
    'title': 'TEST_DVD_VIDEO',
    'vmg_id': 'DVDVIDEO-VMG',
    'provider_id': '',
    'track': [
        {
            'ix': 1,
            'length': 5400.0,
            'vts_id': 'DVDVIDEO-VTS',
            'playback_time': '01:30:00.000',
            'chapter': [
                {'ix': 1, 'length': 1800.0, 'startcell': 1},
                {'ix': 2, 'length': 1800.0, 'startcell': 2},
                {'ix': 3, 'length': 1800.0, 'startcell': 3}
            ],
            'subp': [
                {'ix': 1, 'langcode': 'de', 'language': 'German', 'content': 'Normal'},
                {'ix': 2, 'langcode': 'en', 'language': 'English', 'content': 'Normal'}
            ],
            'audio': [
                {'ix': 1, 'langcode': 'de', 'language': 'German', 'format': 'ac3', 'channels': 6, 'frequency': 48000},
                {'ix': 2, 'langcode': 'en', 'language': 'English', 'format': 'dts', 'channels': 6, 'frequency': 48000}
            ],
            'video': {'aspect': '16:9', 'format': 'PAL', 'width': 720, 'height': 576, 'fps': 25.0, 'codec': 'mpeg2video'}
        },
        {
            'ix': 2,
            'length': 300.0,
            'vts_id': 'DVDVIDEO-VTS',
            'playback_time': '00:05:00.000',
            'chapter': [
                {'ix': 1, 'length': 300.0, 'startcell': 1}
            ],
            'subp': [],
            'audio': [
                {'ix': 1, 'langcode': 'de', 'language': 'German', 'format': 'ac3', 'channels': 2, 'frequency': 48000}
            ],
            'video': {'aspect': '16:9', 'format': 'PAL', 'width': 720, 'height': 576, 'fps': 25.0, 'codec': 'mpeg2video'}
        }
    ]
}"""

BD_INFO_FIXTURE = """Using libbluray version 1.4.1
Volume Identifier   : BIG_BUCK_BUNNY_BD
Blu-ray Disc Type   : BD-ROM
Disc Title          : Big Buck Bunny 1080p

Playlists:
  Playlist: 00800.MPLS, Duration: 00:10:34, Chapters: 5
    Video Stream: H.264 / 1080p / 24 fps / 16:9 / High Profile 4.1
    Audio Stream: DTS-HD Master Audio / 5.1 / 48 kHz / 24-bit (German)
    Audio Stream: AC-3 / 5.1 / 48 kHz / 640 kbps (English)
    Subtitle: PGS / German
    Subtitle: PGS / English
  Playlist: 00801.MPLS, Duration: 00:02:15, Chapters: 1
    Video Stream: H.264 / 1080p / 24 fps / 16:9 / High Profile 4.1
    Audio Stream: AC-3 / 2.0 / 48 kHz / 192 kbps (German)
"""


class OpticalMediaCoreTest(unittest.TestCase):

    def test_scan_optical_drives_with_mock_sysfs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sysfs_root = os.path.join(tmpdir, "sys_block")
            dev_root = os.path.join(tmpdir, "dev")
            os.makedirs(sysfs_root)
            os.makedirs(dev_root)

            # Leeres Verzeichnis -> keine Laufwerke
            drives = scan_optical_drives(sysfs_root, dev_root)
            self.assertEqual(len(drives), 0)

            # Ein virtuelles sr0 anlegen
            sr0_sys = os.path.join(sysfs_root, "sr0", "device")
            os.makedirs(sr0_sys)
            with open(os.path.join(sr0_sys, "vendor"), "w") as f:
                f.write("ASUS    \n")
            with open(os.path.join(sr0_sys, "model"), "w") as f:
                f.write("BW-16D1HT   \n")

            # Nicht-optisches Gerät sda (wird ignoriert)
            os.makedirs(os.path.join(sysfs_root, "sda", "device"))

            drives = scan_optical_drives(sysfs_root, dev_root)
            self.assertEqual(len(drives), 1)
            self.assertEqual(drives[0].device_path, os.path.join(dev_root, "sr0"))
            self.assertEqual(drives[0].vendor, "ASUS")
            self.assertEqual(drives[0].model, "BW-16D1HT")

    def test_parse_cdparanoia_toc(self):
        tracks = parse_cdparanoia_toc(CDPARANOIA_STDERR_FIXTURE)
        self.assertEqual(len(tracks), 5)
        
        self.assertEqual(tracks[0].track_num, 1)
        self.assertEqual(tracks[0].start_sector, 150)
        self.assertEqual(tracks[0].end_sector, 150 + 19515 - 1)
        self.assertAlmostEqual(tracks[0].duration_sec, 19515 / 75.0, places=2)
        self.assertEqual(tracks[0].title, "Track 01")
        self.assertEqual(tracks[0].formatted_duration(), "04:20")

        self.assertEqual(tracks[4].track_num, 5)
        self.assertEqual(tracks[4].start_sector, 76965)
        self.assertEqual(tracks[4].end_sector, 76965 + 21000 - 1)
        self.assertAlmostEqual(tracks[4].duration_sec, 21000 / 75.0, places=2)

    def test_parse_cd_text(self):
        album, artist, track_dict = parse_cd_text(CD_INFO_FIXTURE)
        self.assertEqual(album, "Best of Linux Audio")
        self.assertEqual(artist, "Open Source Orchestra")
        self.assertEqual(len(track_dict), 5)
        self.assertEqual(track_dict[1]["title"], "Symphony No. 1 in C Major")
        self.assertEqual(track_dict[2]["title"], "Concerto for Kernel and Userspace")
        self.assertEqual(track_dict[3]["title"], "Suite for PipeWire and ALSA")
        self.assertEqual(track_dict[4]["title"], "Overture to Open Source")
        self.assertEqual(track_dict[5]["title"], "Finale: Return Code Zero")

    def test_parse_lsdvd_output(self):
        result = parse_lsdvd_output(LSDVD_OY_FIXTURE)
        self.assertIsNone(result.error)
        self.assertEqual(result.disc_type, DiscType.DVD_VIDEO)
        self.assertEqual(result.disc_label, "TEST_DVD_VIDEO")
        self.assertEqual(len(result.video_titles), 2)

        # Titel 1 (Hauptfilm: 5400s = 90 min)
        t1 = result.video_titles[0]
        self.assertEqual(t1.title_num, 1)
        self.assertEqual(t1.duration_sec, 5400.0)
        self.assertEqual(t1.formatted_duration(), "01:30:00")
        self.assertEqual(t1.chapter_count, 3)
        self.assertTrue(t1.is_main_feature)
        self.assertEqual(len(t1.audio_streams), 2)
        self.assertEqual(t1.audio_streams[0].language, "German")
        self.assertEqual(t1.audio_streams[0].codec, "ac3")
        self.assertEqual(t1.audio_streams[0].channels, 6)
        self.assertEqual(t1.audio_streams[1].language, "English")
        self.assertEqual(t1.audio_streams[1].codec, "dts")
        self.assertEqual(len(t1.subtitle_streams), 2)
        self.assertEqual(t1.subtitle_streams[0].language, "German")
        self.assertEqual(t1.subtitle_streams[1].language, "English")

        # Titel 2 (Bonus: 300s = 5 min)
        t2 = result.video_titles[1]
        self.assertEqual(t2.title_num, 2)
        self.assertEqual(t2.duration_sec, 300.0)
        self.assertEqual(t2.formatted_duration(), "05:00")
        self.assertFalse(t2.is_main_feature)

        self.assertEqual(result.main_title_idx, 0)
        self.assertEqual(result.total_duration_sec, 5700.0)

    def test_parse_bdinfo_output(self):
        result = parse_bdinfo_output(BD_INFO_FIXTURE)
        self.assertIsNone(result.error)
        self.assertEqual(result.disc_type, DiscType.BLURAY)
        self.assertEqual(result.disc_label, "BIG_BUCK_BUNNY_BD")
        self.assertEqual(len(result.video_titles), 2)

        # Playlist 800 (Hauptfilm)
        p1 = result.video_titles[0]
        self.assertEqual(p1.title_num, 800)
        self.assertEqual(p1.duration_sec, 634.0)  # 10*60 + 34
        self.assertEqual(p1.chapter_count, 5)
        self.assertEqual(p1.width, 1920)
        self.assertEqual(p1.height, 1080)
        self.assertEqual(p1.video_codec, "h264")
        self.assertTrue(p1.is_main_feature)
        self.assertEqual(len(p1.audio_streams), 2)
        self.assertEqual(p1.audio_streams[0].codec, "dts-hd")
        self.assertEqual(p1.audio_streams[0].language, "German")
        self.assertEqual(p1.audio_streams[1].codec, "ac3")
        self.assertEqual(p1.audio_streams[1].language, "English")
        self.assertEqual(len(p1.subtitle_streams), 2)

        # Playlist 801 (Kurzclip)
        p2 = result.video_titles[1]
        self.assertEqual(p2.title_num, 801)
        self.assertEqual(p2.duration_sec, 135.0)  # 2*60 + 15
        self.assertFalse(p2.is_main_feature)

    def test_detect_disc_type_folder_structures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. DVD Ordner mit VIDEO_TS
            dvd_dir = os.path.join(tmpdir, "MyDVD")
            os.makedirs(os.path.join(dvd_dir, "VIDEO_TS"))
            with open(os.path.join(dvd_dir, "VIDEO_TS", "VIDEO_TS.IFO"), "w") as f:
                f.write("mock")
            self.assertEqual(detect_disc_type(dvd_dir), DiscType.DVD_VIDEO)
            self.assertEqual(detect_disc_type(os.path.join(dvd_dir, "VIDEO_TS")), DiscType.DVD_VIDEO)

            # 2. Blu-ray Ordner mit BDMV
            bd_dir = os.path.join(tmpdir, "MyBD")
            os.makedirs(os.path.join(bd_dir, "BDMV"))
            with open(os.path.join(bd_dir, "BDMV", "index.bdmv"), "w") as f:
                f.write("mock")
            self.assertEqual(detect_disc_type(bd_dir), DiscType.BLURAY)
            self.assertEqual(detect_disc_type(os.path.join(bd_dir, "BDMV")), DiscType.BLURAY)

            # 3. Allgemeiner Ordner
            data_dir = os.path.join(tmpdir, "Data")
            os.makedirs(data_dir)
            with open(os.path.join(data_dir, "file.txt"), "w") as f:
                f.write("hello")
            self.assertEqual(detect_disc_type(data_dir), DiscType.DATA_DISC)

            # 4. Nicht existenter Pfad
            self.assertEqual(detect_disc_type("/nicht/vorhanden/123"), DiscType.UNKNOWN)

    def test_build_dvd_rip_args(self):
        # 1. Standard Transcoding mit H.264
        args, out = build_dvd_rip_args(
            source_path="/dev/sr0",
            title_num=3,
            chapter_start=2,
            chapter_end=5,
            audio_stream_idx=1,
            subtitle_stream_idx=None,
            output_file="/tmp/output.mp4",
            preset_settings={"video_codec": "libx264", "crf": "22", "audio_codec": "aac", "audio_bitrate": "192k"},
        )
        self.assertIn("-f", args)
        self.assertEqual(args[args.index("-f") + 1], "dvdvideo")
        self.assertIn("-title", args)
        self.assertEqual(args[args.index("-title") + 1], "3")
        self.assertIn("-chapter_start", args)
        self.assertEqual(args[args.index("-chapter_start") + 1], "2")
        self.assertIn("-chapter_end", args)
        self.assertEqual(args[args.index("-chapter_end") + 1], "5")
        self.assertIn("-i", args)
        self.assertEqual(args[args.index("-i") + 1], "/dev/sr0")
        self.assertIn("-map", args)
        self.assertIn("0:a:1", args)
        self.assertIn("-c:v", args)
        self.assertEqual(args[args.index("-c:v") + 1], "libx264")
        self.assertIn("-crf", args)
        self.assertEqual(args[args.index("-crf") + 1], "22")
        self.assertEqual(out, "/tmp/output.mp4")

        # 2. Untertitel gewählt -> erzwingt .mkv
        args_sub, out_sub = build_dvd_rip_args(
            source_path="/dev/sr0",
            title_num=1,
            subtitle_stream_idx=0,
            output_file="/tmp/movie.mp4",
        )
        self.assertTrue(out_sub.endswith(".mkv"))
        self.assertIn("-map", args_sub)
        self.assertIn("0:s:0", args_sub)
        self.assertIn("-c:s", args_sub)
        self.assertEqual(args_sub[args_sub.index("-c:s") + 1], "copy")

        # 3. Remux Modus -> -c:v copy -c:a copy
        args_remux, out_remux = build_dvd_rip_args(
            source_path="/tmp/VIDEO_TS",
            title_num=1,
            remux_mkv=True,
            output_file="/tmp/remux.mp4",
        )
        self.assertTrue(out_remux.endswith(".mkv"))
        self.assertIn("-c:v", args_remux)
        self.assertEqual(args_remux[args_remux.index("-c:v") + 1], "copy")
        self.assertIn("-c:a", args_remux)
        self.assertEqual(args_remux[args_remux.index("-c:a") + 1], "copy")

    def test_build_bluray_rip_args(self):
        # 1. Blu-ray Remuxing
        args, out = build_bluray_rip_args(
            source_path="/media/bluray",
            playlist_num=800,
            audio_stream_idx=0,
            subtitle_stream_idx=1,
            output_file="/tmp/bluray.mp4",
            remux_mkv=True,
        )
        self.assertIn("-playlist", args)
        self.assertEqual(args[args.index("-playlist") + 1], "800")
        self.assertIn("-i", args)
        self.assertEqual(args[args.index("-i") + 1], "bluray:/media/bluray")
        self.assertIn("0:a:0", args)
        self.assertIn("0:s:1", args)
        self.assertTrue(out.endswith(".mkv"))
        self.assertIn("-c:v", args)
        self.assertEqual(args[args.index("-c:v") + 1], "copy")

    def test_build_audio_cd_and_encode_commands(self):
        # cdparanoia
        cmd = build_audio_cd_rip_command("/dev/sr0", 3, "/tmp/track3.wav")
        self.assertEqual(cmd, ["cdparanoia", "-d", "/dev/sr0", "3-3", "/tmp/track3.wav"])

        # ffmpeg audio encode mit FLAC
        track = AudioTrackInfo(track_num=3, duration_sec=180.0, title="Song Title", artist="Great Artist", album="Awesome Album")
        args_flac = build_audio_encode_args("/tmp/track3.wav", "/tmp/track3.flac", codec="flac", track_info=track)
        self.assertIn("-c:a", args_flac)
        self.assertEqual(args_flac[args_flac.index("-c:a") + 1], "flac")
        self.assertIn("title=Song Title", args_flac)
        self.assertIn("artist=Great Artist", args_flac)
        self.assertIn("album=Awesome Album", args_flac)
        self.assertIn("track=3", args_flac)
        self.assertEqual(args_flac[-1], "/tmp/track3.flac")

        # ffmpeg audio encode mit MP3
        args_mp3 = build_audio_encode_args("/tmp/track3.wav", "/tmp/track3.mp3", codec="mp3", bitrate="320k", track_info=track)
        self.assertIn("-c:a", args_mp3)
        self.assertEqual(args_mp3[args_mp3.index("-c:a") + 1], "libmp3lame")
        self.assertIn("-b:a", args_mp3)
        self.assertEqual(args_mp3[args_mp3.index("-b:a") + 1], "320k")

    def test_build_iso_dump_command(self):
        cmd = build_iso_dump_command("/dev/sr0", "/tmp/backup.iso", block_count=123456)
        self.assertEqual(cmd, ["dd", "if=/dev/sr0", "of=/tmp/backup.iso", "bs=2048", "status=progress", "count=123456"])

    def test_encryption_and_capabilities_check(self):
        has_dvdcss, msg_dvd = check_dvd_encryption_support()
        self.assertTrue(has_dvdcss)

        caps = check_ffmpeg_optical_capabilities()
        self.assertTrue(caps.get("dvdvideo", False))
        self.assertTrue(caps.get("bluray", False))


class DiscRipperDialogAndWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        import sys
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_dialog_init_empty_drives(self):
        from disc_ripper_dialog import DiscRipperDialog
        with patch("optical_media.scan_optical_drives", return_value=[]):
            dialog = DiscRipperDialog()
            self.assertEqual(dialog.combo_drives.count(), 1)
            self.assertFalse(dialog.btn_eject.isEnabled())
            self.assertFalse(dialog.btn_action.isEnabled())
            dialog.close()

    def test_dialog_populate_and_selection_dvd(self):
        from disc_ripper_dialog import DiscRipperDialog
        mock_dvd = parse_lsdvd_output(LSDVD_OY_FIXTURE)

        with patch("optical_media.scan_optical_drives", return_value=[]), \
             patch("optical_media.inspect_source", return_value=mock_dvd):
            dialog = DiscRipperDialog(initial_source="/tmp/fake_dvd")
            self.assertEqual(dialog.table_titles.rowCount(), 2)
            self.assertTrue(dialog.btn_action.isEnabled())

            # Hauptfilm sollte standardmäßig markiert sein
            selected = dialog._get_selected_rows()
            self.assertEqual(selected, [0])

            # "Keine" drücken -> leer
            dialog._select_no_titles()
            self.assertEqual(dialog._get_selected_rows(), [])

            # "Alle auswählen" drücken -> [0, 1]
            dialog._select_all_titles()
            self.assertEqual(dialog._get_selected_rows(), [0, 1])

            # "Hauptfilm" drücken -> [0]
            dialog._select_main_feature()
            self.assertEqual(dialog._get_selected_rows(), [0])

            dialog.close()

    def test_dialog_queue_action_emission(self):
        from disc_ripper_dialog import DiscRipperDialog
        mock_dvd = parse_lsdvd_output(LSDVD_OY_FIXTURE)

        with patch("optical_media.scan_optical_drives", return_value=[]), \
             patch("optical_media.inspect_source", return_value=mock_dvd), \
             patch("disc_ripper_dialog.QMessageBox.information"):
            dialog = DiscRipperDialog(initial_source="/tmp/fake_dvd")
            dialog.edit_output_dir.setText("/tmp/my_videos")

            received_jobs = []
            dialog.jobs_queued.connect(lambda jobs: received_jobs.extend(jobs))

            dialog._on_action_clicked()
            self.assertEqual(len(received_jobs), 1)
            job = received_jobs[0]
            self.assertEqual(job["input_file"], "/tmp/fake_dvd")
            self.assertEqual(job["output_dir"], "/tmp/my_videos")
            self.assertEqual(job["settings"]["disc_type"], "dvd_video")
            self.assertEqual(job["settings"]["title_num"], 1)
            self.assertIn("-title", job["settings"]["input_args"])
            dialog.close()

    def test_audio_cd_worker_signals_and_flow(self):
        from disc_rip_worker import AudioCdRipWorker
        track1 = AudioTrackInfo(track_num=1, duration_sec=10.0, title="T1")
        worker = AudioCdRipWorker(
            device_path="/dev/sr0",
            tracks=[track1],
            output_dir="/tmp/test_cdda_out",
        )
        self.assertEqual(len(worker.tracks), 1)
        self.assertEqual(worker.codec, "flac")
        worker.stop()
        self.assertTrue(worker._is_cancelled)


if __name__ == "__main__":
    unittest.main()
