from __future__ import annotations

import unittest
from datetime import date

from speedwagon_ai.voice_tasks import clean_task_transcript, parse_voice_task_text


class VoiceTaskTests(unittest.TestCase):
    def test_clean_task_transcript_removes_common_prefixes(self) -> None:
        self.assertEqual(clean_task_transcript("Remind me to send notes"), "send notes")
        self.assertEqual(clean_task_transcript("add task review the launch doc"), "review the launch doc")

    def test_clean_task_transcript_ignores_blank_audio_tokens(self) -> None:
        self.assertEqual(clean_task_transcript("[BLANK_AUDIO]"), "")

    def test_parse_voice_task_text_extracts_trailing_due_date(self) -> None:
        parsed = parse_voice_task_text("send app update to Megan by June 8")
        self.assertEqual(parsed["text"], "send app update to Megan")
        self.assertEqual(parsed["due_date"], date(date.today().year, 6, 8).isoformat())

        iso = parse_voice_task_text("email project status due 2026-06-10")
        self.assertEqual(iso["text"], "email project status")
        self.assertEqual(iso["due_date"], "2026-06-10")

    def test_parse_voice_task_text_keeps_non_date_by_phrase(self) -> None:
        parsed = parse_voice_task_text("send notes by email")
        self.assertEqual(parsed["text"], "send notes by email")
        self.assertIsNone(parsed["due_date"])


if __name__ == "__main__":
    unittest.main()
