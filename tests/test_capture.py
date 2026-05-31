from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from speedwagon_ai.capture import recorder_command


class RecorderCommandTests(unittest.TestCase):
    def test_configured_command_injects_output(self) -> None:
        command = recorder_command("rec -c 1 {output}", Path("audio/test.wav"))
        self.assertEqual(command, ["rec", "-c", "1", "audio/test.wav"])

    def test_auto_detects_rec(self) -> None:
        with patch("speedwagon_ai.capture.shutil.which", side_effect=lambda name: "/opt/homebrew/bin/rec" if name == "rec" else None):
            command = recorder_command("", Path("audio/test.wav"))
        self.assertEqual(command, ["/opt/homebrew/bin/rec", "-c", "1", "-r", "16000", "audio/test.wav"])

    def test_blackhole_profile_uses_coreaudio_device(self) -> None:
        with patch("speedwagon_ai.capture.shutil.which", side_effect=lambda name: "/opt/homebrew/bin/rec" if name == "rec" else None):
            command = recorder_command("", Path("audio/test.wav"), profile="blackhole", input_device="BlackHole 2ch")
        self.assertEqual(
            command,
            ["/opt/homebrew/bin/rec", "-t", "coreaudio", "BlackHole 2ch", "-c", "2", "-r", "48000", "audio/test.wav"],
        )

    def test_raises_clear_error_when_no_recorder_exists(self) -> None:
        with patch("speedwagon_ai.capture.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "brew install sox"):
                recorder_command("", Path("audio/test.wav"))


if __name__ == "__main__":
    unittest.main()
