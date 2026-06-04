from __future__ import annotations

import unittest

from speedwagon_ai.voice_tasks import clean_task_transcript


class VoiceTaskTests(unittest.TestCase):
    def test_clean_task_transcript_removes_common_prefixes(self) -> None:
        self.assertEqual(clean_task_transcript("Remind me to send notes"), "send notes")
        self.assertEqual(clean_task_transcript("add task review the launch doc"), "review the launch doc")

    def test_clean_task_transcript_ignores_blank_audio_tokens(self) -> None:
        self.assertEqual(clean_task_transcript("[BLANK_AUDIO]"), "")


if __name__ == "__main__":
    unittest.main()
