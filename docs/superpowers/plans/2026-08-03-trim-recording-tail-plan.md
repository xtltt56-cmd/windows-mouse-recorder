# 录制末尾三秒自动排除实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在用户点击停止录制时，按真实录制总时长自动排除最后 3000 毫秒的事件，再保存并循环回放裁剪后的模板。

**Architecture:** `RecordingSession` 保留原有事件序列，同时记录每个有效事件相对于录制开始的偏移时间和停止时的总时长，封装为 `RecordingResult`。纯函数 `trim_recorded_tail` 根据停止时刻倒推 3 秒过滤事件；Tkinter 停止录制流程只保存过滤后的事件，播放器、模板 JSON 和快捷方式接口保持不变。

**Tech Stack:** Python 3.8+、标准库 `dataclasses`/`unittest`、现有 `pynput`/Tkinter/Windows API 实现。

---

## 文件结构与变更范围

- Modify: `mouse_clicker/recorder.py`：增加 `RecordingResult`、事件偏移记录、停止时长和末尾裁剪函数。
- Modify: `mouse_clicker/app.py`：停止录制时应用固定 3000ms 裁剪并更新状态文字。
- Modify: `tests/test_recorder.py`：验证停止时长、事件偏移、总时长不受排除窗口影响、裁剪边界和监听器停止时刻。
- Modify: `README.md`：说明停止录制时自动排除末尾三秒。
- Modify: `docs/superpowers/specs/2026-08-03-trim-recording-tail-design.md`：保留已批准设计，无结构修改。
- Create: `dist/MouseClicker.exe`：重新打包覆盖现有 exe，桌面快捷方式仍指向同一绝对路径。

## Task 1: 为录制结果和末尾裁剪编写失败测试

**Files:**

- Modify: `tests/test_recorder.py`

- [ ] **Step 1: 添加停止时长和事件偏移测试**

新增可控时钟测试：

```python
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
```

新增排除窗口测试：事件被过滤时不出现在 `events` 和 `event_times_ms` 中，但 `duration_ms` 仍按停止时刻计算。

- [ ] **Step 2: 添加 `trim_recorded_tail` 边界测试**

构造 `RecordingResult`：总时长 10000ms，事件时间 `[1000, 6999, 7000, 9999]`，裁剪 3000ms 后只保留前两个事件；测试总时长 3000ms 时返回空列表，裁剪 0ms 时返回全部事件，负裁剪时长抛出 `ValueError`，事件数组和时间数组长度不一致时抛出 `ValueError`。

- [ ] **Step 3: 更新监听器返回值测试**

把现有生命周期断言从列表改为 `result.events`，并断言 `result.duration_ms >= 0`，确保 `GlobalMouseRecorder.stop()` 返回完整录制结果。

- [ ] **Step 4: 运行测试确认因接口不存在而失败**

运行：

```powershell
python -m unittest tests.test_recorder -v
```

预期：导入或属性错误，原因是 `RecordingResult` 和 `trim_recorded_tail` 尚未实现，而不是测试语法错误。

## Task 2: 实现录制结果、停止时长和固定三秒裁剪

**Files:**

- Modify: `mouse_clicker/recorder.py`

- [ ] **Step 1: 添加 `RecordingResult` 数据类**

在 `RecorderUnavailableError` 后加入：

```python
from dataclasses import dataclass


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
```

- [ ] **Step 2: 让 `RecordingSession`记录开始时间和事件偏移**

在 `start()` 中记录 `_started_at = self._clock()`，并清空 `_event_times_ms`。在 `_append()` 中，排除区域判断仍然先于时钟更新；有效事件使用 `event_time_ms = round(max(0.0, now - self._started_at) * 1000.0, 3)` 追加到 `_event_times_ms`，原有 `MouseEvent.delay_ms` 计算保持不变。

- [ ] **Step 3: 让 `stop()` 返回稳定的 `RecordingResult`**

首次停止时用传入的 `stop_time` 或当前时钟计算总时长，复制事件和偏移数组并缓存结果；重复调用返回同一结果。固定接口为：

```python
def stop(self, stop_time: Optional[float] = None) -> RecordingResult:
    with self._lock:
        if not self._active and self._cached_result is not None:
            return self._cached_result
        final_time = self._clock() if stop_time is None else stop_time
        duration_ms = round(max(0.0, final_time - self._started_at) * 1000.0, 3)
        self._active = False
        self._cached_result = RecordingResult(
            events=list(self._events),
            event_times_ms=list(self._event_times_ms),
            duration_ms=duration_ms,
        )
        return self._cached_result
```

