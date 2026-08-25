import threading
import time
from enum import Enum
from typing import Callable, Optional, Protocol, Set, Tuple

from .models import MouseEvent, PlaybackConfig, Template


class InputBackend(Protocol):
    def move_to(self, x: int, y: int) -> None:
        pass

    def button_down(self, button: str) -> None:
        pass

    def button_up(self, button: str) -> None:
        pass

    def scroll(self, dx: int, dy: int) -> None:
        pass


class PlaybackState(Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"


class PlaybackEngine:
    def __init__(
        self,
        backend: InputBackend,
        on_state: Optional[Callable[[PlaybackState], None]] = None,
        on_loop: Optional[Callable[[int], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self._backend = backend
        self._on_state = on_state
        self._on_loop = on_loop
        self._on_error = on_error
        self._clock = clock
        self._sleeper = sleeper
        self._condition = threading.Condition(threading.RLock())
        self._state = PlaybackState.IDLE
        self._stop_requested = False
        self._paused = False
        self._thread = None  # type: Optional[threading.Thread]
        self._pressed_buttons = set()  # type: Set[str]
        self._last_position = None  # type: Optional[Tuple[int, int]]

    @property
    def state(self) -> PlaybackState:
        with self._condition:
            return self._state

    @property
    def is_running(self) -> bool:
        return self.state != PlaybackState.IDLE

    def start(self, template: Template, config: PlaybackConfig) -> None:
        if not template.events:
            raise ValueError("cannot play an empty template")
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("playback is already active")
            self._stop_requested = False
            self._paused = False
            self._pressed_buttons.clear()
            self._last_position = None
            self._state = PlaybackState.PLAYING
            thread = threading.Thread(
                target=self._run,
                args=(template, config),
                name="mouse-clicker-playback",
                daemon=True,
            )
            self._thread = thread
        self._emit_state(PlaybackState.PLAYING)
        thread.start()

    def pause(self) -> None:
        changed = False
        with self._condition:
            if self._state == PlaybackState.PLAYING:
                self._paused = True
                self._state = PlaybackState.PAUSED
                self._condition.notify_all()
                changed = True
        if changed:
            self._emit_state(PlaybackState.PAUSED)

    def resume(self) -> None:
        changed = False
        with self._condition:
            if self._state == PlaybackState.PAUSED:
                self._paused = False
                self._state = PlaybackState.PLAYING
                self._condition.notify_all()
                changed = True
        if changed:
            self._emit_state(PlaybackState.PLAYING)

    def stop(self) -> None:
        with self._condition:
            if self._state == PlaybackState.IDLE and not (
                self._thread is not None and self._thread.is_alive()
            ):
                return
            self._stop_requested = True
            self._paused = False
            self._condition.notify_all()

    def join(self, timeout: Optional[float] = None) -> None:
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def _run(self, template: Template, config: PlaybackConfig) -> None:
        loop_index = 0
        try:
            while not self._is_stop_requested():
                self._last_position = None
                for event in template.events:
                    if not self._wait_delay(event.delay_ms / 1000.0):
                        return
                    if self._is_stop_requested():
                        return
                    self._dispatch(event)
                loop_index += 1
                if self._on_loop is not None:
                    self._on_loop(loop_index)
                if config.loops is not None and loop_index >= config.loops:
                    return
        except Exception as exc:
            if not self._is_stop_requested():
                self._report_error(exc)
        finally:
            self._release_pressed_buttons()
            with self._condition:
                self._state = PlaybackState.IDLE
                self._paused = False
                self._condition.notify_all()
            self._emit_state(PlaybackState.IDLE)

    def _wait_delay(self, seconds: float) -> bool:
        remaining = max(0.0, seconds)
        while True:
            with self._condition:
                while self._paused and not self._stop_requested:
                    self._condition.wait()
                if self._stop_requested:
                    return False
                if remaining <= 0.0:
                    return True
                slice_seconds = min(remaining, 0.01)
            started = self._clock()
            self._sleeper(slice_seconds)
            elapsed = max(0.0, self._clock() - started)
            remaining -= max(elapsed, slice_seconds)

    def _dispatch(self, event: MouseEvent) -> None:
        self._ensure_position(event.x, event.y)
        if event.type == "move":
            return
        if event.type == "button":
            if event.action == "press":
                self._backend.button_down(event.button)
                self._pressed_buttons.add(event.button)
            else:
                self._backend.button_up(event.button)
                self._pressed_buttons.discard(event.button)
            return
        if event.type == "scroll":
            self._backend.scroll(event.dx, event.dy)
            return
        raise ValueError("unsupported event type: {}".format(event.type))

    def _ensure_position(self, x: int, y: int) -> None:
        position = (x, y)
        if self._last_position != position:
            self._backend.move_to(x, y)
            self._last_position = position

    def _release_pressed_buttons(self) -> None:
        pressed = list(self._pressed_buttons)
        self._pressed_buttons.clear()
        for button in pressed:
            try:
                self._backend.button_up(button)
            except Exception as exc:
                self._report_error(exc)

    def _is_stop_requested(self) -> bool:
        with self._condition:
            return self._stop_requested

    def _emit_state(self, state: PlaybackState) -> None:
        if self._on_state is not None:
            try:
                self._on_state(state)
            except Exception:
                pass

    def _report_error(self, error: Exception) -> None:
        if self._on_error is not None:
            try:
                self._on_error(error)
            except Exception:
                pass
