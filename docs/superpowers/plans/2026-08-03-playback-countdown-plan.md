# 回放前 5 秒倒计时 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在点击“开始回放”后增加可取消的固定 5 秒倒计时，倒计时结束后才启动现有鼠标模板回放。

**Architecture:** 在 Tkinter 主线程中新增独立的 `playback_countdown` 状态和 `after()` 定时任务。开始回放时先完成现有校验并保存已校验的模板/循环配置，倒计时期间不启动播放器；倒计时结束后调用原有 `PlaybackEngine.start()`。窗口“停止”按钮在倒计时状态下负责取消待启动任务。

**Tech Stack:** Python 3.8+、Tkinter、现有 `PlaybackEngine`/Win32 `SendInput` 后端、Python `unittest`、PyInstaller。

---

## 文件结构与职责

- Modify: `tests/test_app_helpers.py` — 为倒计时提示文本和新增状态的启动资格增加回归测试。
- Create: `tests/test_app_countdown.py` — 用假的 Tk `after()` 调度器验证 5 秒延迟和停止取消，不触发真实鼠标。
- Modify: `mouse_clicker/app.py` — 增加 5 秒回放倒计时、取消逻辑、状态显示和控件锁定。
- Modify: `README.md` — 说明开始回放前固定等待 5 秒及取消方式。
- Create: `docs/superpowers/specs/2026-08-03-playback-countdown-design.md` — 已批准的行为规格。
- Create: `docs/superpowers/plans/2026-08-03-playback-countdown-plan.md` — 本实现计划。
- Regenerate: `dist/MouseClicker.exe` — 通过既有 `build.ps1` 重新生成打包程序。

## 约定

- 保持录制前的 `STATE_COUNTDOWN` 和 3 秒录制准备时间不变。
- 新增 `STATE_PLAYBACK_COUNTDOWN = "playback_countdown"`，不复用录制定时器句柄。
- 倒计时固定为 `PLAYBACK_COUNTDOWN_SECONDS = 5`，不增加新的用户设置。
- 由于当前工作区没有 Git 仓库，本计划使用测试、构建和运行检查作为检查点，不执行 Git 提交。

### Task 1: 先锁定倒计时的纯逻辑契约

**Files:**
- Modify: `tests/test_app_helpers.py`
- Test: `tests/test_app_helpers.py`

- [ ] **Step 1: 写入失败测试**

在现有导入中加入 `STATE_PLAYBACK_COUNTDOWN` 和 `playback_countdown_message`，并加入以下测试；同时把新增状态加入既有的录制/回放不可启动断言：

```python
from mouse_clicker.app import (
    STATE_PLAYBACK_COUNTDOWN,
    can_start_playback,
    can_start_recording,
    parse_loop_input,
    playback_countdown_message,
    recording_finished_message,
)


class AppHelperTest(unittest.TestCase):
    def test_recording_can_start_only_when_idle(self):
        self.assertTrue(can_start_recording("idle"))
        self.assertFalse(can_start_recording("countdown"))
        self.assertFalse(can_start_recording("recording"))
        self.assertFalse(can_start_recording("playing"))
        self.assertFalse(can_start_recording(STATE_PLAYBACK_COUNTDOWN))

    def test_playback_requires_idle_state_and_events(self):
        self.assertTrue(can_start_playback("idle", 1))
        self.assertFalse(can_start_playback("idle", 0))
        self.assertFalse(can_start_playback("recording", 1))
        self.assertFalse(can_start_playback("paused", 1))
        self.assertFalse(can_start_playback(STATE_PLAYBACK_COUNTDOWN, 1))

    def test_playback_countdown_message_shows_remaining_seconds(self):
        self.assertEqual(
            playback_countdown_message(5), "回放将在 5 秒后开始"
        )
        self.assertEqual(
            playback_countdown_message(1), "回放将在 1 秒后开始"
        )
```

保留该文件中已有的循环配置和录制完成提示测试，不删除原有覆盖。

- [ ] **Step 2: 运行失败测试，确认缺少新契约**

Run:

```powershell
py -3.12 -m unittest tests.test_app_helpers -v
```

Expected: FAIL during import because `STATE_PLAYBACK_COUNTDOWN` 和 `playback_countdown_message` 尚未定义。

### Task 2: 实现可取消的 5 秒回放倒计时

**Files:**
- Modify: `mouse_clicker/app.py`
- Create: `tests/test_app_countdown.py`

- [ ] **Step 1: 添加常量、状态和纯提示函数**

在现有状态常量之后加入：

```python
STATE_PLAYBACK_COUNTDOWN = "playback_countdown"
PLAYBACK_COUNTDOWN_SECONDS = 5
```

在 `recording_finished_message` 后加入：

```python
def playback_countdown_message(seconds: int) -> str:
    return "回放将在 {} 秒后开始".format(seconds)
```

- [ ] **Step 2: 添加倒计时实例字段并保存无限循环控件**

在 `__init__` 的录制定时字段后加入：

```python
self._playback_countdown_job = None
self._playback_countdown_remaining = 0
self._pending_playback = None
```

把界面中内联创建的 `ttk.Checkbutton` 保存为 `self._infinite_checkbutton`，其文本、变量和布局保持不变：

```python
self._infinite_checkbutton = ttk.Checkbutton(
    playback_frame,
    text="无限循环",
    variable=self._infinite_var,
)
self._infinite_checkbutton.grid(row=0, column=2, sticky="w", padx=(10, 0))
```

