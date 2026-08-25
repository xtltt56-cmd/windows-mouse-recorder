# Windows 全局鼠标连点器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Windows 桌面连点器，录制全局鼠标事件并按绝对坐标、原始时间间隔和用户设置的循环方式回放。

**Architecture:** 使用 Tkinter 主线程负责界面，使用独立的录制线程接收全局鼠标回调，使用独立的回放线程执行可暂停、可停止的事件序列。录制数据先进入纯 Python 数据模型，再由本地 JSON 存储层持久化；Windows API 输入后端通过接口注入播放器，核心逻辑可在不触碰真实鼠标的情况下测试。

**Tech Stack:** Python 3.8+、Tkinter、`pynput`、Windows `ctypes`/`SendInput`、标准库 `unittest`、PyInstaller（打包阶段）。

---

## 文件结构

将创建以下文件：

- `requirements.txt`：运行时依赖 `pynput`。
- `main.py`：启动 `MouseClickerApp`。
- `mouse_clicker/__init__.py`：包标识和版本常量。
- `mouse_clicker/models.py`：事件、模板、屏幕几何和循环配置模型。
- `mouse_clicker/storage.py`：模板 JSON 的本地 CRUD 和原子写入。
- `mouse_clicker/recorder.py`：录制会话和全局 `pynput` 监听适配器。
- `mouse_clicker/windows_input.py`：Windows 虚拟桌面读取和 `SendInput` 输入后端。
- `mouse_clicker/player.py`：后台回放、暂停、继续、停止和循环。
- `mouse_clicker/app.py`：Tkinter 界面、状态转换和线程消息轮询。
- `tests/__init__.py`：测试包标识。
- `tests/test_models.py`：模型和循环配置测试。
- `tests/test_storage.py`：存储层测试。
- `tests/test_recorder.py`：录制转换和过滤测试。
- `tests/test_player.py`：回放顺序、循环和停止测试。
- `tests/test_windows_input.py`：Windows 输入标志和屏幕几何纯函数测试。
- `README.md`：安装、使用、限制和打包说明。
- `build.ps1`：安装 PyInstaller 并生成单文件 Windows exe。

## Task 1: 建立 Python 项目和测试基础

**Files:**

- Create: `requirements.txt`
- Create: `mouse_clicker/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: 创建依赖和包目录**

写入 `requirements.txt`：

```text
pynput>=1.7.6,<2
```

写入 `mouse_clicker/__init__.py`：

```python
__version__ = "0.1.0"
```

创建空的 `tests/__init__.py`。

- [ ] **Step 2: 先写启动烟雾测试**

写入 `tests/test_smoke.py`：

```python
import unittest


