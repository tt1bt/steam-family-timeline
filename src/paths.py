"""路径解析：源码运行与 PyInstaller 冻结 exe 两种模式统一处理。

冻结（onefile）成 exe 之后，有两类路径**必须分开**，混在一起会出问题：

- **只读资源**（``web/index.html`` 等打包进来的文件）位于 ``sys._MEIPASS``。
  这是 PyInstaller 每次启动时解压出来的临时目录，**进程一退出就没了**。
- **可写数据**（``appmeta.json`` 元数据缓存、``snapshot.json`` 快照）**不能**放那儿 ——
  否则每次启动都要重新抓几百款游戏的商店元数据，首批加载要几分钟。

所以可写目录优先放在 **exe 同级目录**（便携模式，绿色软件），该位置不可写时
（exe 放在 ``Program Files`` 或只读介质上）退回 ``%LOCALAPPDATA%\\SteamFamilyToolbox``。
"""

from __future__ import annotations

import os
import sys

# PyInstaller 会在运行时给 sys 打上 frozen 标记
FROZEN = bool(getattr(sys, "frozen", False))

#: 数据目录用的名字。和 version.APP_NAME 刻意不同 —— 这里要当文件系统路径用，
#: 不能有空格，改它会连带改变已有用户的缓存位置。
APP_NAME = "SteamFamilyToolbox"


def _resource_root() -> str:
    """只读资源根目录。

    - 冻结：``sys._MEIPASS``（onefile 的解压目录；onedir 模式下不存在，退回 exe 所在目录）
    - 源码：项目根目录（本文件的上一级）
    """
    if FROZEN:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _probe_writable(path: str) -> bool:
    """真的试着写一个文件来判断可写，不要只信权限位。

    Windows 上 ``os.access`` 对目录的 W_OK 判断并不可靠。
    """
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".sft_write_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("x")
        os.remove(probe)
        return True
    except Exception:
        return False


def _data_root() -> str:
    """可写数据根目录。"""
    if not FROZEN:
        return os.path.join(_resource_root(), "data")

    # 便携优先：exe 旁边的 data/
    portable = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "data")
    if _probe_writable(portable):
        return portable

    # 退回用户目录
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    fallback = os.path.join(base, APP_NAME)
    os.makedirs(fallback, exist_ok=True)
    return fallback


RESOURCE_ROOT = _resource_root()
WEB_DIR = os.path.join(RESOURCE_ROOT, "web")
DATA_DIR = _data_root()
SNAPSHOT = os.path.join(DATA_DIR, "snapshot.json")
META_CACHE = os.path.join(DATA_DIR, "appmeta.json")
LOG_FILE = os.path.join(DATA_DIR, "_server.log")


def describe() -> str:
    """给启动 banner 用的一行说明，方便排查「数据到底存哪了」。"""
    mode = "打包 exe" if FROZEN else "源码"
    return f"{mode} | 数据目录 {DATA_DIR}"
