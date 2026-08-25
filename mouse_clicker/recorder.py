import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from .models import BUTTONS, MouseEvent


class RecorderUnavailableError(RuntimeError):
    """Raised when the global mouse hook cannot be created."""


@dataclass(frozen=True)
class RecordingResult:
    events: List[MouseEvent]
    event_times_ms: List[float]
    duration_ms: float

    def __post_init__(self):
        if len(self.events) != len(self.event_times_ms):
            raise ValueError("events and event_times_ms must have equal lengths")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")


class RecordingSession:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        excluded_region: Optional[Callable[[int, int], bool]] = None,
    ):
        self._clock = clock
        self._excluded_region = excluded_region
        self._events = []  # type: List[MouseEvent]
        self._event_times_ms = []  # type: List[float]
        self._active = False
        self._last_timestamp = None  # type: Optional[float]
        self._started_at = None  # type: Optional[float]
        self._cached_result = None  # type: Optional[RecordingResult]
        self._lock = threading.RLock()

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def start(self) -> None:
        with self._lock:
            self._events = []
            self._event_times_ms = []
            self._last_timestamp = None
            self._active = True
            self._started_at = self._clock()
            self._cached_result = None

    def on_move(self, x: int, y: int) -> None:
        self._append(
            MouseEvent(type="move", x=int(x), y=int(y), delay_ms=0.0),
            int(x),
            int(y),
        )

    def on_click(self, x: int, y: int, button, pressed: bool) -> None:
        name = self._normalize_button(button)
        self._append(
            MouseEvent(
                type="button",
                x=int(x),
                y=int(y),
                delay_ms=0.0,
                action="press" if pressed else "release",
                button=name,
            ),
            int(x),
            int(y),
        )

    def on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if int(dx) == 0 and int(dy) == 0:
            return
        self._append(
            MouseEvent(
                type="scroll",
                x=int(x),
                y=int(y),
                delay_ms=0.0,
                dx=int(dx),
                dy=int(dy),
            ),
            int(x),
            int(y),
        )

    def stop(self, stop_time: Optional[float] = None) -> RecordingResult:
        with self._lock:
            if not self._active and self._cached_result is not None:
                return self._cached_result
            final_time = self._clock() if stop_time is None else stop_time
            started_at = self._started_at if self._started_at is not None else final_time
            duration_ms = round(max(0.0, final_time - started_at) * 1000.0, 3)
            self._active = False
            self._cached_result = RecordingResult(
                events=list(self._events),
                event_times_ms=list(self._event_times_ms),
                duration_ms=duration_ms,
            )
            return self._cached_result

    def _append(self, event: MouseEvent, x: int, y: int) -> None:
        with self._lock:
            if not self._active:
                return
            if self._excluded_region is not None and self._excluded_region(x, y):
                return

            now = self._clock()
            delay_ms = 0.0
            if self._last_timestamp is not None:
                delay_ms = round(max(0.0, now - self._last_timestamp) * 1000.0, 3)
            self._last_timestamp = now
            self._events.append(
                MouseEvent(
                    type=event.type,
                    x=event.x,
                    y=event.y,
                    delay_ms=delay_ms,
                    action=event.action,
                    button=event.button,
                    dx=event.dx,
                    dy=event.dy,
                )
            )
            started_at = self._started_at if self._started_at is not None else now
            event_time_ms = round(max(0.0, now - started_at) * 1000.0, 3)
            self._event_times_ms.append(event_time_ms)

    @staticmethod
    def _normalize_button(button) -> str:
        name = getattr(button, "name", button)
        if not isinstance(name, str):
            name = str(name).rsplit(".", 1)[-1]
        if name not in BUTTONS:
            raise ValueError("unsupported mouse button: {}".format(name))
        return name


def _default_listener_factory(**callbacks):
    try:
        from pynput import mouse
    except ImportError as exc:
        raise RecorderUnavailableError(
            "pynput is required for global mouse recording; "
            "run python -m pip install -r requirements.txt"
        ) from exc
    return mouse.Listener(**callbacks)


class GlobalMouseRecorder:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        excluded_region: Optional[Callable[[int, int], bool]] = None,
        listener_factory: Optional[Callable] = None,
    ):
        self._clock = clock
        self.session = RecordingSession(clock=clock, excluded_region=excluded_region)
        self._listener_factory = listener_factory or _default_listener_factory
        self._listener = None

    @property
    def is_recording(self) -> bool:
        return self.session.is_active

    def start(self) -> None:
        if self.is_recording:
            raise RuntimeError("recording is already active")
        self.session.start()
        try:
            self._listener = self._listener_factory(
                on_move=self.session.on_move,
                on_click=self.session.on_click,
                on_scroll=self.session.on_scroll,
            )
            self._listener.start()
        except Exception:
            self.session.stop()
            self._listener = None
            raise

    def stop(self) -> RecordingResult:
        stop_time = self._clock()
        listener = self._listener
        self._listener = None
        stop_error = None
        if listener is not None:
            try:
                listener.stop()
            except Exception as exc:
                stop_error = exc
            try:
                listener.join()
            except Exception as exc:
                if stop_error is None:
                    stop_error = exc
        result = self.session.stop(stop_time=stop_time)
        if stop_error is not None:
            raise stop_error
        return result


def trim_recorded_tail(
    result: RecordingResult, tail_ms: float = 3000.0
) -> List[MouseEvent]:
    if len(result.events) != len(result.event_times_ms):
        raise ValueError("events and event_times_ms must have equal lengths")
    if tail_ms < 0:
        raise ValueError("tail_ms must not be negative")
    if tail_ms == 0:
        return list(result.events)
    cutoff = max(0.0, result.duration_ms - tail_ms)
    return [
        event
        for event, event_time in zip(result.events, result.event_times_ms)
        if event_time < cutoff
    ]
