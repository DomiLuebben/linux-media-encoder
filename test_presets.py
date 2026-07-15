import unittest

import presets


class FFmpegArgsTest(unittest.TestCase):
    def test_video_stream_copy_with_audio_aac_does_not_encode_video(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings.update({
            "video_codec": "copy",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
        })

        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

        self.assertIn("-c:v", args)
        self.assertEqual(args[args.index("-c:v") + 1], "copy")
        self.assertIn("-c:a", args)
        self.assertEqual(args[args.index("-c:a") + 1], "aac")
        self.assertNotIn("libx264", args)
        self.assertNotIn("-s", args)
        self.assertNotIn("-r", args)
        self.assertNotIn("-b:v", args)
        self.assertNotIn("-crf", args)
        self.assertNotIn("-pix_fmt", args)

    def test_ui_copy_alias_is_treated_as_stream_copy(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings.update({
            "video_codec": "Copy",
            "audio_codec": "Kopieren (Copy)",
        })

        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

        self.assertEqual(args[args.index("-c:v") + 1], "copy")
        self.assertEqual(args[args.index("-c:a") + 1], "copy")

    def test_audio_labels_map_to_ffmpeg_codecs(self):
        self.assertEqual(presets.audio_label_to_codec("AAC"), "aac")
        self.assertEqual(presets.audio_label_to_codec("Kopieren (Copy)"), "copy")
        self.assertEqual(presets.audio_label_to_codec("Kein Audio"), "none")
        self.assertEqual(presets.audio_label_to_codec("PCM 24-bit"), "pcm_s24le")

    def test_custom_mode_exposes_unfiltered_codec_choices(self):
        video_codecs = presets.get_video_codec_options("mp4", custom=True)
        audio_labels = presets.get_audio_codec_labels("mp4", custom=True)

        self.assertIn("copy", video_codecs)
        self.assertIn("libsvtav1", video_codecs)
        self.assertIn("libvpx-vp9", video_codecs)
        self.assertIn("Kopieren (Copy)", audio_labels)
        self.assertIn("Opus", audio_labels)
        self.assertIn("FLAC", audio_labels)

    def test_match_source_presets_keep_source_dimensions_and_fps(self):
        settings = dict(presets.PRESETS["Match Source - Adaptive High Bitrate (H.264)"])
        settings.update({
            "width": 1920,
            "height": 1080,
        })

        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

        self.assertNotIn("-s", args)
        # Preset ohne fps-Angabe -> Quell-Framerate bleibt unangetastet
        self.assertNotIn("-r", args)
        self.assertIn("-b:v", args)
        self.assertEqual(args[args.index("-b:v") + 1], "16M")

    def test_fps_is_independent_of_scale_mode(self):
        # Explizite Framerate gilt auch bei "Quellgröße beibehalten"
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings["scale_mode"] = "source"
        settings["fps"] = "30"
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertNotIn("-vf", args)
        self.assertEqual(args[args.index("-r") + 1], "30")

        # "Wie Quelle" bzw. leer -> kein -r
        settings["fps"] = presets.FPS_SOURCE_LABEL
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertNotIn("-r", args)
        settings["fps"] = ""
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertNotIn("-r", args)

    def test_video_scaling_keeps_aspect_ratio_by_default(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])

        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

        self.assertNotIn("-s", args)
        self.assertEqual(
            args[args.index("-vf") + 1],
            "scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2",
        )
        self.assertIn("-r", args)

    def test_video_scale_mode_stretch_forces_exact_size(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings["scale_mode"] = "stretch"

        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

        self.assertEqual(args[args.index("-vf") + 1], "scale=1920:1080")

    def test_video_stretch_makes_odd_yuv420p_dimensions_even(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings.update({"scale_mode": "stretch", "width": 1919, "height": 1079})

        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

        self.assertEqual(args[args.index("-vf") + 1], "scale=1918:1078")

    def test_video_scale_mode_source_skips_scaling(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings["scale_mode"] = "source"

        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

        self.assertNotIn("-vf", args)
        self.assertNotIn("-s", args)
        # fps ist von der Skalierung entkoppelt: das Preset nennt explizit 25
        self.assertEqual(args[args.index("-r") + 1], "25")

    def test_hard_subtitles_and_scaling_share_one_vf_chain(self):
        import tempfile
        import os
        fd, temp_path = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        try:
            settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
            settings.update({
                "subtitles_enabled": True,
                "temp_srt_path": temp_path,
                "subtitles_mode": "Hard-Untertitel (in Video einbrennen)",
            })

            args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

            vf_indices = [i for i, x in enumerate(args) if x == "-vf"]
            self.assertEqual(len(vf_indices), 1)
            vf = args[vf_indices[0] + 1]
            self.assertIn("scale=1920:1080", vf)
            self.assertIn("subtitles=", vf)
            self.assertLess(vf.index("scale="), vf.index("subtitles="))
        finally:
            os.remove(temp_path)

    def test_subtitle_filter_path_escapes_ffmpeg_special_chars(self):
        self.assertEqual(
            presets.build_subtitles_filter("/tmp/lme test's co:lon,br[1].srt"),
            r"subtitles=filename=/tmp/lme\ test\\\'s\ co\\:lon\,br\[1\].srt",
        )

    def test_preset_dropdown_has_no_external_tool_branding(self):
        names = presets.get_preset_dropdown_options()
        forbidden = ("Hand" + "Brake", "Hand" + "brake")

        self.assertFalse(any(any(term in name for term in forbidden) for name in names))
        self.assertIn("Schnell 1080p30 (MP4 H.264)", names)
        self.assertIn("Match Source - Adaptive High Bitrate (H.264)", names)

    def test_ffmpeg_args_with_soft_subtitles_mp4(self):
        import tempfile
        import os
        fd, temp_path = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        try:
            settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
            settings.update({
                "subtitles_enabled": True,
                "temp_srt_path": temp_path,
                "subtitles_mode": "Soft-Untertitel (in Container einbetten)",
            })

            args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

            self.assertIn("-i", args)
            i_indices = [i for i, x in enumerate(args) if x == "-i"]
            self.assertEqual(len(i_indices), 2)
            self.assertEqual(args[i_indices[1] + 1], temp_path)

            self.assertIn("-map", args)
            # 0:V statt 0:v: Cover-Art (attached_pic) darf nicht mitgemappt werden
            self.assertIn("0:V?", args)
            self.assertIn("0:a:0?", args)
            self.assertIn("1:s?", args)

            self.assertIn("-c:s", args)
            self.assertEqual(args[args.index("-c:s") + 1], "mov_text")
        finally:
            os.remove(temp_path)

    def test_ffmpeg_args_with_soft_subtitles_mkv(self):
        import tempfile
        import os
        fd, temp_path = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        try:
            settings = dict(presets.PRESETS["MKV (H.264 / FLAC) - Verlustfreies Audio"])
            settings.update({
                "subtitles_enabled": True,
                "temp_srt_path": temp_path,
                "subtitles_mode": "Soft-Untertitel (in Container einbetten)",
            })

            args = presets.get_ffmpeg_args("input.mp4", "output.mkv", settings)

            self.assertIn("-c:s", args)
            self.assertEqual(args[args.index("-c:s") + 1], "subrip")
        finally:
            os.remove(temp_path)

    def test_ffmpeg_args_with_hard_subtitles_burn_in(self):
        import tempfile
        import os
        fd, temp_path = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        try:
            settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
            settings.update({
                "subtitles_enabled": True,
                "video_codec": "copy",
                "temp_srt_path": temp_path,
                "subtitles_mode": "Hard-Untertitel (in Video einbrennen)",
            })

            args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

            self.assertIn("-c:v", args)
            self.assertEqual(args[args.index("-c:v") + 1], "libx264")

            self.assertIn("-vf", args)
            self.assertTrue(any("subtitles=" in arg for arg in args))
        finally:
            os.remove(temp_path)

    def test_soft_subtitles_are_not_muxed_into_audio_only_container(self):
        import tempfile
        import os
        fd, temp_path = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        try:
            settings = dict(presets.PRESETS["MP3 (Nur Audio) - High Quality 320k"])
            settings.update({
                "subtitles_enabled": True,
                "temp_srt_path": temp_path,
                "subtitles_mode": "Soft-Untertitel (in Container einbetten)",
            })

            args = presets.get_ffmpeg_args("input.mp4", "output.mp3", settings)

            self.assertEqual([args[i + 1] for i, x in enumerate(args) if x == "-i"], ["input.mp4"])
            self.assertNotIn(temp_path, args)
            self.assertNotIn("1:s?", args)
            self.assertNotIn("-c:s", args)
            self.assertIn("-vn", args)
            self.assertEqual(args[args.index("-c:a") + 1], "libmp3lame")
        finally:
            os.remove(temp_path)

    def test_webm_hard_subtitles_copy_falls_back_to_webm_compatible_codec(self):
        import tempfile
        import os
        fd, temp_path = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        try:
            settings = {
                "container": "webm",
                "video_codec": "copy",
                "audio_codec": "none",
                "subtitles_enabled": True,
                "temp_srt_path": temp_path,
                "subtitles_mode": "Hard-Untertitel (in Video einbrennen)",
                "scale_mode": "source",
            }

            args = presets.get_ffmpeg_args("input.mp4", "output.webm", settings)

            self.assertEqual(args[args.index("-c:v") + 1], "libvpx-vp9")
            self.assertNotIn("libx264", args)
            self.assertEqual(args[args.index("-crf") + 1], "23")
            self.assertEqual(args[args.index("-b:v") + 1], "0")
            self.assertIn("-vf", args)
            self.assertIn("subtitles=filename=", args[args.index("-vf") + 1])
        finally:
            os.remove(temp_path)

    def test_subtitle_path_is_ignored_when_option_disabled(self):
        import tempfile
        import os
        fd, temp_path = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        try:
            settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
            settings.update({
                "subtitles_enabled": False,
                "temp_srt_path": temp_path,
                "subtitles_mode": "Soft-Untertitel (in Container einbetten)",
            })

            args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

            self.assertNotIn(temp_path, args)
            self.assertNotIn("-c:s", args)
        finally:
            os.remove(temp_path)

    def test_generated_subtitle_path_preferred_over_manual_path(self):
        import tempfile
        import os
        fd1, generated_path = tempfile.mkstemp(suffix=".srt")
        fd2, manual_path = tempfile.mkstemp(suffix=".srt")
        os.close(fd1)
        os.close(fd2)
        try:
            settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
            settings.update({
                "subtitles_enabled": True,
                "temp_srt_path": generated_path,
                "subtitles_file_path": manual_path,
                "subtitles_mode": "Soft-Untertitel (in Container einbetten)",
            })

            args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

            i_indices = [i for i, x in enumerate(args) if x == "-i"]
            self.assertEqual(args[i_indices[1] + 1], generated_path)
        finally:
            os.remove(generated_path)
            os.remove(manual_path)


class TrimArgsTest(unittest.TestCase):
    def test_trim_start_and_end_become_output_options(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings["trim_start"] = 5.0
        settings["trim_end"] = 80.5

        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)

        # Nach dem Input (Output-Option, frame-genau, Untertitel-sicher)
        self.assertGreater(args.index("-ss"), args.index("-i"))
        self.assertEqual(args[args.index("-ss") + 1], "5.000")
        self.assertEqual(args[args.index("-to") + 1], "80.500")

    def test_trim_end_only(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings["trim_end"] = 30
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertNotIn("-ss", args)
        self.assertEqual(args[args.index("-to") + 1], "30.000")

    def test_invalid_trim_is_ignored(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings["trim_start"] = "kaputt"
        settings["trim_end"] = -3
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertNotIn("-ss", args)
        self.assertNotIn("-to", args)

    def test_trim_end_before_start_is_dropped(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings["trim_start"] = 60
        settings["trim_end"] = 10
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertIn("-ss", args)
        self.assertNotIn("-to", args)

    def test_parse_seconds(self):
        self.assertEqual(presets.parse_seconds("12.5"), 12.5)
        self.assertEqual(presets.parse_seconds(0), 0.0)
        self.assertIsNone(presets.parse_seconds(""))
        self.assertIsNone(presets.parse_seconds(None))
        self.assertIsNone(presets.parse_seconds("abc"))
        self.assertIsNone(presets.parse_seconds(-1))


class NvencArgsTest(unittest.TestCase):
    def _settings(self, codec, **extra):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings["video_codec"] = codec
        settings.update(extra)
        return settings

    def test_nvenc_crf_maps_to_cq(self):
        settings = self._settings("h264_nvenc", encoding_mode="crf", crf="23", video_bitrate="")
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertNotIn("-crf", args)
        self.assertEqual(args[args.index("-cq") + 1], "23")
        self.assertEqual(args[args.index("-rc") + 1], "vbr")
        self.assertEqual(args[args.index("-b:v") + 1], "0")
        self.assertIn("-pix_fmt", args)

    def test_hevc_nvenc_rejects_x264_profiles(self):
        settings = self._settings("hevc_nvenc", profile="High")
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertNotIn("-profile:v", args)
        settings = self._settings("hevc_nvenc", profile="Main")
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertEqual(args[args.index("-profile:v") + 1], "main")

    def test_h264_nvenc_bitrate_mode(self):
        settings = self._settings("h264_nvenc")
        args = presets.get_ffmpeg_args("input.mp4", "output.mp4", settings)
        self.assertEqual(args[args.index("-b:v") + 1], "8M")
        self.assertNotIn("-cq", args)

    def test_nvenc_format_mapping_roundtrip(self):
        self.assertEqual(presets.container_from_format_text("H.264 (MP4, GPU/NVENC)"), "mp4")
        self.assertEqual(presets.container_from_format_text("AV1 (MP4, GPU/NVENC)"), "mp4")
        defaults = presets.default_settings_for_format("HEVC (MP4, GPU/NVENC)")
        self.assertEqual(defaults["video_codec"], "hevc_nvenc")
        self.assertEqual(
            presets.format_option_for_settings(defaults), "HEVC (MP4, GPU/NVENC)"
        )


class AudioFormatsTest(unittest.TestCase):
    def test_wav_and_ogg_in_format_options(self):
        options = presets.get_format_options(False)
        self.assertIn("WAV (Nur Audio)", options)
        self.assertIn("OGG (Nur Audio)", options)

    def test_wav_defaults_use_pcm_without_bitrate(self):
        settings = presets.default_settings_for_format("WAV (Nur Audio)")
        self.assertEqual(settings["container"], "wav")
        self.assertEqual(settings["audio_codec"], "pcm_s16le")
        args = presets.get_ffmpeg_args("input.mp4", "output.wav", settings)
        self.assertIn("-vn", args)
        self.assertEqual(args[args.index("-c:a") + 1], "pcm_s16le")
        self.assertNotIn("-b:a", args)  # PCM ist verlustfrei, keine Bitrate

    def test_ogg_defaults_use_opus(self):
        settings = presets.default_settings_for_format("OGG (Nur Audio)")
        args = presets.get_ffmpeg_args("input.mp4", "output.ogg", settings)
        self.assertEqual(args[args.index("-c:a") + 1], "libopus")
        self.assertEqual(presets.container_from_format_text("WAV (Nur Audio)"), "wav")
        self.assertEqual(presets.container_from_format_text("OGG (Nur Audio)"), "ogg")


class PresetLabelTest(unittest.TestCase):
    def test_stored_quick_preset_label_wins(self):
        settings = dict(presets.PRESETS["MP4 (H.264 / AAC) - Standard 1080p"])
        settings["video_bitrate"] = "16M"  # kein exakter Preset-Treffer mehr
        settings["preset_label"] = "YouTube 1080p HD"
        self.assertEqual(presets.preset_label(settings), "YouTube 1080p HD")

    def test_custom_mode_overrides_stored_label(self):
        settings = {"custom_mode": True, "preset_label": "YouTube 1080p HD"}
        self.assertEqual(presets.preset_label(settings), "Benutzerdefiniert")

    def test_format_option_for_settings_simple_containers(self):
        self.assertEqual(
            presets.format_option_for_settings({"container": "wav", "video_codec": "none"}),
            "WAV (Nur Audio)",
        )
        self.assertEqual(
            presets.format_option_for_settings({"container": "mp4", "video_codec": "libx265"}),
            "HEVC / H.265 (MP4)",
        )


class UiHelperTest(unittest.TestCase):
    def test_bitrate_to_mbps_parses_ffmpeg_units(self):
        self.assertEqual(presets.bitrate_to_mbps("8M"), 8.0)
        self.assertEqual(presets.bitrate_to_mbps("8000k"), 8.0)
        self.assertEqual(presets.bitrate_to_mbps("8000000"), 8.0)
        self.assertEqual(presets.bitrate_to_mbps("8"), 8.0)
        self.assertIsNone(presets.bitrate_to_mbps("Source / CRF"))

    def test_sub_100k_bitrate_formats_without_rounding_to_zero(self):
        self.assertEqual(presets.format_mbps(0.033), "33k")
        self.assertEqual(presets.bitrate_to_mbps("33k"), 0.033)

    def test_quick_presets_are_complete_container_settings(self):
        yt = presets.quick_preset_settings("YouTube 1080p HD")
        self.assertEqual(yt["container"], "mp4")
        self.assertEqual(yt["video_codec"], "libx264")
        self.assertEqual(yt["audio_codec"], "aac")
        self.assertEqual(yt["encoding_mode"], "vbr")

        efficient = presets.quick_preset_settings("Hocheffizient (CRF 23)")
        self.assertEqual(efficient["video_codec"], "libx265")
        self.assertEqual(efficient["encoding_mode"], "crf")


if __name__ == "__main__":
    unittest.main()
