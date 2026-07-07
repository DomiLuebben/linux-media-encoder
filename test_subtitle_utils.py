import unittest

import subtitle_utils


class SubtitleUtilsTest(unittest.TestCase):
    def test_merge_translation_preserves_source_indices_and_timecodes(self):
        source = """1
00:00:01,000 --> 00:00:03,500
Hallo Welt.

2
00:00:04,000 --> 00:00:06,000
Wie geht es dir?
"""
        translated = """1
00:10:01,000 --> 00:10:03,500
Hello world.

2
00:10:04,000 --> 00:10:06,000
How are you?
"""

        merged = subtitle_utils.merge_translated_text_with_source_timecodes(source, translated)

        self.assertIn("00:00:01,000 --> 00:00:03,500", merged)
        self.assertIn("00:00:04,000 --> 00:00:06,000", merged)
        self.assertNotIn("00:10:01,000", merged)
        self.assertIn("Hello world.", merged)
        self.assertIn("How are you?", merged)

    def test_clean_markdown_fence_and_normalize_srt(self):
        raw = """```srt
1
00:00:00,000 --> 00:00:01,000
Test.
```"""

        self.assertEqual(
            subtitle_utils.normalize_srt(raw),
            "1\n00:00:00,000 --> 00:00:01,000\nTest.\n",
        )

    def test_translation_prompt_allows_neighbor_rebalancing_without_timecode_changes(self):
        prompt = subtitle_utils.build_translation_prompt(
            "1\n00:00:00,000 --> 00:00:01,000\nHallo.\n",
            "English (US)",
        )

        self.assertIn("Timecode-Zeile exakt bei", prompt)
        self.assertIn("direkt vorherigen oder direkt folgenden Block", prompt)
        self.assertIn("niemals Timecodes anpassen", prompt)


if __name__ == "__main__":
    unittest.main()
