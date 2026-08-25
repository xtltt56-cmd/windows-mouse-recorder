from mouse_clicker.windows_input import enable_per_monitor_dpi_awareness


# Must run before Tk creates any window, otherwise Windows may virtualize DPI coordinates.
enable_per_monitor_dpi_awareness()

from mouse_clicker.app import MouseClickerApp


if __name__ == "__main__":
    MouseClickerApp().run()
