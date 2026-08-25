import unittest

from mouse_clicker.models import MouseEvent
from mouse_clicker.recorder import (
    GlobalMouseRecorder,
    RecordingResult,
    RecordingSession,
    trim_recorded_tail,
)


class MutableClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class FakeListener:
    def __init__(self, **callbacks):
        self.callbacks = callbacks
        self.started = False
        self.stopped = False
        self.joined = False

    def start(self):
        self.started = True
        return self

    def stop(self):
        self.stopped = True

    def join(self):
        self.joined = True


class RecordingSessionTest(unittest.TestCase):
    def test_records_total_duration_and_event_offsets_from_start(self):
        clock = MutableClock(10.0)
        session = RecordingSession(clock=clock)

        session.start()
        clock.value = 10.500
        session.on_move(100, 200)
        clock.value = 18.000
        result = session.stop()

        self.assertEqual(result.duration_ms, 8000.0)
        self.assertEqual(result.event_times_ms, [500.0])
        self.assertEqual(len(result.events), 1)

    def test_records_event_delays_from_monotonic_clock(self):
        clock = MutableClock(10.0)
        session = RecordingSession(clock=clock)

        session.start()
        clock.value = 10.125
        session.on_move(100, 200)
        clock.value = 10.250
        session.on_click(100, 200, "left", True)
        clock.value = 10.300
        session.on_click(100, 200, "left", False)
        events = session.stop().events

        self.assertEqual([event.delay_ms for event in events], [0.0, 125.0, 50.0])
        self.assertEqual(events[1].action, "press")
        self.assertEqual(events[1].button, "left")

    def test_records_scroll_and_button_names(self):
        clock = MutableClock()
        session = RecordingSession(clock=clock)

        session.start()
        session.on_click(1, 2, "right", True)
        session.on_scroll(1, 2, 0, -1)
        events = session.stop().events

        self.assertEqual(events[0].button, "right")
        self.assertEqual(events[1].type, "scroll")
        self.assertEqual((events[1].dx, events[1].dy), (0, -1))

    def test_ignores_events_inside_excluded_region_without_changing_timing(self):
        clock = MutableClock(1.0)
        session = RecordingSession(
            clock=clock,
            excluded_region=lambda x, y: 0 <= x <= 100 and 0 <= y <= 100,
        )

        session.start()
        session.on_move(50, 50)
        clock.value = 2.0
        session.on_move(500, 500)
        events = session.stop().events

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].delay_ms, 0.0)

    def test_does_not_record_when_inactive_or_after_stop(self):
        clock = MutableClock()
        session = RecordingSession(clock=clock)

        session.on_move(1, 1)
        session.start()
        session.on_move(2, 2)
        session.stop()
        session.on_move(3, 3)

        self.assertEqual(
            [(event.x, event.y) for event in session.stop().events], [(2, 2)]
        )

    def test_excluded_events_do_not_change_total_duration(self):
        clock = MutableClock(1.0)
        session = RecordingSession(
            clock=clock,
            excluded_region=lambda x, y: x < 100,
        )

        session.start()
        clock.value = 2.0
        session.on_move(50, 50)
        clock.value = 5.0
        result = session.stop()

        self.assertEqual(result.events, [])
        self.assertEqual(result.event_times_ms, [])
        self.assertEqual(result.duration_ms, 4000.0)


class GlobalMouseRecorderTest(unittest.TestCase):
    def test_listener_lifecycle_forwards_callbacks_and_joins(self):
        clock = MutableClock()
        created = []

        def factory(**callbacks):
            listener = FakeListener(**callbacks)
            created.append(listener)
            return listener

        recorder = GlobalMouseRecorder(clock=clock, listener_factory=factory)
        recorder.start()
        created[0].callbacks["on_move"](10, 20)
        result = recorder.stop()

        self.assertTrue(created[0].started)
        self.assertTrue(created[0].stopped)
        self.assertTrue(created[0].joined)
        self.assertEqual(
            [(event.x, event.y) for event in result.events], [(10, 20)]
        )
        self.assertGreaterEqual(result.duration_ms, 0.0)


class TrimRecordedTailTest(unittest.TestCase):
    def setUp(self):
        self.events = [
            MouseEvent(type="move", x=index, y=0, delay_ms=0)
            for index in range(4)
        ]

    def test_keeps_events_before_three_second_cutoff(self):
        result = RecordingResult(
            events=self.events,
            event_times_ms=[1000.0, 6999.0, 7000.0, 9999.0],
            duration_ms=10000.0,
        )

        trimmed = trim_recorded_tail(result)

        self.assertEqual(trimmed, self.events[:2])

    def test_recording_shorter_than_three_seconds_becomes_empty(self):
        result = RecordingResult(
            events=self.events[:2],
            event_times_ms=[0.0, 1000.0],
            duration_ms=3000.0,
        )

        self.assertEqual(trim_recorded_tail(result), [])

    def test_zero_tail_keeps_all_events(self):
        result = RecordingResult(
            events=self.events,
            event_times_ms=[0.0, 1.0, 2.0, 3.0],
            duration_ms=4.0,
        )

        self.assertEqual(trim_recorded_tail(result, tail_ms=0), self.events)

    def test_rejects_negative_tail_and_mismatched_arrays(self):
        result = RecordingResult(
            events=self.events,
            event_times_ms=[0.0, 1.0, 2.0, 3.0],
            duration_ms=4.0,
        )
        with self.assertRaises(ValueError):
            trim_recorded_tail(result, tail_ms=-1)
        with self.assertRaises(ValueError):
            RecordingResult(
                events=self.events,
                event_times_ms=[0.0],
                duration_ms=4.0,
            )


if __name__ == "__main__":
    unittest.main()
