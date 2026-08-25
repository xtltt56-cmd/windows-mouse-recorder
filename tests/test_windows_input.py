import os
import subprocess
import sys
import unittest

from mouse_clicker.windows_input import (
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_MIDDLEDOWN,
    MOUSEEVENTF_RIGHTUP,
    WHEEL_DELTA,
    get_virtual_screen_geometry,
    mouse_button_flags,
    wheel_data,
)


class WindowsInputMappingTest(unittest.TestCase):
    def test_button_flags_match_windows_mouse_constants(self):
        self.assertEqual(mouse_button_flags("left", True), MOUSEEVENTF_LEFTDOWN)
        self.assertEqual(mouse_button_flags("left", False), MOUSEEVENTF_LEFTUP)
        self.assertEqual(mouse_button_flags("middle", True), MOUSEEVENTF_MIDDLEDOWN)
        self.assertEqual(mouse_button_flags("right", False), MOUSEEVENTF_RIGHTUP)

    def test_wheel_data_preserves_tick_direction(self):
        self.assertEqual(wheel_data(1), WHEEL_DELTA)
        self.assertEqual(wheel_data(-2), -2 * WHEEL_DELTA)

    def test_unknown_button_is_rejected(self):
        with self.assertRaises(ValueError):
            mouse_button_flags("xbutton", True)


@unittest.skipUnless(os.name == "nt", "DPI awareness is Windows-only")
class DpiAwarenessTest(unittest.TestCase):
    def test_main_entrypoint_uses_per_monitor_dpi_awareness(self):
        script = r'''
import ctypes
from ctypes import wintypes

import main

shcore = ctypes.windll.shcore
kernel32 = ctypes.windll.kernel32
shcore.GetProcessDpiAwareness.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(ctypes.c_int),
]
shcore.GetProcessDpiAwareness.restype = ctypes.c_long
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
awareness = ctypes.c_int(-1)
result = shcore.GetProcessDpiAwareness(
    kernel32.GetCurrentProcess(), ctypes.byref(awareness)
)
if result != 0:
    raise SystemExit("GetProcessDpiAwareness failed: {}".format(result))
print(awareness.value)
'''
        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "2")


@unittest.skipUnless(os.name == "nt", "Windows screen metrics are only available on Windows")
class VirtualScreenTest(unittest.TestCase):
    def test_virtual_screen_has_positive_size(self):
        geometry = get_virtual_screen_geometry()

        self.assertGreater(geometry.width, 0)
        self.assertGreater(geometry.height, 0)


if __name__ == "__main__":
    unittest.main()
