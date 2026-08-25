import unittest

from mouse_clicker.models import (
    MouseEvent,
    PlaybackConfig,
    ScreenGeometry,
    Template,
)


class MouseEventTest(unittest.TestCase):
    def test_button_event_round_trips_through_dict(self):
        event = MouseEvent(
            type="button",
            x=100,
            y=200,
            delay_ms=12.5,
            action="press",
            button="left",
        )

        restored = MouseEvent.from_dict(event.to_dict())

        self.assertEqual(restored, event)

    def test_rejects_unknown_event_type(self):
        with self.assertRaises(ValueError):
            MouseEvent(type="keyboard", x=1, y=2, delay_ms=0)

    def test_scroll_event_requires_a_delta(self):
        with self.assertRaises(ValueError):
            MouseEvent(type="scroll", x=1, y=2, delay_ms=0, dx=0, dy=0)


class TemplateTest(unittest.TestCase):
    def test_duration_is_sum_of_event_delays(self):
        template = Template(
            id="t1",
            name="demo",
            screen=ScreenGeometry(left=0, top=0, width=1920, height=1080),
            events=[
                MouseEvent(type="move", x=1, y=2, delay_ms=0),
                MouseEvent(type="move", x=3, y=4, delay_ms=25.5),
            ],
        )

        self.assertEqual(template.duration_ms, 25.5)

    def test_template_round_trips_through_dict(self):
        template = Template(
            id="t1",
            name="demo",
            screen=ScreenGeometry(left=-1920, top=0, width=3840, height=1080),
            events=[
                MouseEvent(
                    type="scroll",
                    x=50,
                    y=60,
                    delay_ms=10,
                    dx=0,
                    dy=-1,
                )
            ],
        )

        self.assertEqual(Template.from_dict(template.to_dict()), template)

    def test_template_rejects_blank_name(self):
        with self.assertRaises(ValueError):
            Template(
                id="t1",
                name=" ",
                screen=ScreenGeometry(left=0, top=0, width=1, height=1),
            )


class PlaybackConfigTest(unittest.TestCase):
    def test_fixed_loop_requires_positive_integer(self):
        self.assertEqual(PlaybackConfig.fixed(3).loops, 3)
        with self.assertRaises(ValueError):
            PlaybackConfig.fixed(0)
        with self.assertRaises(ValueError):
            PlaybackConfig.fixed(-1)
        with self.assertRaises(ValueError):
            PlaybackConfig.fixed(True)

    def test_infinite_loop_has_no_loop_limit(self):
        config = PlaybackConfig.infinite()

        self.assertTrue(config.is_infinite)
        self.assertIsNone(config.loops)


if __name__ == "__main__":
    unittest.main()
