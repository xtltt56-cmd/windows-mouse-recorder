import unittest
from types import SimpleNamespace

from mouse_clicker.app import (
    PLAYBACK_COUNTDOWN_SECONDS,
    STATE_IDLE,
    STATE_PLAYBACK_COUNTDOWN,
    MouseClickerApp,
)


class FakeVariable:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class FakeRoot:
    def __init__(self):
        self.jobs = {}
        self.cancelled = []
        self._next_job = 1

    def after(self, delay_ms, callback):
        job_id = self._next_job
        self._next_job += 1
        self.jobs[job_id] = (delay_ms, callback)
        return job_id

    def after_cancel(self, job_id):
        self.cancelled.append(job_id)
        self.jobs.pop(job_id, None)

    def run_next(self):
        job_id = min(self.jobs)
        _delay_ms, callback = self.jobs.pop(job_id)
        callback()


class FakePlayer:
    def __init__(self):
        self.started = []

    def start(self, template, config):
        self.started.append((template, config))


def make_countdown_app():
    app = MouseClickerApp.__new__(MouseClickerApp)
    app.root = FakeRoot()
    app._closing = False
    app._state = STATE_PLAYBACK_COUNTDOWN
    app._playback_countdown_job = None
    app._playback_countdown_remaining = PLAYBACK_COUNTDOWN_SECONDS
    app._pending_playback = (SimpleNamespace(name="测试模板"), object())
    app._status_var = FakeVariable()
    app._progress_var = FakeVariable()
    app._player = FakePlayer()
    app._set_state = lambda state: setattr(app, "_state", state)
    return app


class PlaybackCountdownTest(unittest.TestCase):
    def test_player_starts_only_after_five_seconds(self):
        app = make_countdown_app()

        app._playback_countdown_step()
        for _ in range(4):
            app.root.run_next()

        self.assertEqual(app._player.started, [])
        self.assertEqual(app._status_var.value, "回放将在 1 秒后开始")

        app.root.run_next()

        self.assertEqual(len(app._player.started), 1)
        self.assertIsNone(app._pending_playback)

    def test_stop_cancels_countdown_without_starting_player(self):
        app = make_countdown_app()

        app._playback_countdown_step()
        pending_job = app._playback_countdown_job
        app._stop_playback()

        self.assertEqual(app._state, STATE_IDLE)
        self.assertEqual(app._player.started, [])
        self.assertIsNone(app._pending_playback)
        self.assertIn(pending_job, app.root.cancelled)
        self.assertEqual(app._status_var.value, "已取消回放")


if __name__ == "__main__":
    unittest.main()
