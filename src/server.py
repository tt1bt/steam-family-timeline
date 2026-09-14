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
PROJECT = os.path.dirname(HERE)
WEB_DIR = os.path.join(PROJECT, "web")
DATA_DIR = os.path.join(PROJECT, "data")
SNAPSHOT = os.path.join(DATA_DIR, "snapshot.json")

sys.path.insert(0, HERE)
import build as builder  # noqa: E402

_state = {"data": None, "lock": threading.Lock(), "building": False}


def get_snapshot(force: bool = False) -> dict:
    """取快照；无缓存或 force 时重新生成。"""
    with _state["lock"]:
        if force or _state["data"] is None:
            if os.path.isfile(SNAPSHOT) and not force:
                try:
                    with open(SNAPSHOT, "r", encoding="utf-8") as fh:
                        _state["data"] = json.load(fh)
                except Exception:
                    _state["data"] = None

            if _state["data"] is None:
                _state["building"] = True
                try:
                    _state["data"] = builder.build(refresh_meta=True,
                                                   resolve_names=True, verbose=True)
                    os.makedirs(DATA_DIR, exist_ok=True)
                    with open(SNAPSHOT, "w", encoding="utf-8") as fh:
                        json.dump(_state["data"], fh, ensure_ascii=False, indent=2)
                finally:
                    _state["building"] = False
        return _state["data"]


class Handler(BaseHTTPRequestHandler):
    server_version = "SteamFamilyTimeline/1.0"

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
                force = query.get("refresh", ["0"])[0] == "1"
                self._json(get_snapshot(force=force))
            elif route == "/api/health":
                self._json({"ok": True, "building": _state["building"],
                            "has_data": _state["data"] is not None})
            elif route == "/api/raw":
                # 原始事件文本，方便自己再加工
                snap = get_snapshot()
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
    ap = argparse.ArgumentParser(description="Steam 家庭组时间线 - 本地服务")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="启动时强制重新采集")
    ap.add_argument("--rebuild", action="store_true", help="只重新生成快照后退出")
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
    if not os.path.isfile(SNAPSHOT) or args.refresh:
        print("正在采集 Steam 本地数据（首次运行需要抓取游戏封面，约 30 秒）...")

    snap = get_snapshot(force=args.refresh)
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
    data = builder.build(refresh_meta=True, resolve_names=True, verbose=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SNAPSHOT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    _state["data"] = data
    return data


if __name__ == "__main__":
    main()
