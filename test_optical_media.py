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
    parse_bdinfo_header,
    list_bluray_playlists,
    find_bdmv_root,
    build_dvd_rip_args,
    build_bluray_rip_args,
    build_audio_cd_rip_command,
    build_audio_encode_args,
    build_iso_dump_command,
    get_optical_media_size,
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

# Echtes Ausgabeformat von 'lsdvd -Oy': width/height/fps/aspect/format liegen
# FLACH auf dem Track, es gibt kein verschachteltes 'video'-Woerterbuch, und das
# Seitenverhaeltnis wird mit Schraegstrich geschrieben ('16/9').
LSDVD_OY_FIXTURE = """lsdvd = {
 'device' : '/dev/sr0',
 'title' : 'TEST_DVD_VIDEO',
 'vmg_id' : 'DVDVIDEO-AMG',
 'provider_id' : '',
 'track' : [
   { 'ix' : 1, 'length' : 5400.000, 'vts' : 1, 'ttn' : 1, 'fps' : 29.97,
     'format' : 'NTSC', 'aspect' : '16/9', 'width' : 720, 'height' : 480,
     'df' : 'Letterbox', 'angles' : 1,
     'audio' : [
       { 'ix' : 1, 'langcode' : 'de', 'language' : 'German', 'format' : 'ac3', 'frequency' : 48000, 'channels' : 6, 'streamid' : '0x80' },
       { 'ix' : 2, 'langcode' : 'en', 'language' : 'English', 'format' : 'dts', 'frequency' : 48000, 'channels' : 6, 'streamid' : '0x88' }
     ],
     'chapter' : [
       { 'ix' : 1, 'length' : 1800.000, 'startcell' : 1 },
       { 'ix' : 2, 'length' : 1800.000, 'startcell' : 2 },
       { 'ix' : 3, 'length' : 1800.000, 'startcell' : 3 }
     ],
     'subp' : [
       { 'ix' : 1, 'langcode' : 'de', 'language' : 'German', 'streamid' : '0x20' },
       { 'ix' : 2, 'langcode' : 'en', 'language' : 'English', 'streamid' : '0x21' }
     ],
   },
   { 'ix' : 2, 'length' : 300.000, 'vts' : 2, 'ttn' : 1, 'fps' : 29.97,
     'format' : 'NTSC', 'aspect' : '4/3', 'width' : 720, 'height' : 480,
     'df' : 'Pan and Scan', 'angles' : 1,
     'audio' : [
       { 'ix' : 1, 'langcode' : 'de', 'language' : 'German', 'format' : 'ac3', 'frequency' : 48000, 'channels' : 2, 'streamid' : '0x80' }
     ],
     'chapter' : [
       { 'ix' : 1, 'length' : 300.000, 'startcell' : 1 }
     ],
     'subp' : [],
   }
 ],
 'longest_track' : 1,
}"""