- [ ] **Step 4: 在全局监听器停止前捕获停止时刻**

`GlobalMouseRecorder.stop()` 先执行 `stop_time = self._clock()`，再停止并 join listener，最后调用 `self.session.stop(stop_time=stop_time)`。这样 listener 清理耗时不会把收尾动作错误地算进或排除出三秒窗口。

- [ ] **Step 5: 添加并实现裁剪纯函数**

实现：

```python
def trim_recorded_tail(result: RecordingResult, tail_ms: float = 3000.0) -> List[MouseEvent]:
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
```

先校验 `RecordingResult` 的数组长度，再执行过滤；不修改原结果对象。

- [ ] **Step 6: 运行录制测试确认通过**

运行 `python -m unittest tests.test_recorder -v`，预期所有录制和裁剪测试通过。

- [ ] **Step 7: 运行全套回归测试**

运行 `python -m unittest discover -s tests -v`，预期现有测试全部通过；若旧测试依赖列表返回值，只修正测试访问 `.events`，不改变播放器或模板格式。

## Task 3: 将裁剪接入停止录制 UI

**Files:**

- Modify: `mouse_clicker/app.py`
- Modify: `tests/test_app_helpers.py`

- [ ] **Step 1: 添加 UI 文案辅助测试**

添加纯函数：

```python
def recording_finished_message(event_count: int) -> str:
    return "录制完成，已排除末尾 3 秒，保存 {} 个事件".format(event_count)
```

测试输入 0 和正整数都包含“已排除末尾 3 秒”和对应数量。

- [ ] **Step 2: 运行辅助测试确认失败**

运行 `python -m unittest tests.test_app_helpers -v`，预期因辅助函数不存在而失败。

- [ ] **Step 3: 实现辅助函数并修改停止录制流程**

从 `recorder` 导入 `trim_recorded_tail`。`_stop_recording()` 接收 `result = self._recording.stop()`，使用 `events = trim_recorded_tail(result)`，用过滤后的事件替换模板并保存；状态栏调用 `recording_finished_message(len(events))`。录制异常时仍恢复 `STATE_IDLE`，原模板文件不被空结果覆盖。

- [ ] **Step 4: 运行辅助和全套测试**

运行：

```powershell
python -m unittest tests.test_app_helpers -v
python -m unittest discover -s tests -v
```

预期新增测试和全部回归测试通过。

## Task 4: 更新说明、重新打包并验证

**Files:**

- Modify: `README.md`
- Modify: `build.ps1`（仅在打包脚本需要同步说明时修改）
- Replace: `dist/MouseClicker.exe`

- [ ] **Step 1: 更新 README 行为说明**

在使用方法和安全提示中写明：点击停止录制时，程序按停止时刻自动忽略最后 3 秒；录制不足 3 秒时会得到空模板，需重新录制。

- [ ] **Step 2: 运行 Python 3.8 和 3.12 全套测试**

运行：

```powershell
python -m unittest discover -s tests -v
py -3.12 -m unittest discover -s tests -v
```

预期两条命令都报告 0 failures、0 errors。

- [ ] **Step 3: 重新生成 exe**

运行 `powershell -ExecutionPolicy Bypass -File .\build.ps1`，预期退出码为 0 且 `dist\MouseClicker.exe` 的修改时间更新。

- [ ] **Step 4: 启动打包程序做烟雾测试**

启动 `dist\MouseClicker.exe`，等待 2 秒确认进程存活，再通过窗口关闭，确认程序退出；不在自动化脚本中发送真实点击，避免污染用户桌面。

## Task 5: 最终验收清单

- [ ] **Step 1: 检查关键文件和桌面快捷方式**

确认 `C:\Users\lenovo\Desktop\MouseClicker.lnk` 仍指向 `C:\Users\lenovo\Documents\New project 2\dist\MouseClicker.exe`。

- [ ] **Step 2: 检查临时文件**

运行 `Get-ChildItem -Recurse -File -Filter '*.tmp'`，预期无输出。

- [ ] **Step 3: 记录真实验证范围**

最终报告列出两套 Python 测试结果、exe 启动结果和裁剪纯函数证据；明确说明真实用户鼠标动作仍需要用户录制第一套模板时在目标软件中验收。
