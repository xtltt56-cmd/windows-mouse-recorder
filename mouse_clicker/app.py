import os
import queue
import uuid
from dataclasses import replace
from pathlib import Path
from queue import Empty
from typing import Dict, Optional

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .models import Template, parse_playback_config
from .player import PlaybackEngine, PlaybackState
from .recorder import GlobalMouseRecorder, trim_recorded_tail
from .storage import TemplateStore, TemplateStoreError
from .windows_input import Win32InputBackend, get_virtual_screen_geometry


STATE_IDLE = "idle"
STATE_COUNTDOWN = "countdown"
STATE_RECORDING = "recording"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"
STATE_PLAYBACK_COUNTDOWN = "playback_countdown"
PLAYBACK_COUNTDOWN_SECONDS = 5


def can_start_recording(state: str) -> bool:
    return state == STATE_IDLE


def can_start_playback(state: str, event_count: int) -> bool:
    return state == STATE_IDLE and event_count > 0


def parse_loop_input(raw: str, infinite: bool):
    return parse_playback_config(raw, infinite)


def recording_finished_message(event_count: int) -> str:
    return "录制完成，已排除末尾 3 秒，保存 {} 个事件".format(event_count)


def playback_countdown_message(seconds: int) -> str:
    return "回放将在 {} 秒后开始".format(seconds)


def default_template_root() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "MouseClicker" / "templates"


