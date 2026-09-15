"""从 Steam 商店接口抓取游戏元数据，本地缓存。

只使用公开接口 ``store.steampowered.com/api/appdetails``，不需要登录、不需要 API key。
抓到的字段缓存到 ``data/appmeta.json``，默认 30 天内不重复请求。

接口限制：单次请求可带多个 appids，但请求太密会被限流（429）。这里串行 + 间隔 +
指数退避重试，慢但稳。抓不全也不影响主流程 —— 页面会退化成显示 appid。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

CACHE_TTL = 30 * 24 * 3600  # 30 天
API = "https://store.steampowered.com/api/appdetails"
UA = "steam-family-timeline/1.0 (+https://github.com/tt1bt/steam-family-timeline)"


def _http_json(url: str, retries: int = 4) -> dict | None:
    delay = 2.0
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(delay)
                delay *= 2
                continue
            return None
        except Exception:
            time.sleep(delay)
            delay *= 2
    return None


class MetaCache:
    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    self.data = json.load(fh)
            except Exception:
                self.data = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def is_fresh(self, appid: str) -> bool:
        entry = self.data.get(appid)
        if not entry:
            return False
        # 没抓到名字的条目分两种，TTL 不同：
        #   _missing  商店确认没有这个 appid（已下架 / 非商品）—— 30 天内不再问
        #   _failed   网络或限流的临时失败 —— 每次都重试，否则一次 429 就锁死很久
        if entry.get("_missing"):
            return (time.time() - entry.get("_fetched", 0)) < CACHE_TTL
        if entry.get("_failed"):
            return False
        return (time.time() - entry.get("_fetched", 0)) < CACHE_TTL

    def fetch_missing(self, appids: list[str], language: str = "schinese",
                      verbose: bool = True, progress=None) -> int:
        """补齐缺失的 appid，返回实际成功抓取的条目数。

        注意：appdetails 接口目前**只接受单个 appid**，传逗号分隔的多个
        appid 会直接返回 HTTP 400。因此这里只能一个一个来。

        ``progress(stage, done, total)`` 可选回调，用来给界面上报进度。
        """
        todo = [a for a in appids if not self.is_fresh(a)]
        if not todo:
            return 0

        fetched = 0
        total = len(todo)
        for idx, a in enumerate(todo, 1):
            if progress:
                try:
                    progress("抓取游戏元数据", idx - 1, total)
                except Exception:
                    pass
            params = urllib.parse.urlencode({"appids": a, "l": language})
            payload = _http_json(f"{API}?{params}")

            if payload is None:
                if verbose:
                    print(f"  [{idx}/{total}] 请求失败 {a}，稍后重试可补齐")
                self.data[a] = {"appid": a, "name": None, "_failed": True}
                self.save()
                time.sleep(0.6)
                continue

            entry = payload.get(a) or {}
            if entry.get("success") and isinstance(entry.get("data"), dict):
                self.data[a] = _slim(a, entry["data"])
                fetched += 1
                if verbose:
                    print(f"  [{idx}/{total}] ok  {a} {self.data[a]['name']}")
            else:
                # 商店明确返回「没有这个 appid」，是永久状态，记 _missing
                self.data[a] = {"appid": a, "name": None, "_missing": True,
                                "_fetched": time.time()}
                if verbose:
                    print(f"  [{idx}/{total}] miss {a} (商店无数据/已下架)")

            self.save()
            time.sleep(0.6)

        return fetched

    def get(self, appid: str) -> dict:
        return self.data.get(appid) or {"appid": appid, "name": None}


def _slim(appid: str, data: dict) -> dict:
    """只保留页面上用得到的字段，避免缓存文件过大。"""
    price = None
    if isinstance(data.get("price_overview"), dict):
        price = data["price_overview"].get("final_formatted")
    elif data.get("is_free"):
        price = "免费"

    return {
        "appid": str(appid),
        "name": data.get("name"),
        "type": data.get("type"),
        "header": data.get("header_image"),
        "capsule": data.get("capsule_image") or data.get("capsule_imagev5"),
        "background": data.get("background_raw") or data.get("background"),
        "short_description": (data.get("short_description") or "")[:400],
        "developers": data.get("developers") or [],
        "publishers": data.get("publishers") or [],
        "genres": [g.get("description") for g in (data.get("genres") or []) if g.get("description")],
        "release_date": (data.get("release_date") or {}).get("date"),
        "coming_soon": (data.get("release_date") or {}).get("coming_soon", False),
        "price": price,
        "is_free": bool(data.get("is_free")),
        "metacritic": (data.get("metacritic") or {}).get("score"),
        "_fetched": time.time(),
    }
