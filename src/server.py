"""本地 HTTP 服务：提供 API 与前端页面。

启动后浏览器打开 http://127.0.0.1:8765/ 即可看到家庭组时间线。

只监听 127.0.0.1，不对外暴露。数据全部来自本机 Steam 客户端。
"""

from __future__ import annotations

import argparse
import json
import os
import socketserver
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

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
    """从磁盘读快照。读到返回 dict，读不到或坏了返回 None。"""
    if not os.path.isfile(SNAPSHOT):
        return None
    try:
        with open(SNAPSHOT, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


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
    黑窗口好几分钟。所以这里只负责「有缓存就加载，没有就起后台线程」。
    """
    if _state["data"] is None and not _state["building"]:
        cached = _read_snapshot_file()
        if cached is not None:
            _state["data"] = cached
        else:
            start_build()
    return _state["data"]


class Handler(BaseHTTPRequestHandler):
    server_version = f"SteamFamilyToolbox/{version.__version__}"

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
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser(description="Steam 家庭组工具箱 - 本地服务")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="启动时强制重新采集")
    ap.add_argument("--rebuild", action="store_true", help="只重新生成快照后退出")
    ap.add_argument("--version", action="version",
                    version=f"Steam 家庭组工具箱 v{version.__version__}")
    args = ap.parse_args()

    banner = r"""
   ____  _             _____                     _
  / ___|| |_ ___  __ _|  ___|_ _ _ __ ___  _   _| |_   _  ___
  \___ \| __/ _ \/ _` | |_ / _` | '_ ` _ \| | | | | | | |/ _ \
   ___) | ||  __/ (_| |  _| (_| | | | | | | |_| | | |_| |  __/
  |____/ \__\___|\__,_|_|  \__,_|_| |_| |_|\__, |_|\__, |\___|
                                           |___/  |___/
"""

    if args.rebuild:
        snap = build_snapshot_fresh()
        s = snap["summary"]
        print(f"家庭组 {s['group_name']}：{s['member_count']} 人 / "
              f"{s['game_count']} 款游戏 / {s['event_count']} 条事件")
        print(f"快照已写入 {SNAPSHOT}")
        return

    print(banner)
    print(f"  Steam 家庭组工具箱 v{version.__version__}")
    print(f"  {paths.describe()}\n")

    if args.refresh:
        _state["data"] = None
        start_build()

    # 先把 HTTP 服务起起来，采集在后台跑。首次运行要抓几百款游戏的元数据，
    # 同步等会让用户盯着一个没浏览器的黑窗口好几分钟。
    snap = get_snapshot()
    if snap is None:
        print("正在采集 Steam 本地数据并抓取游戏元数据（首次运行需要几分钟）...")
        print("浏览器稍后会自动打开，页面里会显示进度。这个窗口别关。\n")
    else:
        s = snap["summary"]
        print(f"家庭组：{s['group_name']}（{s['group_id']}）")
        print(f"成员 {s['member_count']} 人 | 共享游戏 {s['game_count']} 款 | "
              f"启动记录 {s['launch_count']} 次 | 时间线 {s['event_count']} 条")
        print(f"Steam 目录：{s['steam_root']}")

    url = f"http://{args.host}:{args.port}/"
    print(f"\n服务已启动 -> {url}")
    print("按 Ctrl+C 停止\n")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    httpd = Server((args.host, args.port), Handler)
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


if __name__ == "__main__":
    main()
