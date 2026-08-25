import ctypes
import os
from ctypes import wintypes

from .models import ScreenGeometry


INPUT_MOUSE = 0
WHEEL_DELTA = 120

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

PROCESS_PER_MONITOR_DPI_AWARE = 2
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = (
    (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 4
)


_BUTTON_FLAGS = {
    ("left", True): MOUSEEVENTF_LEFTDOWN,
    ("left", False): MOUSEEVENTF_LEFTUP,
    ("right", True): MOUSEEVENTF_RIGHTDOWN,
    ("right", False): MOUSEEVENTF_RIGHTUP,
    ("middle", True): MOUSEEVENTF_MIDDLEDOWN,
    ("middle", False): MOUSEEVENTF_MIDDLEUP,
}


def mouse_button_flags(button: str, pressed: bool) -> int:
    try:
        return _BUTTON_FLAGS[(button, pressed)]
    except KeyError as exc:
        raise ValueError("unsupported mouse button: {}".format(button)) from exc


def wheel_data(delta: int) -> int:
    return int(delta) * WHEEL_DELTA


def enable_per_monitor_dpi_awareness() -> bool:
    if os.name != "nt":
        return False

    user32 = ctypes.windll.user32
    set_context = getattr(user32, "SetProcessDpiAwarenessContext", None)
    if set_context is not None:
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = wintypes.BOOL
        if set_context(
            ctypes.c_void_p(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        ):
            return True

    shcore = ctypes.windll.shcore
    set_awareness = getattr(shcore, "SetProcessDpiAwareness", None)
    if set_awareness is None:
        return False
    set_awareness.argtypes = [ctypes.c_int]
    set_awareness.restype = ctypes.c_long
    return set_awareness(PROCESS_PER_MONITOR_DPI_AWARE) == 0


def _require_windows():
    if os.name != "nt":
        raise OSError("Windows input backend requires Windows")
    return ctypes.windll.user32


def get_virtual_screen_geometry() -> ScreenGeometry:
    user32 = _require_windows()
    return ScreenGeometry(
        left=int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
        top=int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
        width=int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)),
        height=int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


class Win32InputBackend:
    def __init__(self):
        self._user32 = _require_windows()
        self._user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(INPUT),
            ctypes.c_int,
        ]
        self._user32.SendInput.restype = wintypes.UINT

    def move_to(self, x: int, y: int) -> None:
        if not self._user32.SetCursorPos(int(x), int(y)):
            raise ctypes.WinError()

    def button_down(self, button: str) -> None:
        self._send(flags=mouse_button_flags(button, True))

    def button_up(self, button: str) -> None:
        self._send(flags=mouse_button_flags(button, False))

    def scroll(self, dx: int, dy: int) -> None:
        if int(dy):
            self._send(mouse_data=wheel_data(dy), flags=MOUSEEVENTF_WHEEL)
        if int(dx):
            self._send(mouse_data=wheel_data(dx), flags=MOUSEEVENTF_HWHEEL)

    def _send(self, mouse_data: int = 0, flags: int = 0) -> None:
        input_event = INPUT()
        input_event.type = INPUT_MOUSE
        input_event.mi = MOUSEINPUT(
            dx=0,
            dy=0,
            mouseData=mouse_data & 0xFFFFFFFF,
            dwFlags=flags,
            time=0,
            dwExtraInfo=None,
        )
        sent = self._user32.SendInput(1, ctypes.byref(input_event), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError()