并把录制提示改为明确区分两种等待：

```python
text="录制前倒计时 3 秒；开始回放前倒计时 5 秒。连点器窗口中的按钮不会被录入。",
```

- [ ] **Step 3: 让开始回放先进入倒计时，而不是立即启动播放器**

保留现有模板、循环参数和屏幕布局校验；将 `_start_playback` 校验成功后的结尾替换为：

```python
            self._pending_playback = (template, config)
            self._playback_countdown_remaining = PLAYBACK_COUNTDOWN_SECONDS
            self._progress_var.set("准备回放：{}".format(template.name))
            self._set_state(STATE_PLAYBACK_COUNTDOWN)
            self._playback_countdown_step()
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("无法开始回放", str(exc), parent=self.root)
```

新增 `_playback_countdown_step`，使用 `after(1000, ...)`，每次只更新界面，不调用播放器或输入后端；计数到 0 后才调用现有播放器：

```python
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
```

- [ ] **Step 4: 使“停止”可取消倒计时并清理待启动数据**

新增取消辅助方法，并在 `_stop_playback` 开头处理新状态：

```python
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
```

- [ ] **Step 5: 更新状态文本、控件启用规则和关闭流程**

在 `_set_state` 的状态映射中加入：

```python
STATE_PLAYBACK_COUNTDOWN: "准备回放",
```

在 `_update_controls` 中加入无限循环复选框的状态同步，并把停止按钮的可用状态扩展为：

```python
self._set_widget_state(self._infinite_checkbutton, idle)
self._set_widget_state(
    self._play_stop_button,
    self._state
    in (STATE_PLAYING, STATE_PAUSED, STATE_PLAYBACK_COUNTDOWN),
)
```

在 `_close` 中、停止录制器和播放器之前调用：

```python
self._cancel_playback_countdown()
```

这样关闭窗口会取消 Tk 定时器、清除待启动模板/配置，并继续执行既有的录制器和播放器清理。

- [ ] **Step 6: 用假的窗口调度器验证时序和取消**

在 `tests/test_app_countdown.py` 中使用假的 `after()` 根对象、状态变量和播放器，验证播放器在前五次调度回调中不会启动，第五秒结束后的回调才启动；验证调用 `_stop_playback()` 会取消定时器、清除待启动数据并且不启动播放器。

Run:

```powershell
py -3.12 -m unittest tests.test_app_countdown -v
```

Expected: 2 个测试全部通过。

- [ ] **Step 7: 运行目标测试，确认契约通过**

Run:

```powershell
py -3.12 -m unittest tests.test_app_helpers tests.test_app_countdown -v
```

Expected: PASS，8 个测试全部通过；其中回放倒计时提示测试覆盖 5 秒和 1 秒，调度器测试确认未到 5 秒不会启动播放器且停止可以取消，录制/回放资格测试确认 `playback_countdown` 不能重入。

### Task 3: 更新使用说明

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新使用步骤**

把“点击开始回放”步骤改为：

```markdown
5. 点击“开始回放”。程序先倒计时 5 秒，倒计时期间不会操作鼠标；需要取消时点击“停止”，倒计时结束后才开始回放。回放过程中可使用“暂停/继续/停止”。
```

在安全提示中加入：

```markdown
- 回放开始前固定等待 5 秒，倒计时期间不会注入鼠标事件。
```

- [ ] **Step 2: 检查文档变更内容**

Run:

```powershell
Select-String -Path README.md -Pattern '倒计时 5 秒|回放开始前固定等待 5 秒|点击“停止”'
```

Expected: 至少输出使用步骤和安全提示中的两处 5 秒说明。

### Task 4: 全量测试、打包和运行验证

**Files:**
- Regenerate: `dist/MouseClicker.exe`
- Verify: `C:\Users\lenovo\Desktop\MouseClicker.lnk`

- [ ] **Step 1: 运行默认 Python 的全量测试**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: 44 tests, 0 failures, 0 errors。

- [ ] **Step 2: 用打包所用 Python 3.12 再跑全量测试**

Run:

```powershell
py -3.12 -m unittest discover -s tests -v
```

Expected: 44 tests, 0 failures, 0 errors。

- [ ] **Step 3: 重新构建 Windows 可执行文件**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Expected: 命令成功结束，`dist\MouseClicker.exe` 的修改时间更新，文件存在且大小大于 0。

- [ ] **Step 4: 启动打包程序进行 UI 烟雾测试**

Run:

```powershell
$process = Start-Process -FilePath '.\dist\MouseClicker.exe' -PassThru
Start-Sleep -Seconds 2
$running = -not $process.HasExited
if ($running) {
    Stop-Process -Id $process.Id
}
"running_after_2s=$running"
```

Expected: 输出 `running_after_2s=True`，随后进程可以被安全结束；本步骤不触发真实鼠标点击。

- [ ] **Step 5: 验证桌面快捷方式仍指向最新程序**

Run:

```powershell
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('C:\Users\lenovo\Desktop\MouseClicker.lnk')
"target=$($shortcut.TargetPath)"
```

Expected: `target=C:\Users\lenovo\Documents\New project 2\dist\MouseClicker.exe`。

- [ ] **Step 6: 确认构建没有残留临时文件**

Run:

```powershell
(Get-ChildItem -Path . -Filter '*.tmp' -File -Recurse -ErrorAction SilentlyContinue).Count
```

Expected: `0`。
