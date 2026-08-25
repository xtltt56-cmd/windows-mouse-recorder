import threading
import time
import unittest

from mouse_clicker.models import MouseEvent, PlaybackConfig, ScreenGeometry, Template
from mouse_clicker.player import PlaybackEngine, PlaybackState


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class FakeInputBackend:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on
        self.down_event = threading.Event()
        self.move_event = threading.Event()

    def _record(self, name, *args):
        self.calls.append((name,) + args)
        if name == "move_to":
            self.move_event.set()
        if name == "button_down":
            self.down_event.set()
        if name == self.fail_on:
            raise RuntimeError("fake input failure")

    def move_to(self, x, y):
        self._record("move_to", x, y)

    def button_down(self, button):
        self._record("button_down", button)

    def button_up(self, button):
        self._record("button_up", button)

    def scroll(self, dx, dy):
        self._record("scroll", dx, dy)


def make_template(events):
    return Template(
        id="t1",
        name="demo",
        screen=ScreenGeometry(left=0, top=0, width=1920, height=1080),
        events=events,
    )


class PlaybackEngineTest(unittest.TestCase):
    def test_fixed_loop_replays_each_action_in_order(self):
        backend = FakeInputBackend()
        clock = FakeClock()
        template = make_template(
            [
                MouseEvent(type="move", x=10, y=20, delay_ms=0),
                MouseEvent(
                    type="button",
                    x=10,
                    y=20,
                    delay_ms=5,
                    action="press",
                    button="left",
                ),
                MouseEvent(
                    type="button",
                    x=10,
                    y=20,
                    delay_ms=2,
                    action="release",
                    button="left",
                ),
            ]
        )
        engine = PlaybackEngine(backend, clock=clock, sleeper=clock.sleep)

        engine.start(template, PlaybackConfig.fixed(2))
        engine.join(1)

        self.assertEqual(
            backend.calls,
            [
                ("move_to", 10, 20),
                ("button_down", "left"),
                ("button_up", "left"),
                ("move_to", 10, 20),
                ("button_down", "left"),
                ("button_up", "left"),
            ],
        )
        self.assertEqual(engine.state, PlaybackState.IDLE)

    def test_infinite_loop_stops_when_requested(self):
        backend = FakeInputBackend()
        clock = FakeClock()
        engine = None

        def stop_after_two_loops(index):
            if index == 2:
                engine.stop()

        engine = PlaybackEngine(
            backend,
            on_loop=stop_after_two_loops,
            clock=clock,
            sleeper=clock.sleep,
        )
        template = make_template(
            [MouseEvent(type="move", x=1, y=1, delay_ms=0)]
        )

        engine.start(template, PlaybackConfig.infinite())
        engine.join(1)

        self.assertFalse(engine.is_running)
        self.assertEqual(backend.calls.count(("move_to", 1, 1)), 2)

    def test_pause_prevents_next_event_until_resume(self):
        backend = FakeInputBackend()
        template = make_template(
            [
                MouseEvent(type="move", x=1, y=1, delay_ms=0),
                MouseEvent(
                    type="button",
                    x=1,
                    y=1,
                    delay_ms=200,
                    action="press",
                    button="left",
                ),
            ]
        )
        engine = PlaybackEngine(backend)

        engine.start(template, PlaybackConfig.fixed(1))
        self.assertTrue(backend.move_event.wait(1))
        engine.pause()
        time.sleep(0.08)

        self.assertEqual(backend.calls, [("move_to", 1, 1)])
        self.assertEqual(engine.state, PlaybackState.PAUSED)

        engine.resume()
        engine.join(1)

        self.assertIn(("button_down", "left"), backend.calls)
        self.assertEqual(backend.calls[-1], ("button_up", "left"))
        self.assertEqual(engine.state, PlaybackState.IDLE)

    def test_stop_releases_buttons_that_are_still_down(self):
        backend = FakeInputBackend()
        template = make_template(
            [
                MouseEvent(
                    type="button",
                    x=2,
                    y=2,
                    delay_ms=0,
                    action="press",
                    button="right",
                ),
                MouseEvent(type="move", x=3, y=3, delay_ms=500),
            ]
        )
        engine = PlaybackEngine(backend)

        engine.start(template, PlaybackConfig.fixed(1))
        self.assertTrue(backend.down_event.wait(1))
        engine.stop()
        engine.join(1)

        self.assertIn(("button_up", "right"), backend.calls)
        self.assertEqual(engine.state, PlaybackState.IDLE)

    def test_input_failure_reports_error_and_returns_to_idle(self):
        backend = FakeInputBackend(fail_on="button_down")
        errors = []
        states = []
        template = make_template(
            [
                MouseEvent(
                    type="button",
                    x=2,
                    y=2,
                    delay_ms=0,
                    action="press",
                    button="left",
                )
            ]
        )
        engine = PlaybackEngine(
            backend,
            on_state=states.append,
            on_error=errors.append,
        )

        engine.start(template, PlaybackConfig.fixed(1))
        engine.join(1)

        self.assertEqual(len(errors), 1)
        self.assertEqual(engine.state, PlaybackState.IDLE)
        self.assertIn(PlaybackState.PLAYING, states)
        self.assertEqual(states[-1], PlaybackState.IDLE)

    def test_empty_template_is_rejected(self):
        with self.assertRaises(ValueError):
            PlaybackEngine(FakeInputBackend()).start(
                make_template([]), PlaybackConfig.fixed(1)
            )


if __name__ == "__main__":
    unittest.main()
