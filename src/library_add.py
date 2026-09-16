"""推导「游戏何时进入本机库」。

**先说清楚：Steam 本地没有任何「某游戏于 X 日加入库」的记录。** 这是服务端状态，
客户端只拿到结果。这个模块做的是**从本机日志里找旁证，反推一个近似时间**，
并如实报告证据强度和置信度 —— 不允许输出看起来很准但其实错得离谱的日期。

三个可用信号，各自都有硬伤：

1. ``userdata/<账号>/config/librarycache/<appid>.json`` 的**创建时间**
   = Steam 首次为本机缓存这个 app 的库信息。
   硬伤：Steam 在某些事件（版本升级、库重整）会**批量重建**这些文件，
   ctime 会一起被刷新。实测 236 个有游玩记录的游戏里，**58 个的
   「最后游玩时间」早于 ctime**，最大差 1799 天 —— 所以老游戏基本不可信。

2. ``logs/steamui_librarycache.txt`` 里 ``Completed asset downloads for app N``
   的**首次出现时间** = 本机第一次为这个 app 下载封面/图标等资源。
   硬伤：日志滚动，本机只覆盖 2025-07-23 之后；
   且商店浏览、好友动态也会触发下载，可能早于真正入库。

3. ``logs/librarysharing_log.txt`` 里该 app 的首次事件
   = 第一次有人真的用了它。**语义不同**（是「首次使用」不是「入库」），
   只在没法判断时作为「早于某时可用」的下界参考。

两个信号在近期吻合得很好（实测多数在几分钟内），所以在能交叉验证时给出高置信度；
只有一个信号时给中等；两者相差太远时给低并同时展示两个日期，让人自己判断。
"""

from __future__ import annotations

import os
import re
import time

#: 两个信号相差超过这么多天就认为互相矛盾
CONFLICT_DAYS = 90

#: 相差在这么多天以内认为互相印证
AGREE_DAYS = 7

_DT_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
_ASSET_RE = re.compile(r"asset downloads for app (\d+)")


def _parse_dt(s: str) -> float | None:
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return None


