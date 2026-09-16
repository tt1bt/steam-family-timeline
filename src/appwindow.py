"""把界面开成一个独立窗口，而不是浏览器标签页。

**为什么不用 pywebview / Electron / CEF。** 实测过 pywebview：
源码模式能开窗，但打成单文件 exe 后 WebView2 窗口起不来
（``Main window failed to start``，pythonnet + PyInstaller 的经典坑），
而且 exe 会从 8.85 MB 涨到 14.2 MB、破坏「零第三方依赖」这个定位。
这个工具的价值就在于「下载一个 9 MB 的文件双击就能用」。

**改用系统自带的浏览器跑「应用模式」。** Edge 是 Windows 10/11 自带的，
``--app=URL`` 开出来的是**没有地址栏、没有标签页**的独立窗口，
有标题栏和自己的任务栏项 —— 对外观来说和原生窗口没有区别。
代价：任务栏图标是浏览器的。换来的是零依赖、零体积增长。

顺带把控制台窗口藏起来（双击时不再有个黑窗口杵在后面）。
**崩溃时会自动把控制台显示回来**，所以「出错看得见」这条没有被牺牲。
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys

IS_WINDOWS = os.name == "nt"

#: 常见安装位置。先查注册表拿真实路径，再退回这些。
_EDGE_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
_CHROME_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
)


def _from_registry() -> list[str]:
    """从注册表查 App Paths —— 用户装在非默认位置时靠这个。"""
    if not IS_WINDOWS:
        return []
    import winreg
    found = []
    for exe in ("msedge.exe", "chrome.exe"):
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"):
                try:
                    key = winreg.OpenKey(hive, sub + "\\" + exe)
                    path = winreg.QueryValueEx(key, "")[0]
                    if os.path.isfile(path):
                        found.append(path)
                except OSError:
                    continue
    return found


def find_browser() -> str | None:
    """找一个支持 ``--app`` 的浏览器。Edge 优先（Windows 自带，一定存在）。"""
    for path in _from_registry():
        return path
    for path in _EDGE_PATHS + _CHROME_PATHS:
        if os.path.isfile(path):
            return path
    for name in ("msedge", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    return None


def open_app_window(url: str, width: int, height: int,
                    profile_dir: str) -> subprocess.Popen | None:
    """用应用模式打开独立窗口。

    返回子进程（调用方可以等它退出来决定何时收工），失败返回 None。

    ``--user-data-dir`` 指向我们自己的目录：**不要污染用户正在用的浏览器配置**
    （否则窗口里会带上人家的登录态、还会和已开的窗口互相干扰）。
    """
    exe = find_browser()
    if exe is None:
        return None
    try:
        os.makedirs(profile_dir, exist_ok=True)
    except Exception:
        return None

    args = [
        exe,
        f"--app={url}",
        f"--window-size={width},{height}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        # 下面这些是应用/信息亭模式的常规开关：这个窗口只用来渲染本地页面，
        # 不需要同步、扩展、组件更新、Crashpad 上报。
        # 顺带把 user-data-dir 从 ~40 MB 压到 ~10 MB —— 它会留在用户的 data/ 里。
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-crash-reporter",
        "--disable-extensions",
        "--disable-sync",
        "--no-service-autorun",
        "--disable-features=Translate,TranslateUI,MediaRouter,OptimizationHints",
    ]
    try:
        return subprocess.Popen(args, close_fds=True)
    except Exception:
        return None


# ------------------------------------------------------------ 控制台窗口

def _console_hwnd():
    if not IS_WINDOWS:
        return 0
    try:
        return ctypes.windll.kernel32.GetConsoleWindow()
    except Exception:
        return 0


def has_console() -> bool:
    """是否真的有一个控制台窗口。

    从管道、服务、后台任务启动时 ``GetConsoleWindow()`` 返回 0 ——
    那既不是「可见」也不是「被隐藏」，报告时要区分开，别让用户以为被藏了。
    """
    return bool(_console_hwnd())


def hide_console() -> bool:
    """藏掉控制台窗口。只在确实是控制台程序时有效（GUI 构建下返回 False）。"""
    hwnd = _console_hwnd()
    if not hwnd:
        return False
    try:
        ctypes.windll.user32.ShowWindow(hwnd, 0)   # SW_HIDE
        return True
    except Exception:
        return False


def show_console() -> bool:
    """把控制台显示回来并存活 —— 出错时要让人看得到报告。"""
    hwnd = _console_hwnd()
    if not hwnd:
        return False
    try:
        ctypes.windll.user32.ShowWindow(hwnd, 5)   # SW_SHOW
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def is_console_visible() -> bool:
    hwnd = _console_hwnd()
    if not hwnd:
        return False
    try:
        return bool(ctypes.windll.user32.IsWindowVisible(hwnd))
    except Exception:
        return False


def set_window_title(title: str) -> None:
    """给控制台窗口改个名字（出错重新显示时，标题要能说明是哪来的）。"""
    hwnd = _console_hwnd()
    if not hwnd:
        return
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass
