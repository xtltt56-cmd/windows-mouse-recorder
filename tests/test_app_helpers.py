import unittest

from mouse_clicker.app import (
    STATE_PLAYBACK_COUNTDOWN,
    can_start_playback,
    can_start_recording,
    parse_loop_input,
    playback_countdown_message,
    recording_finished_message,
)


class AppHelperTest(unittest.TestCase):
    def test_recording_can_start_only_when_idle(self):
        self.assertTrue(can_start_recording("idle"))
        self.assertFalse(can_start_recording("countdown"))
        self.assertFalse(can_start_recording("recording"))
        self.assertFalse(can_start_recording("playing"))
        self.assertFalse(can_start_recording(STATE_PLAYBACK_COUNTDOWN))

    def test_playback_requires_idle_state_and_events(self):
        self.assertTrue(can_start_playback("idle", 1))
        self.assertFalse(can_start_playback("idle", 0))
        self.assertFalse(can_start_playback("recording", 1))
        self.assertFalse(can_start_playback("paused", 1))
        self.assertFalse(can_start_playback(STATE_PLAYBACK_COUNTDOWN, 1))

    def test_playback_countdown_message_shows_remaining_seconds(self):
        self.assertEqual(
            playback_countdown_message(5), "回放将在 5 秒后开始"
        )
        self.assertEqual(
            playback_countdown_message(1), "回放将在 1 秒后开始"
        )

    def test_parse_loop_input_supports_fixed_and_infinite(self):
        self.assertEqual(parse_loop_input(" 3 ", False).loops, 3)
        self.assertTrue(parse_loop_input("ignored", True).is_infinite)

    def test_parse_loop_input_rejects_invalid_fixed_values(self):
        for value in ("", "0", "-1", "1.5", "abc"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_loop_input(value, False)

    def test_recording_finished_message_mentions_tail_trim_and_count(self):
        self.assertIn("已排除末尾 3 秒", recording_finished_message(0))
        self.assertIn("保存 7 个事件", recording_finished_message(7))


if __name__ == "__main__":
    unittest.main()