def scan_asset_downloads(root: str) -> tuple[dict[str, float], float | None, float | None]:
    """扫 steamui_librarycache.txt，取每个 appid **首次**下载资源的时间。

    返回 ``({appid: ts}, 日志覆盖起点, 日志覆盖终点)``。
    覆盖范围很重要 —— 超出这个范围的结论都不可靠，得如实告诉用户。
    """
    first: dict[str, float] = {}
    lo = hi = None
    for name in ("steamui_librarycache.txt", "steamui_librarycache.previous.txt"):
        path = os.path.join(root, "logs", name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "asset downloads for app" not in line:
                        continue
                    m_dt = _DT_RE.match(line)
                    m_app = _ASSET_RE.search(line)
                    if not m_dt or not m_app:
                        continue
                    ts = _parse_dt(m_dt.group(1))
                    if ts is None:
                        continue
                    appid = m_app.group(1)
                    cur = first.get(appid)
                    if cur is None or ts < cur:
                        first[appid] = ts
                    if lo is None or ts < lo:
                        lo = ts
                    if hi is None or ts > hi:
                        hi = ts
        except OSError:
            continue
    return first, lo, hi


def scan_librarycache_ctime(root: str) -> dict[str, float]:
    """取每个 appid 在所有本机账号里**最早**的 librarycache 文件创建时间。

    跨账号取最早：同一个共享游戏可能因为多个成员登录而在不同账号下各建一份缓存，
    最早的那份最接近「本机第一次见到它」。

    注意 Windows 上 ``st_ctime`` 就是创建时间；Unix 上是 inode 变更时间，
    语义不同，所以这个信号只在 Windows 上可靠。
    """
    ud = os.path.join(root, "userdata")
    if not os.path.isdir(ud):
        return {}
    first: dict[str, float] = {}
    for acc in os.listdir(ud):
        if not acc.isdigit():
            continue
        cache = os.path.join(ud, acc, "config", "librarycache")
        if not os.path.isdir(cache):
            continue
        try:
            names = os.listdir(cache)
        except OSError:
            continue
        for name in names:
            if not name.endswith(".json"):
                continue
            appid = name[:-5]
            if not appid.isdigit():
                continue
            try:
                ts = os.stat(os.path.join(cache, name)).st_ctime
            except OSError:
                continue
            cur = first.get(appid)
            if cur is None or ts < cur:
                first[appid] = ts
    return first


def build_additions(root: str, shared_appids, first_use: dict[str, float],
                    accounts: int = 0) -> dict:
    """给每个共享游戏推导「何时进入本机库」。

    输出分成两种**语义完全不同**的结论，界面上必须区分显示：

    ``kind="added"``
        封面下载与库缓存创建两个独立信号落在几天之内 —— 这基本就是它出现在
        库里的时刻。可以直接当入库时间用。

    ``kind="bound"``
        只能确定「**不晚于**此时它已经在库里」。因为：
        - 库缓存会被批量重建，ctime 只会偏晚
        - 封面下载也可能偏晚（实测有首次使用比封面下载还早 15 天的）
        - 共享日志的首次事件是「有人用了它」，天然晚于入库
        所以这里给的是**上界**，不是入库时间。
    """
    assets, log_lo, log_hi = scan_asset_downloads(root)
    ctimes = scan_librarycache_ctime(root)

    rows = []
    for appid in sorted({str(a) for a in shared_appids}):
        asset = assets.get(appid)
        ctime = ctimes.get(appid)
        use = first_use.get(appid)

        stamps = [t for t in (asset, ctime, use) if t]
        if not stamps:
            rows.append({
                "appid": appid, "ts": None, "kind": "unknown",
                "confidence": "none",
                "note": "本机没有任何关于它的时间记录",
                "evidence": {"asset": None, "ctime": None, "first_use": None},
            })
            continue

        floor = min(stamps)          # 最保守的上界
        kind, ts, confidence, note = "bound", floor, "low", ""

        if asset and ctime and abs(asset - ctime) <= AGREE_DAYS * 86400:
            cand = min(asset, ctime)
            if use and use < cand - 86400:
                # 首次使用比这还早 → 说明入库在更早，这个只是上界
                kind, ts, confidence = "bound", use, "medium"
                note = "封面与缓存时间吻合，但首次使用更早，只能确定上界"
            else:
                kind, ts, confidence = "added", cand, "high"
                note = "封面下载与库缓存创建在同一时刻，可信度较高"
        elif asset and ctime:
            gap = abs(asset - ctime) / 86400.0
            ts = min(asset, ctime)
            confidence = "medium" if gap <= CONFLICT_DAYS else "low"
            note = f"两个信号相差 {gap:.0f} 天，只能确定上界"
        elif asset:
            kind, ts, confidence = "bound", asset, "low"
            note = "只剩封面下载这一个信号"
        elif ctime:
            kind, ts, confidence = "bound", ctime, "low"
            note = "只剩库缓存时间这一个信号；该时间可能来自一次批量重建"
        else:
            kind, ts, confidence = "bound", floor, "medium"
            note = "只有共享日志的首次使用记录"

        # 上界不该晚于首次使用 —— 若晚于，说明取到的信号是重建产物
        if kind == "bound" and use is not None and ts > use:
            ts = use
            note += "；且已用首次使用时间收紧"

        rows.append({
            "appid": appid, "ts": ts, "kind": kind,
            "confidence": confidence, "note": note,
            "evidence": {"asset": asset, "ctime": ctime, "first_use": use},
        })

    # 新的在前；没有日期的排最后（本来就无从排序）
    rows.sort(key=lambda r: (r["ts"] is None, -(r["ts"] or 0)))
    return {
        "rows": rows,
        "added": sum(1 for r in rows if r["kind"] == "added"),
        "bound": sum(1 for r in rows if r["kind"] == "bound"),
        "unknown": sum(1 for r in rows if r["kind"] == "unknown"),
        "by_confidence": {c: sum(1 for r in rows if r["confidence"] == c)
                          for c in ("high", "medium", "low", "none")},
        # 资源下载日志的覆盖窗口 —— 比这更早的日期根本无从判断
        "log_window": {"from": log_lo, "to": log_hi},
        "accounts_scanned": accounts,
    }
