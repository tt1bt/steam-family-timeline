"""控制台输出：让中文与特殊字符在 Windows 的 GBK 控制台下也不会炸。

背景：Windows 中文版的控制台默认编码是 **GBK (cp936)**。游戏名里带 `™`、`é`、`Ō`
这类字符时，``print()`` 会抛 ``UnicodeEncodeError``。

这个问题**只在打包成 exe、双击运行时才暴露** —— 在 Git Bash 里跑源码时 stdout
是管道、编码为 UTF-8，怎么打都不会出错。实测过：exe 冷启动抓到第 25 款游戏时
遇到 `Apex Legends™` 直接崩掉整个采集。

两道防线：

1. :func:`setup` 把 stdout/stderr 切到 UTF-8，从源头解决
2. :func:`say` 兜底：万一还是失败，也绝不让一行日志把采集搞挂
"""

from __future__ import annotations

import sys


def setup() -> None:
    """把 stdout / stderr 切到 UTF-8 + errors='replace'。

    要在任何 ``print`` 之前调用。失败也不抛 —— 重定向到文件等情况本就不支持
    ``reconfigure``。
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def say(msg: str = "") -> None:
    """安全打印。编码失败时降级而不是抛异常。"""
    try:
        print(msg, flush=True)
    except Exception:
        try:
            sys.stdout.write(msg.encode("ascii", "replace").decode("ascii") + "\n")
            sys.stdout.flush()
        except Exception:
            pass
