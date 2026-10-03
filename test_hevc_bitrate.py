"""Regressionstest: HEVC muss die Zielbitrate respektieren.

Anlass (28.09.2026, Dominik): „Beim Codieren von H265/HEVC-Videos ist das
Ergebnis immer über 300 MB groß, egal wie klein ich die Bitrate einstelle —
es scheint nicht zu funktionieren."

Ursache, an der Quelle nachgemessen statt vermutet:

``presets.py``, Formatvorgabe ``"HEVC / H.265 (MP4)"``:

    "video_bitrate": "",  "crf": "23",   <- und KEIN "encoding_mode"

Das ist die **einzige** Videoformat-Vorgabe ohne ``encoding_mode``; H.264,
VP9, AV1, NVENC-HEVC setzen alle ausdrücklich ``"encoding_mode": "vbr"``.

Zwei Folgen, die sich zum gemeldeten Fehler addieren:

1. Beim Formatwechsel auf HEVC wird die vom Benutzer gewählte Bitrate
   ersetzt: aus ``video_bitrate='1M'`` wird ``video_bitrate=''``,
   ``crf='23'``. Der Regler springt auf 23. Die Bitrate ist weg.
2. Weil weder ``encoding_mode`` noch ``video_bitrate`` gesetzt sind, leitet
   ``get_ffmpeg_args()`` den Modus aus den Werten ab und landet bei
   ``crf='23'`` in der Qualitätssteuerung. Dort ist der Regler **invertiert**:
   ein *kleinerer* Wert bedeutet *bessere* Qualität und damit eine *größere*
   Datei. Wer "die Bitrate kleiner stellt", macht das Ergebnis größer.

Beides ist an der laufenden Oberfläche nachgewiesen (Hautpfenster- und
Dialogpfad), ebenso die Gegenprobe: ist ``-b:v`` einmal gesetzt, greift
libx265 die Vorgabe sauber um.

Geprüft wird an den echten Vorgaben, nicht an einer Nachbildung.
"""

import unittest

import presets


class HevcBitrateTest(unittest.TestCase):
    def test_hevc_preset_keeps_the_user_in_bitrate_control(self):
        # Nach dem Formatwechsel auf HEVC muss der Benutzer in der
        # Bitratensteuerung landen: Regler bedeutet Mbps, nicht Qualität.
        for label in ("HEVC / H.265 (MP4)", "HEVC (MP4, GPU/NVENC)"):
            with self.subTest(format=label):
                settings = presets.default_settings_for_format(label)
                self.assertIsNotNone(settings)
                args = presets.get_ffmpeg_args(
                    "in.mkv", "out.mp4", dict(settings, subtitles_enabled=False)
                )
                self.assertIn(
                    "-b:v", args,
                    f"{label} landet in der Qualitätssteuerung — der Bitratenregler "
                    f"wäre dann invertiert",
                )

    def test_hevc_preset_defaults_to_a_target_bitrate(self):
        # Ein leeres video_bitrate zusammen mit crf='23' ist die Ursache dafür,
        # dass der Regler zur Qualitätsstufe wird. Die Voreinstellung der
        # übrigen Videoformate (H.264 8M, VP9 4M, AV1 4M, NVENC-HEVC 8M) ist
        # eine Zielbitrate; HEVC war die einzige Ausnahme.
        settings = presets.default_settings_for_format("HEVC / H.265 (MP4)")
        self.assertTrue(
            str(settings.get("video_bitrate") or "").strip(),
            "HEVC hat keine Zielbitrate — der Regler wird damit zum CRF-Faktor "
            "und wirkt für den Benutzer genau nicht als Bitrate",
        )
        self.assertEqual(
            str(settings.get("crf") or "").strip(), "",
            "HEVC setzt bitte nicht zugleich eine Qualitätsstufe — sonst "
            "gewinnt die Ableitung und die Bitrate wird wieder ignoriert",
        )

    def test_every_video_format_preset_has_exactly_one_rate_control(self):
        # Die eigentliche Invariante. Kein Format muss `encoding_mode` setzen —
        # H.264, VP9, AV1, MOV und MKV tun es alle nicht und landen trotzdem
        # richtig, weil sie eine Zielbitrate UND kein crf haben. Die Ableitung
        # in get_ffmpeg_args() entscheidet dann auf vbr.
        #
        # Die Falle ist die andere Form: video_bitrate leer und crf gesetzt.
        # Dann kippt die Ableitung in die Qualitätssteuerung, der Regler wird
        # invertiert, und wer "die Bitrate kleiner stellt" macht die Datei
        # größer. Genau das war der gemeldete Fehler, und genau das muss hier
        # für kein Format mehr gelten.
        for label in presets.FORMAT_OPTIONS_VIDEO:
            settings = presets.default_settings_for_format(label)
            if not settings:
                continue
            codec = str(settings.get("video_codec", "")).lower()
            if codec in ("", "copy", "none"):
                continue
            with self.subTest(format=label):
                bitrate = str(settings.get("video_bitrate") or "").strip()
                crf = str(settings.get("crf") or "").strip()
                self.assertFalse(
                    bitrate == "" and crf != "",
                    f"{label}: leere Zielbitrate bei gesetzter Qualitätsstufe "
                    f"crf={crf!r} — der Regler wird damit zum Qualitätsfaktor",
                )
                self.assertTrue(
                    bitrate or crf,
                    f"{label}: weder Zielbitrate noch Qualitätsstufe — der "
                    f"Encoder fällt auf seinen eigenen Standard zurück",
                )

    def test_hevc_produces_a_real_bitrate_argument(self):
        # Ende zu Ende über den Argumentbauer: der Nutzer stellt 1 Mbps ein,
        # und genau das muss bei ffmpeg ankommen — kein -crf.
        settings = dict(
            presets.default_settings_for_format("HEVC / H.265 (MP4)") or {},
            video_bitrate="1M", crf="", encoding_mode="vbr",
            audio_codec="aac", audio_bitrate="192k", subtitles_enabled=False,
        )
        args = presets.get_ffmpeg_args("in.mkv", "out.mp4", settings)
        self.assertIn("-b:v", args, f"kein -b:v in: {args}")
        self.assertEqual(args[args.index("-b:v") + 1], "1M")
        self.assertNotIn("-crf", args,
                         "-crf und -b:v zusammen: die Qualitätsstufe gewinnt "
                         "und die Bitrate bleibt wirkungslos")


if __name__ == "__main__":
    unittest.main()
