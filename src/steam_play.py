"""采集游玩时长与成就数据。

数据来源
--------

1. ``userdata/<账号>/config/localconfig.vdf`` 的 ``apps`` 段
   每个 appid 下可能有：

   - ``Playtime``              累计游玩分钟数（整数，分钟）
   - ``Playtime2wks``          最近两周游玩分钟数
   - ``PlaytimeDisconnected``  离线游玩分钟数
   - ``LastPlayed``            最后游玩时间（Unix 秒）
   - ``autocloud.lastlaunch``  最近一次启动时间（Unix 秒）
   - ``autocloud.lastexit``    最近一次退出时间（Unix 秒）
   - ``LaunchOptions``         启动参数

   ⚠️ ``Playtime`` 是**该账号在本机的累计值**，包含自有游戏和家庭共享游戏，
     无法从这一个字段区分来源。区分只能靠 librarysharing_log（共享启动记录）。

2. ``userdata/<账号>/config/librarycache/<appid>.json``
   结构为 ``[[类型名, {version, data}], ...]``。其中 ``achievements`` 段含：

   - ``nTotal`` / ``nAchieved``  成就总数与已解锁数
   - ``vecAchievedHidden`` / ``vecUnachieved``  未解锁成就详情
   - ``vecHighlight``            精选成就

   只有该账号**实际同步过成就**的游戏才有这段数据（本机约 220/534）。

3. 已确认**不可用**的数据源：``librarycache`` 里的 ``friends`` 段虽然含好友在
   该游戏上的游玩时长（``minutes_played_forever``），但只在用户手动浏览该游戏的
   好友页面时才写入缓存。本机 534 个文件里只有 3 个带数据，**不足以做分析**。
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vdf  # noqa: E402


def _all_apps_sections(node):
    """递归收集所有名为 apps 的段。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "apps" and isinstance(value, dict):
                yield value
            yield from _all_apps_sections(value)
    elif isinstance(node, list):
        for item in node:
            yield from _all_apps_sections(item)


def load_playtime(root: str, accountid: str) -> dict[str, dict]:
    """返回 {appid: {playtime, playtime_2wks, playtime_offline, last_played,
    last_launch, last_exit, launch_options}}（分钟 / Unix 秒）。"""
    path = os.path.join(root, "userdata", accountid, "config", "localconfig.vdf")
    if not os.path.isfile(path):
        return {}

    try:
        data = vdf.load(path)
    except Exception:
        return {}

    out: dict[str, dict] = {}
    for section in _all_apps_sections(data):
        for appid, info in section.items():
            if not appid.isdigit() or not isinstance(info, dict):
                continue
            # appid 0 是 Steam 自己的「非 Steam 应用」汇总桶（实测里面有 6 分钟），
            # 不是真实游戏：它在商店查不到，白占一次请求 + 重试
            if int(appid) <= 0:
                continue
            # 只要含任一游玩相关字段就算有效记录
            if not any(k in info for k in
                       ("Playtime", "Playtime2wks", "LastPlayed", "autocloud")):
                continue

            def _int(key):
                try:
                    return int(info[key])
                except (KeyError, TypeError, ValueError):
                    return None

            entry = {
                "appid": appid,
                "accountid": accountid,
                "playtime": _int("Playtime"),
                "playtime_2wks": _int("Playtime2wks"),
                "playtime_offline": _int("PlaytimeDisconnected"),
                "last_played": _int("LastPlayed"),
                "launch_options": info.get("LaunchOptions") or "",
            }
            cloud = info.get("autocloud")
            if isinstance(cloud, dict):
                try:
                    entry["last_launch"] = int(cloud["lastlaunch"])
                except (KeyError, TypeError, ValueError):
                    entry["last_launch"] = None
                try:
                    entry["last_exit"] = int(cloud["lastexit"])
                except (KeyError, TypeError, ValueError):
                    entry["last_exit"] = None
            else:
                entry["last_launch"] = None
                entry["last_exit"] = None

            out[appid] = entry

    return out


def load_achievements(root: str, accountid: str) -> dict[str, dict]:
    """返回 {appid: {total, achieved, percent, last_unlock}}。"""
    base = os.path.join(root, "userdata", accountid, "config", "librarycache")
    if not os.path.isdir(base):
        return {}

    out: dict[str, dict] = {}
    for name in os.listdir(base):
        if not name.endswith(".json"):
            continue
        appid = name[:-5]
        if not appid.isdigit():
            continue
        try:
            with open(os.path.join(base, name), "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:
            continue
        if not isinstance(payload, list):
            continue

        for item in payload:
            if not (isinstance(item, list) and len(item) == 2 and item[0] == "achievements"):
                continue
            data = (item[1] or {}).get("data") or {}
            total = data.get("nTotal")
            if not total:
                break
            achieved = data.get("nAchieved") or 0

            # 最近一次解锁时间
            last_unlock = None
            for bucket in ("vecHighlight", "vecUnachieved"):
                pass
            # 已解锁成就的详情在 vecAchievedHidden 或需要另取；这里扫所有已知数组
            for key, value in data.items():
                if not isinstance(value, list):
                    continue
                for ach in value:
                    if not isinstance(ach, dict):
                        continue
                    if not ach.get("bAchieved"):
                        continue
                    ts = ach.get("rtUnlocked")
                    if isinstance(ts, (int, float)) and ts > 0:
                        if last_unlock is None or ts > last_unlock:
                            last_unlock = ts

            out[appid] = {
                "appid": appid,
                "accountid": accountid,
                "total": int(total),
                "achieved": int(achieved),
                "percent": round(100.0 * int(achieved) / int(total), 1) if total else 0.0,
                "last_unlock": last_unlock,
            }
            break

    return out


def load_achievement_details(root: str, accountid: str, appid: str) -> list[dict]:
    """取单款游戏的成就明细（用于展开查看）。"""
    path = os.path.join(root, "userdata", accountid, "config", "librarycache",
                        f"{appid}.json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return []

    seen: set[str] = set()
    out: list[dict] = []
    for item in payload if isinstance(payload, list) else []:
        if not (isinstance(item, list) and len(item) == 2 and item[0] == "achievements"):
            continue
        data = (item[1] or {}).get("data") or {}
        for value in data.values():
            if not isinstance(value, list):
                continue
            for ach in value:
                if not isinstance(ach, dict):
                    continue
                aid = ach.get("strID")
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                out.append({
                    "id": aid,
                    "name": ach.get("strName") or "",
                    "desc": ach.get("strDescription") or "",
                    "achieved": bool(ach.get("bAchieved")),
                    "unlocked": ach.get("rtUnlocked") or 0,
                    "percent": round(float(ach.get("flAchieved") or 0), 1),
                    "hidden": bool(ach.get("bHidden")),
                    "icon": ach.get("strImage") or "",
                })
        break
    out.sort(key=lambda a: (not a["achieved"], -a["unlocked"]))
    return out