class MouseClickerApp:
    def __init__(self, root=None, store: Optional[TemplateStore] = None):
        self.root = root or tk.Tk()
        self.root.title("鼠标轨迹连点器")
        self.root.geometry("780x540")
        self.root.minsize(700, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        self.store = store or TemplateStore(default_template_root())
        self._templates = {}  # type: Dict[str, Template]
        self._template_ids = []
        self._selected_id = None  # type: Optional[str]
        self._state = STATE_IDLE
        self._recording = None
        self._countdown_job = None
        self._countdown_remaining = 0
        self._playback_countdown_job = None
        self._playback_countdown_remaining = 0
        self._pending_playback = None
        self._closing = False
        self._messages = queue.Queue()

        self._status_var = tk.StringVar(value="就绪")
        self._event_var = tk.StringVar(value="事件：0")
        self._duration_var = tk.StringVar(value="时长：0.00 秒")
        self._loop_var = tk.StringVar(value="1")
        self._infinite_var = tk.BooleanVar(value=False)
        self._progress_var = tk.StringVar(value="未开始")

        self._backend_error = None
        try:
            backend = Win32InputBackend()
        except OSError as exc:
            backend = None
            self._backend_error = str(exc)

        self._player = None
        if backend is not None:
            self._player = PlaybackEngine(
                backend,
                on_state=self._queue_state,
                on_loop=self._queue_loop,
                on_error=self._queue_error,
            )

        self._build_ui()
        self._refresh_templates()
        self._set_state(STATE_IDLE)
        self.root.after(50, self._drain_messages)

    def run(self):
        self.root.mainloop()

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        template_frame = ttk.LabelFrame(outer, text="点击模板", padding=8)
        template_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        template_frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(template_frame)
        list_frame.grid(row=0, column=0, sticky="nsew")
        template_frame.columnconfigure(0, weight=1)
        self.template_list = tk.Listbox(
            list_frame,
            width=24,
            height=20,
            exportselection=False,
            activestyle="dotbox",
        )
        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.template_list.yview
        )
        self.template_list.configure(yscrollcommand=scrollbar.set)
        self.template_list.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.template_list.bind("<<ListboxSelect>>", self._on_template_selected)

        template_buttons = ttk.Frame(template_frame)
        template_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._new_button = ttk.Button(
            template_buttons, text="新建", command=self._new_template
        )
        self._rename_button = ttk.Button(
            template_buttons, text="重命名", command=self._rename_template
        )
        self._delete_button = ttk.Button(
            template_buttons, text="删除", command=self._delete_template
        )
        self._new_button.grid(row=0, column=0, sticky="ew")
        self._rename_button.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._delete_button.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        status_frame = ttk.LabelFrame(right, text="当前模板", padding=10)
        status_frame.grid(row=0, column=0, sticky="ew")
        status_frame.columnconfigure(1, weight=1)
        ttk.Label(status_frame, text="状态").grid(row=0, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self._status_var).grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        ttk.Label(status_frame, textvariable=self._event_var).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Label(status_frame, textvariable=self._duration_var).grid(
            row=1, column=1, sticky="w", padx=(12, 0), pady=(8, 0)
        )

        record_frame = ttk.LabelFrame(right, text="录制", padding=10)
        record_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        record_frame.columnconfigure(0, weight=1)
        record_frame.columnconfigure(1, weight=1)
        self._record_start_button = ttk.Button(
            record_frame, text="开始录制", command=self._start_recording
        )
        self._record_stop_button = ttk.Button(
            record_frame, text="停止录制", command=self._stop_recording
        )
        self._record_start_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self._record_stop_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        ttk.Label(
            record_frame,
            text="录制前倒计时 3 秒；开始回放前倒计时 5 秒。连点器窗口中的按钮不会被录入。",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        playback_frame = ttk.LabelFrame(right, text="回放", padding=10)
        playback_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        playback_frame.columnconfigure(1, weight=1)
        ttk.Label(playback_frame, text="循环次数").grid(row=0, column=0, sticky="w")
        self._loop_entry = ttk.Entry(
            playback_frame, textvariable=self._loop_var, width=10
        )
        self._loop_entry.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self._infinite_checkbutton = ttk.Checkbutton(
            playback_frame,
            text="无限循环",
            variable=self._infinite_var,
        )
        self._infinite_checkbutton.grid(
            row=0, column=2, sticky="w", padx=(10, 0)
        )
        ttk.Label(playback_frame, textvariable=self._progress_var).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

        playback_buttons = ttk.Frame(playback_frame)
        playback_buttons.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        for column in range(4):
            playback_buttons.columnconfigure(column, weight=1)
        self._play_button = ttk.Button(
            playback_buttons, text="开始回放", command=self._start_playback
        )
        self._pause_button = ttk.Button(
            playback_buttons, text="暂停", command=self._pause_playback
        )
        self._resume_button = ttk.Button(
            playback_buttons, text="继续", command=self._resume_playback
        )
        self._play_stop_button = ttk.Button(
            playback_buttons, text="停止", command=self._stop_playback
        )
        self._play_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._pause_button.grid(row=0, column=1, sticky="ew", padx=4)
        self._resume_button.grid(row=0, column=2, sticky="ew", padx=4)
        self._play_stop_button.grid(row=0, column=3, sticky="ew", padx=(4, 0))

        hint = ttk.Label(
            right,
            text="回放使用录制时的绝对屏幕坐标。改变分辨率或显示器布局后会先提示。",
            wraplength=560,
        )
        hint.grid(row=3, column=0, sticky="w", pady=(14, 0))

    def _refresh_templates(self, select_id: Optional[str] = None):
        try:
            templates = self.store.list_templates()
        except TemplateStoreError as exc:
            templates = []
            messagebox.showerror("读取模板失败", str(exc), parent=self.root)
        self._templates = {template.id: template for template in templates}
        self._template_ids = [template.id for template in templates]
        self.template_list.delete(0, tk.END)
        for template in templates:
            self.template_list.insert(tk.END, template.name)

        target = select_id if select_id in self._template_ids else None
        if target is None and self._template_ids:
            target = self._template_ids[0]
        self._selected_id = target
        if target is not None:
            index = self._template_ids.index(target)
            self.template_list.selection_clear(0, tk.END)
            self.template_list.selection_set(index)
            self.template_list.see(index)
        self._update_template_info()
        self._update_controls()

    def _on_template_selected(self, _event=None):
        selection = self.template_list.curselection()
        if not selection:
            self._selected_id = None
        else:
            self._selected_id = self._template_ids[selection[0]]
        self._update_template_info()
        self._update_controls()

    def _selected_template(self) -> Optional[Template]:
        if self._selected_id is None:
            return None
        return self._templates.get(self._selected_id)

    def _update_template_info(self):
        template = self._selected_template()
        if template is None:
            self._event_var.set("事件：0")
            self._duration_var.set("时长：0.00 秒")
            self._progress_var.set("未选择模板")
            return
        self._event_var.set("事件：{}".format(len(template.events)))
        self._duration_var.set(
            "时长：{:.2f} 秒".format(template.duration_ms / 1000.0)
        )
        self._progress_var.set("模板：{}".format(template.name))

    def _new_template(self):
        if self._state != STATE_IDLE:
            return
        default_name = "模板 {}".format(len(self._templates) + 1)
        name = simpledialog.askstring(
            "新建模板", "请输入模板名称：", initialvalue=default_name, parent=self.root
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("名称不能为空", "请输入模板名称。", parent=self.root)
            return
        try:
            template = Template(
                id=str(uuid.uuid4()),
                name=name,
                screen=get_virtual_screen_geometry(),
                events=[],
            )
            self.store.save(template)
            self._refresh_templates(select_id=template.id)
        except (OSError, TemplateStoreError, ValueError) as exc:
            messagebox.showerror("新建模板失败", str(exc), parent=self.root)

    def _rename_template(self):
        if self._state != STATE_IDLE:
            return
        template = self._selected_template()
        if template is None:
            return
        name = simpledialog.askstring(
            "重命名模板",
            "请输入新的模板名称：",
            initialvalue=template.name,
            parent=self.root,
        )
        if name is None:
            return
        try:
            renamed = self.store.rename(template.id, name.strip())
            self._refresh_templates(select_id=renamed.id)
        except (TemplateStoreError, ValueError) as exc:
            messagebox.showerror("重命名失败", str(exc), parent=self.root)

    def _delete_template(self):
        if self._state != STATE_IDLE:
            return
        template = self._selected_template()
        if template is None:
            return
        if not messagebox.askyesno(
            "删除模板", "确定删除“{}”吗？".format(template.name), parent=self.root
        ):
            return
        try:
            self.store.delete(template.id)
            self._refresh_templates()
        except TemplateStoreError as exc:
            messagebox.showerror("删除失败", str(exc), parent=self.root)

    def _start_recording(self):
        if not can_start_recording(self._state):
            return
        if self._selected_template() is None:
            messagebox.showinfo("请先选择模板", "请先新建或选择一套模板。", parent=self.root)
            return
        self._countdown_remaining = 3
        self._set_state(STATE_COUNTDOWN)
        self._countdown_step()

    def _countdown_step(self):
        if self._closing:
            return
        if self._countdown_remaining <= 0:
            self._begin_recording()
            return
        self._status_var.set("录制将在 {} 秒后开始".format(self._countdown_remaining))
        self._countdown_remaining -= 1
        self._countdown_job = self.root.after(1000, self._countdown_step)

    def _begin_recording(self):
        try:
            self._recording = GlobalMouseRecorder(
                excluded_region=self._window_contains
            )
            self._recording.start()
        except Exception as exc:
            self._recording = None
            self._set_state(STATE_IDLE)
            messagebox.showerror("录制失败", str(exc), parent=self.root)
            return
        self._set_state(STATE_RECORDING)
        self._status_var.set("正在录制，请在完成后点击“停止录制”")

    def _stop_recording(self):
        if self._state != STATE_RECORDING or self._recording is None:
            return
        try:
            result = self._recording.stop()
            events = trim_recorded_tail(result)
            template = self._selected_template()
            if template is None:
                raise TemplateStoreError("当前模板已不存在")
            updated = replace(
                template,
                events=events,
                screen=get_virtual_screen_geometry(),
            )
            self.store.save(updated)
            self._refresh_templates(select_id=updated.id)
            self._set_state(STATE_IDLE)
            self._status_var.set(recording_finished_message(len(events)))
        except (OSError, TemplateStoreError, ValueError) as exc:
            self._set_state(STATE_IDLE)
            messagebox.showerror("保存录制失败", str(exc), parent=self.root)
        finally:
            self._recording = None

    def _start_playback(self):
        if not can_start_playback(
            self._state,
            len(self._selected_template().events) if self._selected_template() else 0,
        ):
            return
        if self._player is None:
            messagebox.showerror(
                "回放不可用",
                self._backend_error or "Windows 输入后端无法初始化。",
                parent=self.root,
            )
            return
        template = self._selected_template()
        try:
            config = parse_loop_input(self._loop_var.get(), self._infinite_var.get())
            current_screen = get_virtual_screen_geometry()
            if current_screen != template.screen:
                if not messagebox.askyesno(
                    "桌面布局已变化",
                    "录制时为 {}x{}，当前为 {}x{}。仍要按绝对坐标回放吗？".format(
                        template.screen.width,
                        template.screen.height,
                        current_screen.width,
                        current_screen.height,
                    ),
                    parent=self.root,
                ):
                    return
            self._pending_playback = (template, config)
            self._playback_countdown_remaining = PLAYBACK_COUNTDOWN_SECONDS
            self._progress_var.set("准备回放：{}".format(template.name))
            self._set_state(STATE_PLAYBACK_COUNTDOWN)
            self._playback_countdown_step()
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("无法开始回放", str(exc), parent=self.root)

    def _playback_countdown_step(self):
        if self._closing or self._state != STATE_PLAYBACK_COUNTDOWN:
            return
        pending = self._pending_playback
        if pending is None:
            self._set_state(STATE_IDLE)
            return
        if self._playback_countdown_remaining <= 0:
            self._playback_countdown_job = None
            self._pending_playback = None
            template, config = pending
            try:
                self._progress_var.set("准备回放：{}".format(template.name))
                self._player.start(template, config)
            except (OSError, RuntimeError, ValueError) as exc:
                self._set_state(STATE_IDLE)
                messagebox.showerror("无法开始回放", str(exc), parent=self.root)
            return

        seconds = self._playback_countdown_remaining
        self._status_var.set(playback_countdown_message(seconds))
        self._progress_var.set(
            "准备回放：{}（{} 秒）".format(pending[0].name, seconds)
        )
        self._playback_countdown_remaining -= 1
        self._playback_countdown_job = self.root.after(
            1000, self._playback_countdown_step
        )

    def _pause_playback(self):
        if self._player is not None:
            self._player.pause()

    def _resume_playback(self):
        if self._player is not None:
            self._player.resume()

    def _cancel_playback_countdown(self):
        if self._playback_countdown_job is not None:
            try:
                self.root.after_cancel(self._playback_countdown_job)
            except tk.TclError:
                pass
            self._playback_countdown_job = None
        self._playback_countdown_remaining = 0
        self._pending_playback = None

    def _stop_playback(self):
        if self._state == STATE_PLAYBACK_COUNTDOWN:
            self._cancel_playback_countdown()
            self._set_state(STATE_IDLE)
            self._status_var.set("已取消回放")
            self._progress_var.set("回放已取消")
            return
        if self._player is not None:
            self._player.stop()

    def _queue_state(self, state: PlaybackState):
        self._messages.put(("state", state.value))

    def _queue_loop(self, index: int):
        self._messages.put(("loop", index))

    def _queue_error(self, error: Exception):
        self._messages.put(("error", error))

    def _drain_messages(self):
        if self._closing:
            return
        try:
            while True:
                kind, value = self._messages.get_nowait()
                if kind == "state":
                    if value == PlaybackState.PLAYING.value:
                        self._set_state(STATE_PLAYING)
                    elif value == PlaybackState.PAUSED.value:
                        self._set_state(STATE_PAUSED)
                    elif value == PlaybackState.IDLE.value:
                        self._set_state(STATE_IDLE)
                        self._status_var.set("回放已停止")
                elif kind == "loop":
                    if self._infinite_var.get():
                        self._progress_var.set("已完成第 {} 轮（无限循环）".format(value))
                    else:
                        self._progress_var.set("已完成第 {} 轮".format(value))
                elif kind == "error":
                    messagebox.showerror("回放失败", str(value), parent=self.root)
        except Empty:
            pass
        self.root.after(50, self._drain_messages)

    def _set_state(self, state: str):
        self._state = state
        status_text = {
            STATE_IDLE: "就绪",
            STATE_COUNTDOWN: "准备录制",
            STATE_RECORDING: "正在录制",
            STATE_PLAYING: "正在回放",
            STATE_PAUSED: "回放已暂停",
            STATE_PLAYBACK_COUNTDOWN: "准备回放",
        }
        self._status_var.set(status_text.get(state, state))
        self._update_controls()

    def _update_controls(self):
        idle = self._state == STATE_IDLE
        recording = self._state == STATE_RECORDING
        can_play = can_start_playback(
            self._state,
            len(self._selected_template().events) if self._selected_template() else 0,
        )
        self._set_widget_state(self.template_list, idle)
        self._set_widget_state(self._new_button, idle)
        self._set_widget_state(self._rename_button, idle and self._selected_id is not None)
        self._set_widget_state(self._delete_button, idle and self._selected_id is not None)
        self._set_widget_state(self._record_start_button, idle and self._selected_id is not None)
        self._set_widget_state(self._record_stop_button, recording)
        self._set_widget_state(self._play_button, can_play and self._player is not None)
        self._set_widget_state(self._pause_button, self._state == STATE_PLAYING)
        self._set_widget_state(self._resume_button, self._state == STATE_PAUSED)
        self._set_widget_state(self._infinite_checkbutton, idle)
        self._set_widget_state(
            self._play_stop_button,
            self._state
            in (STATE_PLAYING, STATE_PAUSED, STATE_PLAYBACK_COUNTDOWN),
        )
        self._set_widget_state(self._loop_entry, idle)

    @staticmethod
    def _set_widget_state(widget, enabled: bool):
        widget.configure(state="normal" if enabled else "disabled")

    def _window_contains(self, x: int, y: int) -> bool:
        self.root.update_idletasks()
        left = self.root.winfo_rootx()
        top = self.root.winfo_rooty()
        right = left + self.root.winfo_width()
        bottom = top + self.root.winfo_height()
        return left <= x <= right and top <= y <= bottom

    def _close(self):
        if self._closing:
            return
        self._closing = True
        if self._countdown_job is not None:
            self.root.after_cancel(self._countdown_job)
            self._countdown_job = None
        self._cancel_playback_countdown()
        if self._recording is not None:
            try:
                self._recording.stop()
            except Exception:
                pass
            self._recording = None
        if self._player is not None:
            self._player.stop()
            self._player.join(1.0)
        self.root.destroy()
