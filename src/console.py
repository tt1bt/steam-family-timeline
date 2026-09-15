"""控制台输出：编码安全 + 日志留存 + 崩溃可见。

这里解决三类问题，都是**双击 exe 运行时才会暴露**的：

1. **GBK 编码崩** —— Windows 中文版控制台默认编码是 **cp936**。游戏名里带 `™`、`é`、
   `Ō` 这类字符时，``print()`` 会抛 ``UnicodeEncodeError``。实测过：exe 冷启动抓到
   第 25 款游戏（Apex Legends™）就崩掉了整个采集。
   这在 Git Bash 里跑源码**永远复现不了** —— 那边 stdout 是管道、编码 UTF-8。

2. **窗口一闪而过看不到错** —— 双击启动时如果崩了，控制台窗口随进程退出一起消失，
   用户只看到「弹出来又关了」，拿不到任何信息，只能来问「没反应」。

3. **日志要能留下来** —— 出错时得有个文件留下痕迹，方便远程排查。

对应 :func:`setup` / :func:`say` / :func:`tee_to_file`，
再加 :func:`pause_before_exit` 负责「别关窗口」。
"""

from __future__ import annotations

import os
import sys
import traceback

#: pause_before_exit 只生效一次，避免多层兜底时连等几次
_paused = False


def setup() -> None:
    """把 stdout / stderr 切到 UTF-8 + errors='replace'。

    要在任何 ``print`` 之前调用。失败不抛 —— 重定向到文件等情况本就不支持
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
    """安全打印。编码失败时降级而不是抛异常。

    日志打印绝不该能搞死主流程 —— 一行 debug 输出把整个任务带崩是很蠢的失败方式。
    """
    try:
        print(msg, flush=True)
    except Exception:
        try:
            sys.stdout.write(msg.encode("ascii", "replace").decode("ascii") + "\n")
            sys.stdout.flush()
        except Exception:
            pass


class _Tee:
    """把输出同时写到原流和日志文件。

    日志文件是崩溃排查的**唯一线索** —— 双击启动时窗口会消失，只有文件留下来。

    ⚠️ stdout 和 stderr 必须共用**同一个文件句柄**。各自 open 一次的话，
    两个句柄各自维护文件偏移量，会互相覆盖对方刚写的内容 ——
    表现就是日志里内容是乱的、甚至中文被截成半个字。
    """

    def __init__(self, stream, fh, owns: bool = False):
        self._stream = stream
        self._fh = fh
        self._owns = owns

    def write(self, s):
        try:
            self._stream.write(s)
        except Exception:
            pass
        if self._fh is not None:
            try:
                self._fh.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        for target in (self._stream, self._fh):
            if target is None:
                continue
            try:
                target.flush()
            except Exception:
                pass

    def isatty(self):
        try:
            return bool(self._stream.isatty())
        except Exception:
            return False

    def close(self):
        if self._owns and self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass

    def __getattr__(self, name):
        # 转发 encoding / fileno / reconfigure / buffer 等属性给原流
        return getattr(self._stream, name)


def tee_to_file(path: str) -> bool:
    """开始把 stdout/stderr 镜像到 ``path``。

    每次运行**覆盖**，只保留最新一次 —— 排查问题时关心的是「这次为什么崩」。
    返回是否成功。
    """
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        # 只打开一次，stdout / stderr 共用（见 _Tee 的说明）
        fh = open(path, "w", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        return False

    ok = False
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        setattr(sys, name, _Tee(stream, fh))
        ok = True
    return ok


def pause_before_exit(message: str = "按回车键关闭这个窗口... ") -> None:
    """等一次按键，让用户能读完错误信息再关窗口。

    只在**交互式控制台**里等 —— 脚本 / CI 调用时 stdin 不是 tty，直接跳过，
    否则会把自动化流程卡死。
    """
    global _paused
    if _paused:
        return
    _paused = True

    try:
        if sys.stdin is None or not sys.stdin.isatty():
            return
    except Exception:
        return

    try:
        print(f"\n{message}", end="", flush=True)
        input()
    except (EOFError, KeyboardInterrupt, OSError):
        pass
    except Exception:
        pass


def report_crash(exc: BaseException, log_path: str | None = None) -> None:
    """把崩溃信息清楚地打出来 —— 这是用户唯一能看到的东西，别只丢个 traceback。"""
    say("")
    say("=" * 62)
    say("  启动失败")
    say("=" * 62)
    say("")
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    say("")
    say(f"  错误类型：{type(exc).__name__}")
    say(f"  错误信息：{exc}")
    if log_path:
        say(f"  日志文件：{log_path}")
    say("")
    say("  排查建议：")
    say("   1. 把上面这段内容（或日志文件）贴到 issue 里")
    say("   2. 确认本机装过并登录过 Steam")
    say("   3. 换一个确定可写的目录再试，例如桌面新建的文件夹")
    say("   4. 如果是杀毒软件拦截，把 exe 加入白名单后重试")
    say("=" * 62)


def install_excepthook(log_path: str | None = None) -> None:
    """兜底：任何未捕获异常都打出来并留住窗口。"""
    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        report_crash(exc, log_path)
        pause_before_exit()
    sys.excepthook = _hook
