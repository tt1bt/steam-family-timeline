"""本地 HTTP 服务：提供 API 与前端页面。

启动后浏览器打开 http://127.0.0.1:8765/ 即可看到界面。

只监听 127.0.0.1，不对外暴露。数据全部来自本机 Steam 客户端。
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import console  # noqa: E402
import paths  # noqa: E402
import version  # noqa: E402
import build as builder  # noqa: E402

WEB_DIR = paths.WEB_DIR
DATA_DIR = paths.DATA_DIR
SNAPSHOT = paths.SNAPSHOT
LOG_FILE = paths.LOG_FILE

_state = {"data": None, "lock": threading.Lock(), "building": False,
          "error": None, "progress": {"stage": "", "done": 0, "total": 0}}


def _read_snapshot_file():
    """从磁盘读快照，**并校验它是不是当前版本能用的**。

    返回 ``(快照或 None, 不可用的原因或 None)``。

    为什么要校验：快照是长期缓存，而新版会往里加分析块。如果不校验，
    老用户升级后程序会直接复用旧结构的快照，新加的视图一片空白 ——
    症状很迷惑（界面没问题、也不报错，就是没数据）。
    这类「静默空白」比崩溃更难排查，所以宁可多花几秒重新聚合。

    注意 ``summary.version`` **不能**当判断依据：那是应用版本，
    和快照结构不是一回事（同一个应用版本也可能改结构）。
    """
    if not os.path.isfile(SNAPSHOT):
        return None, "没有快照"
    try:
        with open(SNAPSHOT, "r", encoding="utf-8") as fh:
            snap = json.load(fh)
    except Exception:
        return None, "快照损坏，读不出来"
    if not isinstance(snap, dict):
        return None, "快照格式不对"

    got = snap.get("schema")
    if got != builder.SNAPSHOT_SCHEMA:
        if got is None:
            return None, "快照是旧版本生成的（没有格式版本号）"
        return None, f"快照格式版本不匹配（{got} != {builder.SNAPSHOT_SCHEMA}）"

    missing = [k for k in builder.SNAPSHOT_REQUIRED_KEYS if k not in snap]
    if missing:
        return None, "快照缺少字段：" + "、".join(missing)

    return snap, None


def _on_progress(stage: str, done: int, total: int) -> None:
    _state["progress"] = {"stage": stage, "done": done, "total": total}


def _build_worker() -> None:
    """后台线程：采集数据并落盘。"""
    import traceback
    try:
        data = builder.build(refresh_meta=True, resolve_names=True, verbose=True,
                             progress=_on_progress)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SNAPSHOT, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        _state["data"] = data
        print(f"\n采集完成：{data['summary']['group_name']} / "
              f"{data['summary']['game_count']} 款共享游戏。页面已就绪。\n")
    except Exception as exc:  # noqa: BLE001
        _state["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        _state["building"] = False


def start_build() -> None:
    """启动后台采集（已在采集就不重复起）。"""
    with _state["lock"]:
        if _state["building"]:
            return
        _state["building"] = True
        _state["error"] = None
    threading.Thread(target=_build_worker, daemon=True).start()


def get_snapshot():
    """取快照。**不阻塞**：还没准备好就返回 None，让前端去轮询。

    首次运行要抓几百款游戏的商店元数据，同步等待会让用户盯着一个没有浏览器的
    黑窗口好几分钟。所以这里只负责「有可用缓存就加载，否则起后台线程」。

    快照过期时**不必重新抓元数据** —— 元数据有独立缓存（appmeta.json），
    ``fetch_missing`` 只补缺的，所以升级后重新聚合通常只要几秒。
    """
    if _state["data"] is None and not _state["building"]:
        cached, why = _read_snapshot_file()
        if cached is not None:
            _state["data"] = cached
        else:
            if why and why != "没有快照":
                console.say(f"  [info] 需要重新聚合本地数据：{why}")
            start_build()
    return _state["data"]


class Handler(BaseHTTPRequestHandler):
    server_version = f'SteamFamilyToolbox/{version.__version__}'

    def log_message(self, fmt, *args):
        if os.environ.get("SFT_VERBOSE"):
            sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

    # ---------------------------------------------------------- helpers
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _file(self, path: str):
        if not os.path.isfile(path):
            self._send(404, b"404 Not Found", "text/plain; charset=utf-8")
            return
        ext = os.path.splitext(path)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
        with open(path, "rb") as fh:
            self._send(200, fh.read(), ctype)

    # ---------------------------------------------------------- routes
    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        try:
            if route in ("/", "/index.html"):
                self._file(os.path.join(WEB_DIR, "index.html"))
            elif route == "/api/timeline":
                if query.get("refresh", ["0"])[0] == "1":
                    _state["data"] = None
                    start_build()
                snap = get_snapshot()
                if snap is None:
                    # 还在采集：503 + 进度，前端据此显示进度并继续轮询
                    self._json({"building": _state["building"],
                                "error": _state["error"],
                                "progress": _state["progress"]}, 503)
                else:
                    self._json(snap)
            elif route == "/api/health":
                self._json({"ok": True, "building": _state["building"],
                            "has_data": _state["data"] is not None,
                            "error": _state["error"],
                            "progress": _state["progress"],
                            "version": version.__version__})
            elif route == "/api/raw":
                # 原始事件文本，方便自己再加工
                snap = get_snapshot()
                if snap is None:
                    self._json({"error": "still building"}, 503)
                    return
                self._json([{"ts": t["ts"], "kind": t["kind"], "appid": t["appid"],
                             "owner": t["owner"], "raw": t["raw"]}
                            for t in snap["timeline"]])
            else:
                # 静态资源，防目录穿越
                rel = route.lstrip("/")
                target = os.path.normpath(os.path.join(WEB_DIR, rel))
                if not target.startswith(os.path.normpath(WEB_DIR)):
                    self._send(403, b"403", "text/plain; charset=utf-8")
                    return
                self._file(target)
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self._json({"error": str(exc)}, 500)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # ⚠️ Windows 上 SO_REUSEADDR 的语义和 POSIX **不一样**：它允许「抢占」一个
    # 已经被别的进程监听的端口，结果两个实例同时绑同一个端口，请求随机落到
    # 其中一个，表现就是「有时候数据不对」。POSIX 下它只是允许复用 TIME_WAIT，
    # 是安全的。所以这里按平台区分。
    allow_reuse_address = (os.name != "nt")


# 本机请求要绕过系统代理，否则会被代理拦成 502
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _is_addr_in_use(exc: OSError) -> bool:
    """判断异常是不是「端口已被占用」。Windows 走 winerror，别只看 errno。"""
    return (getattr(exc, "errno", None) == errno.EADDRINUSE
            or getattr(exc, "winerror", None) == 10048
            or "10048" in str(exc))


def probe_existing(host: str, port: int, timeout: float = 1.5):
    """如果这个端口上已经跑着一个本工具的实例，返回它的 /api/health 字典。

    用来区分「端口被别的程序占了」和「我自己已经开着了」——
    后者不该报错，直接把浏览器打开就好。
    """
    url = f"http://{host}:{port}/api/health"
    try:
        with _LOCAL_OPENER.open(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    # 认出自己：/api/health 是我们特有的字段组合
    if isinstance(data, dict) and data.get("ok") is True and "version" in data:
        return data
    return None


def main():
    # Windows 中文控制台是 GBK，游戏名里的 ™ 之类会 print 失败，先切 UTF-8
    console.setup()

    ap = argparse.ArgumentParser(description=f"{version.APP_NAME} - 本地服务")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="启动时强制重新采集")
    ap.add_argument("--rebuild", action="store_true", help="只重新生成快照后退出")
    ap.add_argument("--selftest", action="store_true",
                    help="打印环境自检信息后退出（报 bug 时贴这个）")
    ap.add_argument("--no-pause", action="store_true",
                    help="出错时不等待按键（脚本/CI 用）")
    ap.add_argument("--version", action="version",
                    version=f"{version.APP_NAME} v{version.__version__}")
    args = ap.parse_args()

    if args.selftest:
        print_selftest()
        return

    # 框线宽度按标题长度算，改名字/版本号不会错位。
    # 注意 APP_NAME 目前是纯 ASCII，len() 就等于显示宽度；若以后改成中文名，
    # 这里要换成 wcwidth 之类的宽度计算。
    title = f"{version.APP_NAME}  v{version.__version__}"
    inner = max(len(title) + 2, 42)
    banner = "\n".join((
        "  ╔" + "═" * inner + "╗",
        "  ║ " + title.ljust(inner - 1) + "║",
        "  ╚" + "═" * inner + "╝",
    ))

    if args.rebuild:
        snap = build_snapshot_fresh()
        s = snap["summary"]
        print(f"家庭组 {s['group_name']}：{s['member_count']} 人 / "
              f"{s['game_count']} 款游戏 / {s['event_count']} 条事件")
        print(f"快照已写入 {SNAPSHOT}")
        return

    print(banner)
    print(f"  {paths.describe()}")
    print(f"  日志文件 {paths.LOG_FILE}\n")

    # 已经有一个实例在跑？直接把浏览器打开，别去抢端口。
    # 双击两次是很常见的操作，不该报个错就把窗口关了。
    existing = probe_existing(args.host, args.port)
    if existing is not None:
        url = f"http://{args.host}:{args.port}/"
        print(f"检测到本工具已经在运行（v{existing.get('version')}）")
        print(f"直接打开已有的页面：{url}")
        print("如果你想同时跑第二个实例，用 --port 换一个端口。\n")
        if not args.no_browser:
            webbrowser.open(url)
        return

    # 换端口重试：被别的程序占用时自动往后找
    httpd = None
    port = args.port
    for offset in range(20):
        port = args.port + offset
        try:
            httpd = Server((args.host, port), Handler)
            break
        except OSError as exc:
            if not _is_addr_in_use(exc):
                raise
            if offset == 0:
                print(f"端口 {port} 已被其他程序占用，尝试往后找...")
            # 占用者可能正好是我们自己的另一个实例
            existing = probe_existing(args.host, port)
            if existing is not None:
                url = f"http://{args.host}:{port}/"
                print(f"端口 {port} 上已有本工具在运行，直接打开：{url}")
                if not args.no_browser:
                    webbrowser.open(url)
                return
    if httpd is None:
        raise RuntimeError(
            f"端口 {args.port}–{args.port + 19} 全被占用，"
            "请用 --port 指定一个空闲端口")

    if port != args.port:
        print(f"已改用端口 {port}\n")

    if args.refresh:
        _state["data"] = None
        start_build()

    # 先把 HTTP 服务起起来，采集在后台跑。首次运行要抓几百款游戏的元数据，
    # 同步等会让用户盯着一个没浏览器的黑窗口好几分钟。
    snap = get_snapshot()
    if snap is None:
        print("正在采集 Steam 本地数据并抓取游戏元数据（首次运行需要几分钟）...")
        print("浏览器会自动打开，页面里会显示进度。这个窗口别关。\n")
    else:
        s = snap["summary"]
        print(f"家庭组：{s['group_name']}（{s['group_id']}）")
        print(f"成员 {s['member_count']} 人 | 共享游戏 {s['game_count']} 款 | "
              f"启动记录 {s['launch_count']} 次 | 时间线 {s['event_count']} 条")
        print(f"Steam 目录：{s['steam_root']}")

    url = f"http://{args.host}:{port}/"
    print(f"\n服务已启动 -> {url}")
    print("按 Ctrl+C 停止\n")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


def build_snapshot_fresh() -> dict:
    """同步完整采集并落盘（给 --rebuild 用）。"""
    data = builder.build(refresh_meta=True, resolve_names=True, verbose=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SNAPSHOT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    _state["data"] = data
    return data


def print_selftest() -> None:
    """打印环境自检信息。

    用途有两个：一是让用户遇到「双击没反应」时能一键把环境状况贴出来
    （日志可能根本写不出来，这个命令的产出是最后一道线索）；
    二是我自己验证打包结果 —— 比如 exe 里烧进去的 User-Agent 是不是新的。
    """
    import platform

    say = console.say
    say("")
    say("=" * 62)
    say(f"  {version.APP_NAME} v{version.__version__}  环境自检")
    say("=" * 62)
    say("")
    say("【程序】")
    say(f"  打包模式      : {'单文件 exe' if paths.FROZEN else '源码'}")
    say(f"  可执行文件    : {sys.executable}")
    say(f"  只读资源目录  : {paths.RESOURCE_ROOT}")
    say(f"  前端页面      : {os.path.join(paths.WEB_DIR, 'index.html')}"
        f"  {'✓ 存在' if os.path.isfile(os.path.join(paths.WEB_DIR, 'index.html')) else '✗ 缺失'}")
    say(f"  项目主页      : {version.REPO_URL}")
    say(f"  User-Agent    : {version.USER_AGENT}")
    say("")
    say("【路径】")
    say(f"  数据目录      : {paths.DATA_DIR}")
    say(f"  ├ 可写        : {'✓' if _writable(paths.DATA_DIR) else '✗ 不可写！'}")
    say(f"  ├ 元数据缓存  : {paths.META_CACHE}"
        f"  {'✓' if os.path.isfile(paths.META_CACHE) else '（首次运行会生成）'}")
    say(f"  ├ 快照        : {paths.SNAPSHOT}"
        f"  {'✓' if os.path.isfile(paths.SNAPSHOT) else '（尚未生成）'}")
    say(f"  └ 日志        : {paths.LOG_FILE}")
    say("")
    say("【运行环境】")
    say(f"  Python        : {sys.version.split()[0]}")
    say(f"  平台          : {platform.platform()}")
    say(f"  控制台编码    : {getattr(sys.stdout, 'encoding', '?')}")
    say(f"  stdin 是终端  : {_safe_isatty()}")
    say("")
    say("【Steam】")
    env = os.environ.get("STEAM_FAMILY_STEAM_PATH")
    say(f"  环境变量覆盖  : {env or '（未设置）'}")
    try:
        import steam_data as sd
        root = sd.read_steam_env() or sd.find_steam_root()
        say(f"  检测到根目录  : {root or '✗ 没找到'}")
        if root:
            log = os.path.join(root, "logs", "librarysharing_log.txt")
            say(f"  ├ steam.exe   : {'✓' if os.path.isfile(os.path.join(root, 'steam.exe')) else '✗'}")
            say(f"  ├ 共享日志    : {log}")
            if os.path.isfile(log):
                size = os.path.getsize(log)
                say(f"  │  └ 大小     : {size:,} 字节"
                    f"{'  ⚠ 空的，本机可能没用过家庭共享' if size == 0 else ''}")
            else:
                say("  │  └ ✗ 不存在，本机没有家庭共享记录")
            ud = os.path.join(root, "userdata")
            if os.path.isdir(ud):
                accounts = [d for d in os.listdir(ud) if d.isdigit()]
                say(f"  └ userdata    : {len(accounts)} 个账号目录")
    except Exception as exc:  # noqa: BLE001
        say(f"  检测失败      : {type(exc).__name__}: {exc}")
    say("")
    say("【网络】")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        val = os.environ.get(key)
        if val:
            say(f"  {key:<14}: {val}")
    say("  （上面为空说明直连）")
    say("")
    say("=" * 62)


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".sft_selftest")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("x")
        os.remove(probe)
        return True
    except Exception:
        return False


def _safe_isatty() -> bool:
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def run() -> int:
    """带全套兜底的入口：编码、日志、崩溃可见、不静默关窗口。"""
    # Windows 中文控制台是 GBK，游戏名里的 ™ 之类会 print 失败，先切 UTF-8
    console.setup()

    # 把输出镜像到日志。双击启动时窗口会消失，日志是唯一线索。
    log_ok = console.tee_to_file(paths.LOG_FILE)
    log_path = paths.LOG_FILE if log_ok else None
    console.install_excepthook(log_path)

    # 双击启动时崩了窗口会立刻关掉，用户什么都看不到 —— 这里等他读完
    no_pause = "--no-pause" in sys.argv

    try:
        main()
        return 0
    except KeyboardInterrupt:
        console.say("\n已停止。")
        return 130
    except SystemExit as exc:                 # --version / --help
        return int(exc.code or 0)
    except BaseException as exc:              # noqa: BLE001
        console.report_crash(exc, log_path)
        if not no_pause:
            console.pause_before_exit()
        return 1


if __name__ == "__main__":
    sys.exit(run())