# 'bd_info' gibt KEINE Playlist-Liste aus. Das hier ist die tatsaechliche
# Kopfzeilen-Ausgabe (abgeleitet aus den Formatzeichenketten des Programms).
BD_INFO_HEADER_FIXTURE = """Using libbluray version 1.4.1
Volume Identifier   : BIG_BUCK_BUNNY_BD
BluRay detected     : yes
First Play supported: yes
Top menu supported  : yes
HDMV titles         : 4
BD-J titles         : 0
UNSUPPORTED titles  : 0
AACS detected       : yes
libaacs detected    : no
AACS handled        : no
BD+ detected        : no
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

        # Wächter gegen einen stillen Rückfall auf die Vorgabewerte: lsdvd legt
        # width/height/fps/aspect FLACH auf dem Track ab. Wer nur unter 'video'
        # nachsieht, bekommt hier 720x576 @ 25.0 und '16:9' statt der echten
        # NTSC-Werte — ohne dass irgendetwas fehlschlägt.
        self.assertEqual((t1.width, t1.height), (720, 480))
        self.assertAlmostEqual(t1.fps, 29.97, places=2)
        self.assertEqual(t1.aspect_ratio, "16:9")
        self.assertEqual(t1.video_codec, "mpeg2video")

        # Titel 2 (Bonus: 300s = 5 min)
        t2 = result.video_titles[1]
        self.assertEqual(t2.title_num, 2)
        self.assertEqual(t2.duration_sec, 300.0)
        self.assertEqual(t2.formatted_duration(), "05:00")
        self.assertFalse(t2.is_main_feature)
        # '4/3' aus lsdvd wird auf die LME-Schreibweise '4:3' normalisiert.
        self.assertEqual(t2.aspect_ratio, "4:3")

        self.assertEqual(result.main_title_idx, 0)
        self.assertEqual(result.total_duration_sec, 5700.0)

    def test_parse_bdinfo_header_reads_volume_id_and_aacs_state(self):
        header = parse_bdinfo_header(BD_INFO_HEADER_FIXTURE)
        self.assertEqual(header["volume_id"], "BIG_BUCK_BUNNY_BD")
        self.assertTrue(header["aacs_detected"])
        self.assertFalse(header["aacs_handled"])

    def test_parse_bdinfo_header_defaults_on_empty_output(self):
        header = parse_bdinfo_header("")
        self.assertEqual(header["volume_id"], "")
        self.assertFalse(header["aacs_detected"])
        self.assertTrue(header["aacs_handled"])

    def test_bluray_playlists_are_read_from_mpls_filenames(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bd_dir = os.path.join(tmpdir, "MyBluray")
            playlist_dir = os.path.join(bd_dir, "BDMV", "PLAYLIST")
            os.makedirs(playlist_dir)
            for name in ("00800.mpls", "00801.MPLS", "00002.mpls", "liesmich.txt"):
                with open(os.path.join(playlist_dir, name), "w") as handle:
                    handle.write("mock")

            self.assertEqual(find_bdmv_root(bd_dir), bd_dir)
            self.assertEqual(find_bdmv_root(os.path.join(bd_dir, "BDMV")), bd_dir)
            self.assertEqual(list_bluray_playlists(bd_dir), [2, 800, 801])
            self.assertEqual(list_bluray_playlists(os.path.join(bd_dir, "BDMV")), [2, 800, 801])

    def test_bluray_playlists_empty_without_bdmv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertIsNone(find_bdmv_root(tmpdir))
            self.assertEqual(list_bluray_playlists(tmpdir), [])
            self.assertEqual(list_bluray_playlists("/dev/sr0"), [])

    def test_iso_without_video_signature_is_data_disc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Daten-Abbild ohne VIDEO_TS/BDMV-Kennzeichen darf NICHT als
            # DVD-Video durchgehen, sonst landet jede beliebige ISO im
            # DVD-Titelparser.
            data_iso = os.path.join(tmpdir, "spiel.iso")
            with open(data_iso, "wb") as handle:
                handle.write(b"\x00" * 40960)
            self.assertEqual(detect_disc_type(data_iso), DiscType.DATA_DISC)

            dvd_iso = os.path.join(tmpdir, "film.iso")
            with open(dvd_iso, "wb") as handle:
                handle.write(b"\x00" * 32768 + b"VIDEO_TS" + b"\x00" * 1024)
            self.assertEqual(detect_disc_type(dvd_iso), DiscType.DVD_VIDEO)

            bd_iso = os.path.join(tmpdir, "bluray.iso")
            with open(bd_iso, "wb") as handle:
                handle.write(b"\x00" * 32768 + b"index.bdmv" + b"\x00" * 1024)
            self.assertEqual(detect_disc_type(bd_iso), DiscType.BLURAY)

    def test_get_optical_media_size_reads_iso9660_descriptor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image = os.path.join(tmpdir, "medium.iso")
            # Primary Volume Descriptor an Sektor 16: Kennung 'CD001',
            # Volumenraum (Blockzahl) an Offset 80, Blockgröße an Offset 128.
            pvd = bytearray(2048)
            pvd[0] = 1
            pvd[1:6] = b"CD001"
            pvd[80:84] = (1000).to_bytes(4, "little")
            pvd[128:130] = (2048).to_bytes(2, "little")
            with open(image, "wb") as handle:
                handle.write(b"\x00" * (16 * 2048))
                handle.write(bytes(pvd))

            # blockdev kennt eine gewöhnliche Datei nicht -> Rückfall auf den PVD
            self.assertEqual(get_optical_media_size(image), 1000 * 2048)

            leer = os.path.join(tmpdir, "leer.iso")
            with open(leer, "wb") as handle:
                handle.write(b"\x00" * 4096)
            self.assertEqual(get_optical_media_size(leer), 0)

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