class ProjectSmokeTest(unittest.TestCase):
    def test_package_imports(self):
        import mouse_clicker

        self.assertEqual(mouse_clicker.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行测试确认测试入口有效**

运行：

```powershell
python -m unittest tests.test_smoke -v
```

预期：`test_package_imports ok`，结果为 `OK`。

- [ ] **Step 4: 运行当前测试集并保持入口范围最小**

此阶段不创建应用入口，避免在 `app.py` 尚未实现时引入未覆盖的生产导入。运行 `python -m unittest discover -s tests -v`，预期只有 `test_smoke` 通过。

## Task 2: 用 TDD 实现事件、模板和循环配置模型

**Files:**

- Create: `tests/test_models.py`
- Create: `mouse_clicker/models.py`

- [ ] **Step 1: 写模型失败测试**

写入 `tests/test_models.py`：

```python
import unittest
from dataclasses import asdict

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
            events=[MouseEvent(type="scroll", x=50, y=60, delay_ms=10, dx=0, dy=-1)],
        )

        self.assertEqual(Template.from_dict(template.to_dict()), template)


class PlaybackConfigTest(unittest.TestCase):
    def test_fixed_loop_requires_positive_integer(self):
        self.assertEqual(PlaybackConfig.fixed(3).loops, 3)
        with self.assertRaises(ValueError):
            PlaybackConfig.fixed(0)
        with self.assertRaises(ValueError):
            PlaybackConfig.fixed(-1)

    def test_infinite_loop_has_no_loop_limit(self):
        self.assertTrue(PlaybackConfig.infinite().is_infinite)
        self.assertIsNone(PlaybackConfig.infinite().loops)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行模型测试确认它因缺少实现而失败**

运行：

```powershell
python -m unittest tests.test_models -v
```

预期：FAIL，原因是 `mouse_clicker.models` 尚不存在；若出现语法错误，先修正测试文件再继续。

- [ ] **Step 3: 实现最小模型**

在 `mouse_clicker/models.py` 中实现：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EVENT_TYPES = {"move", "button", "scroll"}
BUTTONS = {"left", "right", "middle"}
BUTTON_ACTIONS = {"press", "release"}


@dataclass(frozen=True)
class ScreenGeometry:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("screen width and height must be positive")

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScreenGeometry":
        return cls(
            left=int(value["left"]),
            top=int(value["top"]),
            width=int(value["width"]),
            height=int(value["height"]),
        )


@dataclass(frozen=True)
class MouseEvent:
    type: str
    x: int
    y: int
    delay_ms: float
    action: str | None = None
    button: str | None = None
    dx: int = 0
    dy: int = 0

    def __post_init__(self) -> None:
        if self.type not in EVENT_TYPES:
            raise ValueError(f"unsupported event type: {self.type}")
        if self.x != int(self.x) or self.y != int(self.y):
            raise ValueError("mouse coordinates must be integers")
        if self.delay_ms < 0:
            raise ValueError("delay_ms must not be negative")
        if self.type == "button":
            if self.action not in BUTTON_ACTIONS or self.button not in BUTTONS:
                raise ValueError("button event requires a valid action and button")
        elif self.type == "scroll":
            if self.dx == 0 and self.dy == 0:
                raise ValueError("scroll event must have a non-zero delta")
        elif self.action is not None or self.button is not None:
            raise ValueError("move event cannot contain button fields")

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "delay_ms": self.delay_ms,
        }
        if self.action is not None:
            value["action"] = self.action
        if self.button is not None:
            value["button"] = self.button
        if self.type == "scroll":
            value["dx"] = self.dx
            value["dy"] = self.dy
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MouseEvent":
        return cls(
            type=str(value["type"]),
            x=int(value["x"]),
            y=int(value["y"]),
            delay_ms=float(value["delay_ms"]),
            action=value.get("action"),
            button=value.get("button"),
            dx=int(value.get("dx", 0)),
            dy=int(value.get("dy", 0)),
        )


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    screen: ScreenGeometry
    events: list[MouseEvent] = field(default_factory=list)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("template id is required")
        if not self.name.strip():
            raise ValueError("template name is required")
        if self.version != 1:
            raise ValueError(f"unsupported template version: {self.version}")

    @property
    def duration_ms(self) -> float:
        return sum(event.delay_ms for event in self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "name": self.name,
            "screen": self.screen.to_dict(),
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Template":
        return cls(
            version=int(value.get("version", 1)),
            id=str(value["id"]),
            name=str(value["name"]),
            screen=ScreenGeometry.from_dict(value["screen"]),
            events=[MouseEvent.from_dict(item) for item in value.get("events", [])],
        )


@dataclass(frozen=True)
class PlaybackConfig:
    loops: int | None

    @property
    def is_infinite(self) -> bool:
        return self.loops is None

    @classmethod
    def fixed(cls, loops: int) -> "PlaybackConfig":
        if isinstance(loops, bool) or not isinstance(loops, int) or loops <= 0:
            raise ValueError("fixed loop count must be a positive integer")
        return cls(loops=loops)

    @classmethod
    def infinite(cls) -> "PlaybackConfig":
        return cls(loops=None)


def parse_playback_config(raw: str, infinite: bool) -> PlaybackConfig:
    if infinite:
        return PlaybackConfig.infinite()
    try:
        loops = int(raw.strip())
    except ValueError as exc:
        raise ValueError("loop count must be a positive integer") from exc
    return PlaybackConfig.fixed(loops)
```

- [ ] **Step 4: 运行模型测试确认通过**

运行 `python -m unittest tests.test_models -v`，预期所有模型测试为 `ok`。

- [ ] **Step 5: 重构并运行全套现有测试**

检查没有重复的序列化逻辑，运行 `python -m unittest discover -s tests -v`，预期所有当前测试通过。

## Task 3: 用 TDD 实现模板本地存储

**Files:**

- Create: `tests/test_storage.py`
- Create: `mouse_clicker/storage.py`

- [ ] **Step 1: 写存储失败测试**

使用 `tempfile.TemporaryDirectory()`，覆盖：保存后列表可见、重新加载等于原模板、重命名、删除、损坏 JSON 抛出 `TemplateStoreError`，以及保存使用临时文件替换后不留下 `.tmp` 文件。

核心测试接口固定为：

```python
store = TemplateStore(Path(temp_dir))
store.save(template)
self.assertEqual(store.load(template.id), template)
store.rename(template.id, "新名称")
self.assertEqual(store.load(template.id).name, "新名称")
store.delete(template.id)
with self.assertRaises(TemplateNotFoundError):
    store.load(template.id)
```

- [ ] **Step 2: 运行测试确认缺少实现**

运行 `python -m unittest tests.test_storage -v`，预期因 `mouse_clicker.storage` 尚不存在而失败。

- [ ] **Step 3: 实现存储层**

实现以下接口：

```python
class TemplateStoreError(Exception):
    pass

class TemplateNotFoundError(TemplateStoreError):
    pass

class TemplateStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def list_templates(self) -> list[Template]:
        raise NotImplementedError

    def load(self, template_id: str) -> Template:
        raise NotImplementedError

    def save(self, template: Template) -> None:
        raise NotImplementedError

    def rename(self, template_id: str, name: str) -> Template:
        raise NotImplementedError

    def delete(self, template_id: str) -> None:
        raise NotImplementedError
```

`save` 必须创建目录，用 `NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, suffix=".tmp", delete=False)` 写完整 JSON，再用 `os.replace` 替换 `<id>.json`；`load` 对 `OSError`、`JSONDecodeError` 和模型 `ValueError` 统一转换为可显示的 `TemplateStoreError`。`list_templates` 跳过 `.tmp` 文件并按名称、不区分大小写排序。

- [ ] **Step 4: 运行存储测试确认通过**

运行 `python -m unittest tests.test_storage -v`，预期所有存储测试通过。

- [ ] **Step 5: 运行全套测试**

运行 `python -m unittest discover -s tests -v`，预期模型和存储测试全部通过。

## Task 4: 用 TDD 实现录制会话和全局监听适配

**Files:**

- Create: `tests/test_recorder.py`
- Create: `mouse_clicker/recorder.py`

- [ ] **Step 1: 写录制会话失败测试**

测试使用可控时钟：

```python
clock.now = 10.0
session.start()
clock.now = 10.125
session.on_move(100, 200)
clock.now = 10.250
session.on_click(100, 200, "left", True)
clock.now = 10.300
session.on_click(100, 200, "left", False)
events = session.stop()

self.assertEqual(events[0].delay_ms, 0.0)
self.assertEqual(events[1].delay_ms, 125.0)
self.assertEqual(events[2].delay_ms, 50.0)
```

另测：未启动时忽略回调、过滤矩形内事件、滚轮保存 `dx/dy`、按钮枚举转换为 `left/right/middle`、停止后不再追加事件。

- [ ] **Step 2: 运行录制测试确认缺少实现**

运行 `python -m unittest tests.test_recorder -v`，预期因 `mouse_clicker.recorder` 尚不存在而失败。

- [ ] **Step 3: 实现可测试的 `RecordingSession`**

实现固定接口：

```python
class RecordingSession:
    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 excluded_region: Callable[[int, int], bool] | None = None):
        raise NotImplementedError

    def start(self) -> None:
        raise NotImplementedError

    def on_move(self, x: int, y: int) -> None:
        raise NotImplementedError

    def on_click(self, x: int, y: int, button: str, pressed: bool) -> None:
        raise NotImplementedError

    def on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        raise NotImplementedError

    def stop(self) -> list[MouseEvent]:
        raise NotImplementedError
```

首次事件延迟固定为 `0.0`，后续延迟为当前单调时间减去上一个已接收事件时间，换算成毫秒并保留 3 位小数。若坐标命中排除区域则整个事件丢弃，且不更新上一个事件时间，避免连点器按钮操作产生额外间隔。

- [ ] **Step 4: 运行录制测试确认通过**

运行 `python -m unittest tests.test_recorder -v`，预期所有会话测试通过。

- [ ] **Step 5: 实现 `GlobalMouseRecorder` 适配器并只做可导入验证**

使用延迟导入的 `pynput.mouse.Listener`，把 `on_move`、`on_click` 和 `on_scroll` 回调转发给 `RecordingSession`。`start()` 启动 listener，`stop()` 调用 listener.stop/join；如果导入失败，抛出带安装命令的 `RecorderUnavailableError`。运行 `python -c "from mouse_clicker.recorder import GlobalMouseRecorder"`，预期退出码为 0。

## Task 5: 用 TDD 实现 Windows 输入纯函数和屏幕几何

**Files:**

- Create: `tests/test_windows_input.py`
- Create: `mouse_clicker/windows_input.py`

- [ ] **Step 1: 写纯函数失败测试**

测试以下行为：`left/right/middle` 映射到对应按下/释放标志，滚轮方向保留 `dy`，`ScreenGeometry` 返回 Windows 虚拟桌面四个系统指标，未知按钮抛出 `ValueError`。测试不调用真实鼠标。

- [ ] **Step 2: 运行测试确认缺少实现**

运行 `python -m unittest tests.test_windows_input -v`，预期因模块不存在而失败。

- [ ] **Step 3: 实现 Windows API 封装**

实现固定接口：

```python
def get_virtual_screen_geometry() -> ScreenGeometry:
    raise NotImplementedError

def mouse_button_flags(button: str, pressed: bool) -> int:
    raise NotImplementedError

class Win32InputBackend:
    def move_to(self, x: int, y: int) -> None:
        raise NotImplementedError

    def button_down(self, button: str) -> None:
        raise NotImplementedError

    def button_up(self, button: str) -> None:
        raise NotImplementedError

    def scroll(self, dx: int, dy: int) -> None:
        raise NotImplementedError
```

用 `ctypes.windll.user32.GetSystemMetrics` 读取 `SM_XVIRTUALSCREEN=76`、`SM_YVIRTUALSCREEN=77`、`SM_CXVIRTUALSCREEN=78`、`SM_CYVIRTUALSCREEN=79`。用 `SetCursorPos` 执行移动，用 `SendInput` 执行按钮和滚轮；非 Windows 平台构造时抛出 `OSError("Windows input backend requires Windows")`。

- [ ] **Step 4: 运行纯函数测试确认通过**

运行 `python -m unittest tests.test_windows_input -v`，预期所有纯函数测试通过。

- [ ] **Step 5: 运行一次真实 API 读取验证**

运行：

```powershell
python -c "from mouse_clicker.windows_input import get_virtual_screen_geometry; print(get_virtual_screen_geometry())"
```

预期输出当前虚拟桌面几何信息，且不移动鼠标、不产生点击。

## Task 6: 用 TDD 实现可暂停回放引擎

**Files:**

- Create: `tests/test_player.py`
- Create: `mouse_clicker/player.py`

- [ ] **Step 1: 写回放失败测试**

使用记录调用的 `FakeInputBackend`，覆盖：

```python
template = make_template([
    move(10, 20, 0),
    press("left", 10, 20, 5),
    release("left", 10, 20, 2),
])
engine = PlaybackEngine(FakeInputBackend(), sleeper=fake_sleep)
engine.start(template, PlaybackConfig.fixed(2))
engine.join()

self.assertEqual(backend.calls, [
    ("move_to", 10, 20),
    ("button_down", "left"),
    ("button_up", "left"),
    ("move_to", 10, 20),
    ("button_down", "left"),
    ("button_up", "left"),
])
```

另测：空模板拒绝启动、无限循环在 `stop()` 后结束、停止后释放仍按住的按钮、暂停期间不执行后续事件、异常通过回调报告并恢复 `IDLE` 状态。

- [ ] **Step 2: 运行回放测试确认缺少实现**

运行 `python -m unittest tests.test_player -v`，预期因 `mouse_clicker.player` 尚不存在而失败。

- [ ] **Step 3: 实现播放器接口和线程控制**

实现：

```python
class PlaybackState(Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"

class PlaybackEngine:
    def __init__(self, backend: InputBackend,
                 on_state: Callable[[PlaybackState], None] | None = None,
                 on_loop: Callable[[int], None] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep):
        raise NotImplementedError

    def start(self, template: Template, config: PlaybackConfig) -> None:
        raise NotImplementedError

    def pause(self) -> None:
        raise NotImplementedError

    def resume(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def join(self, timeout: float | None = None) -> None:
        raise NotImplementedError
```

回放线程在每个事件前以 `threading.Condition` 等待 `delay_ms`，等待被拆成不超过 10 ms 的片段以响应停止。暂停时冻结剩余延迟，继续后从剩余时间继续。输入调用抛出异常时先释放当前按下按钮，再报告错误并回到 `IDLE`。固定循环在完成指定次数后结束；无限循环只有收到停止信号才结束。

- [ ] **Step 4: 运行回放测试确认通过**

运行 `python -m unittest tests.test_player -v`，预期所有回放测试通过。

- [ ] **Step 5: 检查线程资源并运行全套测试**

确认 `stop()` 可重复调用、`join()` 不泄漏线程，运行 `python -m unittest discover -s tests -v`，预期所有当前测试通过。

## Task 7: 实现 Tkinter 界面和应用状态转换

**Files:**

- Create: `mouse_clicker/app.py`
- Create: `main.py`
- Create: `tests/test_app_helpers.py`

- [ ] **Step 1: 先测试界面输入校验和状态转换辅助函数**

把不依赖 Tk 根窗口的逻辑放在 `app.py` 顶层函数中并先测试：

```python
def can_start_recording(state: str) -> bool:
    raise NotImplementedError

def can_start_playback(state: str, event_count: int) -> bool:
    raise NotImplementedError

def parse_loop_input(raw: str, infinite: bool) -> PlaybackConfig:
    raise NotImplementedError
```

测试录制中不能回放、回放中不能录制、空模板不能回放、无限循环和固定正整数输入有效、空白/0/负数/小数输入无效。

- [ ] **Step 2: 运行辅助函数测试确认失败**

运行 `python -m unittest tests.test_app_helpers -v`，预期因辅助函数不存在而失败。

- [ ] **Step 3: 实现辅助函数并确认通过**

实现函数并复用 `parse_playback_config`，运行 `python -m unittest tests.test_app_helpers -v`，预期全部通过。

- [ ] **Step 4: 实现 `MouseClickerApp` 主窗口**

创建 Tkinter 控件和以下操作：

- 初始化 `%APPDATA%\\MouseClicker\\templates` 存储、全局录制器和 `PlaybackEngine(Win32InputBackend())`。
- `MouseClickerApp.__init__` 创建根窗口和全部控件，`run()` 只调用根窗口的 `mainloop()`。
- 列出模板并在选择变化时更新事件数和总时长。
- 新建模板时生成 UUID 和默认名称 `模板 N`；重命名先校验非空；删除弹出确认。
- 开始录制时创建 3 秒倒计时，通过 `after` 更新状态；倒计时结束后启动 `GlobalMouseRecorder`，并把自身窗口的屏幕矩形作为排除区域。
- 停止录制时把事件和当前虚拟桌面几何写入模板并保存。
- 开始回放前解析循环配置、检查模板非空、比较虚拟桌面几何并在变化时弹出确认。
- 播放状态和线程回调只通过 `after(50, self._drain_messages)` 在主线程更新按钮、状态栏和循环进度。
- `WM_DELETE_WINDOW` 回调先停止录制和回放，再销毁窗口。

- [ ] **Step 5: 运行界面静态导入与手工启动检查**

运行：

```powershell
python -c "from mouse_clicker.app import MouseClickerApp; print('import ok')"
python main.py
```

预期第一条输出 `import ok`；第二条打开主窗口，能看到模板列表、录制区和回放区。关闭窗口后进程退出且没有异常回溯。

## Task 8: 完成依赖、文档和 exe 打包入口

**Files:**

- Create: `README.md`
- Create: `build.ps1`

- [ ] **Step 1: 写 README 使用说明**

README 必须包含：安装 Python 3.8+、`python -m pip install -r requirements.txt`、`python main.py` 启动方式、录制/回放步骤、模板存储位置、绝对坐标和分辨率变化限制、只支持鼠标不支持键盘、如何安全停止。

- [ ] **Step 2: 写打包脚本**

`build.ps1` 内容固定为：

```powershell
$ErrorActionPreference = "Stop"
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name MouseClicker main.py
Write-Host "Built dist\\MouseClicker.exe"
```

- [ ] **Step 3: 验证依赖安装和完整自动化测试**

运行：

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

预期依赖安装成功，测试输出无失败和错误。

- [ ] **Step 4: 生成 exe 并检查文件存在**

运行 `powershell -ExecutionPolicy Bypass -File .\\build.ps1`，预期 `dist\\MouseClicker.exe` 存在且文件大小大于 0。

- [ ] **Step 5: 做一次真实 Windows 验收**

启动 exe，创建“测试模板”，录制以下动作：移动到指定点、左键单击、双击、右键、中键、滚轮、按住左键拖动；停止后确认事件数和总时长非零。分别用 1 次和 2 次固定循环回放，确认动作顺序；再用无限循环启动并点击窗口“停止”，确认回放结束且鼠标没有卡在按下状态。最后创建第二套模板，重命名、切换、删除并重新启动 exe 验证模板仍存在。

## Task 9: 最终验证清单

- [ ] **Step 1: 运行完整测试命令**

运行 `python -m unittest discover -s tests -v`，记录通过数量、失败数量和错误数量。

- [ ] **Step 2: 检查工作区文件**

运行 `Get-ChildItem -Recurse -File | Select-Object FullName`，确认源码、测试、规格和计划文件都在项目目录内，没有临时 JSON 或 `.tmp` 文件。

- [ ] **Step 3: 对照验收标准逐项核对**

确认全局录制、完整鼠标事件、绝对坐标、多模板、固定/无限循环、窗口按钮控制、异常清理和 exe 打包均有自动化或人工证据；没有把未执行的人工步骤描述为已通过。

- [ ] **Step 4: 记录当前验证结果**

在最终交付消息中列出实际执行过的命令及输出摘要；若 Windows 集成验收因权限、依赖或桌面状态无法执行，明确列出未验证项和下一步操作。
