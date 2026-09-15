"""分析统计模块：把原始数据加工成有洞察力的指标。

产出六大块：

1. **成员贡献榜**：谁提供了多少游戏、被其他人玩了多少次（"白嫖指数"）。
2. **时长排行**：按 Playtime 排序，含近两周活跃度。
3. **活跃热力图**：以「星期 × 小时」聚合共享游戏启动事件，看出作息规律。
4. **月度趋势**：逐月的共享启动次数与涉及游戏数。
5. **共享冲突**：同一游戏被抢锁的记录（有人正在玩，另一人想玩）。
6. **成就进度**：完成度排行，含全成就游戏。

设计原则：所有统计都明确标注口径与样本量，避免用户误读。
样本不足的指标直接标记 ``insufficient``，不做无意义的百分比。
"""

from __future__ import annotations

import collections
import time
from datetime import datetime

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _fmt_minutes(minutes: int | None) -> str:
    if not minutes:
        return "—"
    hours = minutes / 60.0
    if hours < 1:
        return f"{minutes} 分钟"
    if hours < 100:
        return f"{hours:.1f} 小时"
    return f"{hours:,.0f} 小时"


def _account_names(playtime_by_account: dict[str, dict],
                   members: list[dict]) -> list[dict]:
    """按时长降序列出「哪些账号有这款游戏的时长」，带显示名。

    只统计本地有 localconfig.vdf 的账号 —— 其余成员本机无数据。
    """
    name_of = {m["accountid"]: m["name"] for m in members}
    out = []
    for acc, games in playtime_by_account.items():
        if not games:
            continue
        minutes = sum(v.get("playtime") or 0 for v in games.values())
        if minutes <= 0:
            continue
        out.append({"accountid": acc, "name": name_of.get(acc, acc),
                    "minutes": minutes})
    out.sort(key=lambda x: -x["minutes"])
    return out


def _display_name(acc: str, name_of: dict[str, str]) -> str:
    """账号显示名。不在家庭组里的本机账号明确标注，避免和成员混淆。"""
    return name_of.get(acc) or f"本机账号 {acc}"


# ------------------------------------------------------------ 成员贡献

def member_contribution(timeline: list[dict], members: list[dict],
                        playtime_by_account: dict[str, dict]) -> dict:
    """谁贡献了游戏、谁在玩别人的游戏。

    数据口径（重要，避免误读）：

    - ``provided_games``  该成员的库被家庭组**其他成员**在本机启动过的游戏数
                          —— 注意本机只能看到出借方，看不到启动者。
    - ``launches``        该成员的库在本机被使用的总次数
    - ``recent_minutes``  该成员最近两周的游玩时长（仅本地有数据的账号）
    - ``net_ratio``       「被使用次数 / 本地游玩时长」的供需比。
                          低 = 玩别人游戏多（净受益方）；高 = 提供者被用得多。

    日志里没有「谁启动了谁的游戏」的配对信息，所以无法直接算白嫖榜。
    这里用「该成员库被使用次数」对比「该成员自己的游玩时长」来近似。
    """
    provider_usage = collections.Counter()   # accountid -> 库被启动次数
    provider_games = collections.defaultdict(set)

    for ev in timeline:
        if ev["kind"] != "launch" or not ev.get("owner"):
            continue
        owner, appid = ev["owner"], ev.get("appid")
        provider_usage[owner] += 1
        if appid:
            provider_games[owner].add(appid)

    rows = []
    for m in members:
        acc = m["accountid"]
        pt = playtime_by_account.get(acc, {})
        total_minutes = sum(v.get("playtime") or 0 for v in pt.values())
        recent_minutes = sum(v.get("playtime_2wks") or 0 for v in pt.values())
        used = provider_usage.get(acc, 0)
        # 该成员库被使用的次数 / 该成员自己玩了多少小时
        # 值越高说明「被白嫖」越严重
        hours = total_minutes / 60.0
        net_ratio = round(used / hours, 2) if hours >= 1 else None
        rows.append({
            "accountid": acc,
            "name": m["name"],
            "is_me": m.get("is_me", False),
            "is_alias": m.get("is_alias", False),
            "provided_games": len(provider_games.get(acc, ())),
            "provided_usage": used,
            "playtime_minutes": total_minutes,
            "playtime_text": _fmt_minutes(total_minutes),
            "recent_minutes": recent_minutes,
            "recent_text": _fmt_minutes(recent_minutes),
            "net_ratio": net_ratio,
            "has_local_data": bool(pt),
        })

    rows.sort(key=lambda r: (-r["provided_games"], -r["provided_usage"]))

    with_data = [r for r in rows if r["has_local_data"]]
    return {
        "rows": rows,
        "local_data_count": len(with_data),
        "local_data_missing": [r["name"] for r in rows if not r["has_local_data"]],
        "note": (
            "「贡献」= 该成员的库中，被家庭组在本机启动过的游戏数。"
            "日志只记录出借方，不含实际启动者，因此无法得出精确的「谁玩了谁的」。"
            f"本机只有 {len(with_data)} 名<b>家庭成员</b>登录过、能读到游玩时长，"
            "其余成员显示「—」。"
        ),
    }


# ------------------------------------------------------------ 时长排行

def playtime_ranking(playtime_by_account: dict[str, dict],
                     meta_lookup, members: list[dict]) -> dict:
    """按游戏排行。每个账号一份明细，同时给出合并后的总量。

    ``by_account`` 只含本地有数据的账号（其余成员本机拿不到时长）。
    ``items`` 是按 appid 合并的多账号总量，用于总排行榜。
    """
    name_of = {m["accountid"]: m["name"] for m in members}
    merged: dict[str, dict] = {}
    per_account: dict[str, dict] = {}

    for acc, games in playtime_by_account.items():
        acc_slot = per_account.setdefault(acc, {
            "accountid": acc, "name": _display_name(acc, name_of),
            "is_member": acc in name_of,
            "total_minutes": 0, "recent_minutes": 0, "games": [],
        })
        for appid, info in games.items():
            minutes = info.get("playtime") or 0
            recent = info.get("playtime_2wks") or 0
            if minutes <= 0 and recent <= 0:
                continue
            acc_slot["total_minutes"] += minutes
            acc_slot["recent_minutes"] += recent

            meta = meta_lookup(appid)
            acc_slot["games"].append({
                "appid": appid,
                "name": meta.get("name") or f"AppID {appid}",
                "capsule": meta.get("capsule"),
                "minutes": minutes,
                "minutes_text": _fmt_minutes(minutes),
                "recent": recent,
                "recent_text": _fmt_minutes(recent),
                "offline": info.get("playtime_offline") or 0,
                "last_played": info.get("last_played"),
            })

            slot = merged.setdefault(appid, {
                "appid": appid, "minutes": 0, "recent": 0, "offline": 0,
                "last_played": None, "accounts": [],
            })
            slot["minutes"] += minutes
            slot["recent"] += recent
            slot["offline"] += info.get("playtime_offline") or 0
            slot["accounts"].append({
                "accountid": acc, "name": _display_name(acc, name_of),
                "minutes": minutes,
            })
            lp = info.get("last_played")
            if lp and (slot["last_played"] is None or lp > slot["last_played"]):
                slot["last_played"] = lp

    items = []
    for slot in merged.values():
        if slot["minutes"] <= 0 and slot["recent"] <= 0:
            continue
        meta = meta_lookup(slot["appid"])
        accounts = sorted(slot["accounts"], key=lambda a: -a["minutes"])
        items.append({
            **slot,
            "accounts": accounts,
            "name": meta.get("name") or f"AppID {slot['appid']}",
            "capsule": meta.get("capsule"),
            "header": meta.get("header"),
            "minutes_text": _fmt_minutes(slot["minutes"]),
            "recent_text": _fmt_minutes(slot["recent"]),
            "account_names": [a["name"] for a in accounts],
        })
    items.sort(key=lambda x: -x["minutes"])

    for slot in per_account.values():
        if not slot["games"]:
            continue                      # 有配置但一条有效时长都没有，跳过
        slot["games"].sort(key=lambda x: -x["minutes"])
        slot["total_text"] = _fmt_minutes(slot["total_minutes"])
        slot["recent_text"] = _fmt_minutes(slot["recent_minutes"])
        slot["game_count"] = len(slot["games"])

    total_minutes = sum(i["minutes"] for i in items)
    return {
        "items": items,
        "by_account": sorted([s for s in per_account.values() if s["games"]],
                             key=lambda x: -x["total_minutes"]),
        "total_minutes": total_minutes,
        "total_text": _fmt_minutes(total_minutes),
        "game_count": len(items),
        "note": (
            "时长是该账号在本机的累计值，包含自有游戏与共享游戏，"
            "单凭这个字段无法区分来源。只有在本机登录过的账号才有数据。"
        ),
    }


# ------------------------------------------------------------ 活跃热力图

def activity_heatmap(timeline: list[dict]) -> dict:
    """星期 × 小时的启动事件分布。"""
    buckets = [[0] * 24 for _ in range(7)]
    launches = [t for t in timeline if t["kind"] == "launch"]
    for ev in launches:
        dt = datetime.fromtimestamp(ev["ts"])
        buckets[dt.weekday()][dt.hour] += 1

    peak = 0
    peak_cell = None
    for d in range(7):
        for h in range(24):
            if buckets[d][h] > peak:
                peak = buckets[d][h]
                peak_cell = (d, h)

    # 每个时段（0-5 凌晨 / 6-11 上午 / 12-17 下午 / 18-23 晚上）
    spans = {"凌晨 0-5": range(0, 6), "上午 6-11": range(6, 12),
             "下午 12-17": range(12, 18), "晚上 18-23": range(18, 24)}
    span_totals = {}
    for label, hours in spans.items():
        span_totals[label] = sum(buckets[d][h] for d in range(7) for h in hours)

    weekday_total = sum(buckets[d][h] for d in range(5) for h in range(24))
    weekend_total = sum(buckets[d][h] for d in (5, 6) for h in range(24))

    total = weekday_total + weekend_total

    return {
        "buckets": buckets,
        "peak": peak,
        "peak_cell": {"weekday": peak_cell[0], "hour": peak_cell[1]} if peak_cell else None,
        "span_totals": span_totals,
        "weekday_total": weekday_total,
        "weekend_total": weekend_total,
        "total": total,
        # 工作日 5 天 vs 周末 2 天，按天平均才有可比性
        "weekday_avg": round(weekday_total / 5, 1) if weekday_total else 0,
        "weekend_avg": round(weekend_total / 2, 1) if weekend_total else 0,
        "sample": total,
    }


# ------------------------------------------------------------ 月度趋势

def monthly_trend(timeline: list[dict]) -> dict:
    """逐月的启动次数、不同游戏数、活跃成员数。空月份补 0，折线才不会断。"""
    months: dict[str, dict] = {}
    for ev in timeline:
        if ev["kind"] != "launch":
            continue
        dt = datetime.fromtimestamp(ev["ts"])
        key = f"{dt.year:04d}-{dt.month:02d}"
        slot = months.setdefault(key, {
            "month": key, "launches": 0, "games": set(), "members": set(),
        })
        slot["launches"] += 1
        if ev.get("appid"):
            slot["games"].add(ev["appid"])
        if ev.get("owner"):
            slot["members"].add(ev["owner"])

    if not months:
        return {"series": [], "note": "没有共享启动记录。", "peak": None}

    # 补齐中间的空月份，否则折线图会跳过空档、误读趋势
    keys = sorted(months)
    start = datetime.strptime(keys[0], "%Y-%m")
    end = datetime.strptime(keys[-1], "%Y-%m")
    cursor = start
    series = []
    while cursor <= end:
        key = f"{cursor.year:04d}-{cursor.month:02d}"
        slot = months.get(key)
        series.append({
            "month": key,
            "launches": slot["launches"] if slot else 0,
            "games": len(slot["games"]) if slot else 0,
            "members": len(slot["members"]) if slot else 0,
        })
        cursor = (datetime(cursor.year + 1, 1, 1) if cursor.month == 12
                  else datetime(cursor.year, cursor.month + 1, 1))

    # 环比（对上一个月，0 时不给百分比，避免除以零的假象）
    for i, item in enumerate(series):
        if i == 0:
            item["delta"] = None
            continue
        prev = series[i - 1]["launches"]
        item["delta"] = (round(100.0 * (item["launches"] - prev) / prev, 1)
                         if prev else None)

    peak = max(series, key=lambda x: x["launches"])
    # 近 3 个月 vs 前 3 个月，判断最近是在升温还是降温
    tail = series[-6:]
    recent3 = sum(s["launches"] for s in tail[-3:])
    prev3 = sum(s["launches"] for s in tail[:3]) if len(tail) >= 6 else None
    momentum = None
    if prev3:
        momentum = round(100.0 * (recent3 - prev3) / prev3, 1)

    return {
        "series": series,
        "peak": {"month": peak["month"], "launches": peak["launches"]},
        "recent3": recent3,
        "prev3": prev3,
        "momentum": momentum,
        "month_count": len(series),
        "note": "按自然月汇总共享游戏的启动次数，空月份补 0。",
    }


# ------------------------------------------------------------ 共享冲突

def lock_conflicts(timeline: list[dict]) -> dict:
    """共享锁记录 —— 同一游戏被争夺/占用的情况。

    Steam 家庭共享同一时刻只能一人游玩某款游戏，锁记录能反映抢占行为。

    ⚠️ 锁事件里的 ``owner`` 是**出借方**（提供游戏的人），不是占用者。
       ``prefer_lender`` 才能看出「谁被指定为出借方」。日志里没有占用者身份，
       因此这里只统计锁的持续时间与出借方，不编造「谁抢了谁的锁」。
    """
    locks = [t for t in timeline if t["kind"] in ("lock_acquire", "lock_release")]
    by_app: dict[str, list] = collections.defaultdict(list)
    for ev in locks:
        if ev.get("appid"):
            by_app[ev["appid"]].append(ev)

    rows = []
    for appid, events in by_app.items():
        events.sort(key=lambda x: x["ts"])
        first = events[0]
        # 一次 acquire -> release 构成一段占用
        sessions = []
        open_at = None
        for ev in events:
            if ev["kind"] == "lock_acquire":
                open_at = ev
            elif ev["kind"] == "lock_release" and open_at is not None:
                sessions.append({
                    "start": open_at["ts"],
                    "end": ev["ts"],
                    "minutes": max(0, round((ev["ts"] - open_at["ts"]) / 60)),
                    "owner": open_at.get("owner"),
                    "owner_name": open_at.get("owner_name") or open_at.get("owner"),
                })
                open_at = None
        total_minutes = sum(s["minutes"] for s in sessions)
        rows.append({
            "appid": appid,
            "game": first.get("game") or f"AppID {appid}",
            "capsule": first.get("capsule"),
            "events": len(events),
            "sessions": sessions,
            "session_count": len(sessions),
            "total_minutes": total_minutes,
            "total_text": _fmt_minutes(total_minutes),
            "avg_text": _fmt_minutes(round(total_minutes / len(sessions))
                                     if sessions else 0),
            "lenders": sorted({s["owner_name"] for s in sessions if s["owner_name"]}),
        })

    rows.sort(key=lambda r: (-r["events"], -r["total_minutes"]))
    return {
        "rows": rows,
        "total_events": len(locks),
        "lock_apps": len(rows),
        "total_minutes": sum(r["total_minutes"] for r in rows),
        "note": (
            "共享锁表示某款共享游戏正被占用。锁事件记录的是「出借方」，"
            "日志里不含实际占用者的身份，所以这里只呈现占用频次与时长。"
        ),
    }


# ------------------------------------------------------------ 成就

def achievement_progress(achievements_by_account: dict[str, dict],
                         meta_lookup, members: list[dict]) -> dict:
    """按账号分开统计。不同账号的库差异巨大，混在一起算总完成度会被稀释。"""
    name_of = {m["accountid"]: m["name"] for m in members}
    items = []
    per_account: dict[str, dict] = {}
    for acc, games in achievements_by_account.items():
        slot = per_account.setdefault(acc, {
            "accountid": acc, "name": _display_name(acc, name_of),
            "is_member": acc in name_of,
            "games": 0, "achieved": 0, "total": 0, "perfect": 0,
        })
        for appid, info in games.items():
            if not info.get("total"):
                continue
            meta = meta_lookup(appid)
            row = {
                **info,
                "name": meta.get("name") or f"AppID {appid}",
                "capsule": meta.get("capsule"),
                "account_name": _display_name(acc, name_of),
                "missing": info["total"] - info["achieved"],
            }
            items.append(row)
            slot["games"] += 1
            slot["achieved"] += info["achieved"]
            slot["total"] += info["total"]
            if info["achieved"] == info["total"]:
                slot["perfect"] += 1

    for slot in per_account.values():
        slot["percent"] = (round(100.0 * slot["achieved"] / slot["total"], 1)
                           if slot["total"] else 0.0)
        # 有成就数据的游戏里，有多少被完整通关过
        slot["perfect_rate"] = (round(100.0 * slot["perfect"] / slot["games"], 1)
                                if slot["games"] else 0.0)

    perfect = [i for i in items if i["total"] and i["achieved"] == i["total"]]
    in_progress = [i for i in items if 0 < i["achieved"] < i["total"]]
    items.sort(key=lambda x: (-x["percent"], -x["achieved"]))

    total_ach = sum(i["total"] for i in items)
    total_got = sum(i["achieved"] for i in items)

    return {
        "items": items,
        "by_account": sorted(per_account.values(),
                             key=lambda x: -x["achieved"]),
        "perfect": sorted(perfect, key=lambda x: -x["total"]),
        "in_progress": sorted(in_progress, key=lambda x: -x["percent"])[:40],
        # 差一点点就全成就的，最容易勾起继续玩的欲望
        "almost": sorted(
            [i for i in in_progress if i["percent"] >= 80],
            key=lambda x: -x["percent"])[:20],
        "counts": {
            "total_games": len(items),
            "perfect": len(perfect),
            "in_progress": len(in_progress),
            "untouched": len([i for i in items if not i["achieved"]]),
            "total_achievements": total_ach,
            "total_achieved": total_got,
        },
        "overall_percent": round(100.0 * total_got / total_ach, 1) if total_ach else 0.0,
        "note": (
            "只有本机同步过成就的游戏才有数据。不同账号库大小差异很大，"
            "整体百分比仅供参考，重点看单个账号的完成度与「差一点全成就」列表。"
        ),
    }


# ------------------------------------------------------------ 总装

def overview(snapshot: dict, playtime: dict, achievements: dict,
             heatmap: dict, trend: dict, conflicts: dict) -> dict:
    """顶部概览用的派生指标。"""
    s = snapshot["summary"]
    days = None
    if s.get("first_ts") and s.get("last_ts"):
        days = max(1, round((s["last_ts"] - s["first_ts"]) / 86400))

    return {
        "span_days": days,
        "first_ts": s.get("first_ts"),
        "last_ts": s.get("last_ts"),
        "avg_launch_per_day": round(s["launch_count"] / days, 2) if days else None,
        "games_per_member": (round(s["game_count"] / s["member_count"], 1)
                             if s["member_count"] else None),
        "peak_month": trend.get("peak"),
        "momentum": trend.get("momentum"),
        "peak_slot": heatmap.get("peak_cell"),
        "conflict_events": conflicts["total_events"],
        "local_accounts": s.get("local_accounts", 0),
        "perfect_games": achievements.get("counts", {}).get("perfect", 0),
        "playtime_total_text": playtime.get("total_text"),
    }


def collect_appids(*playtime_by_account: dict) -> list[str]:
    """把若干 {accountid: {appid: info}} 映射里的 appid 全部收集起来去重。

    用于告诉元数据抓取器「还需要哪些游戏的名称」——分析页比时间线多出
    大量 appid（时长榜、成就榜里的游戏时间线里根本没出现过）。
    """
    ids: set[str] = set()
    for mapping in playtime_by_account:
        for games in mapping.values():
            ids.update(games.keys())
    return sorted(ids)


def build_analysis(snapshot: dict, root: str, playtime_by_account: dict,
                   achievements_by_account: dict, meta_lookup=None) -> dict:
    """组装全部分析结果。

    ``meta_lookup(appid) -> dict`` 由调用方注入，因为分析用到的 appid 远超
    时间线里的游戏（时长榜/成就榜包含大量未共享游戏），需要更全的元数据来源。
    """
    timeline = snapshot["timeline"]
    members = snapshot["members"]

    if meta_lookup is None:
        meta_map = {g["appid"]: g for g in snapshot["games"]}

        def meta_lookup(appid: str) -> dict:
            return meta_map.get(appid, {})

    contribution = member_contribution(timeline, members, playtime_by_account)
    playtime = playtime_ranking(playtime_by_account, meta_lookup, members)
    heatmap = activity_heatmap(timeline)
    trend = monthly_trend(timeline)
    conflicts = lock_conflicts(timeline)
    achievements = achievement_progress(achievements_by_account,
                                        meta_lookup, members)

    # 本机玩过、但从未出现在共享日志里的游戏 —— 说明「玩了但没走家庭共享」
    # 只看单款累计 >= 1 小时的，否则 10 分钟的小玩意会把列表冲爆
    shared_ids = {g["appid"] for g in snapshot["games"]}
    name_of = {m["accountid"]: m["name"] for m in members}
    never_shared = []
    for acc, games in playtime_by_account.items():
        for appid, info in games.items():
            if appid in shared_ids:
                continue
            minutes = info.get("playtime") or 0
            if minutes < 60:
                continue
            meta = meta_lookup(appid)
            never_shared.append({
                "appid": appid,
                "name": meta.get("name") or f"AppID {appid}",
                "accountid": acc,
                "account_name": _display_name(acc, name_of),
                "minutes": minutes,
                "minutes_text": _fmt_minutes(minutes),
            })
    never_shared.sort(key=lambda x: -x["minutes"])

    return {
        "overview": overview(snapshot, playtime, achievements, heatmap,
                             trend, conflicts),
        "contribution": contribution,
        "playtime": playtime,
        "heatmap": heatmap,
        "trend": trend,
        "conflicts": conflicts,
        "achievements": achievements,
        "never_shared": {
            "items": never_shared[:60],
            "count": len(never_shared),
            "note": (
                "本机有游玩时长（≥1 小时）但未出现在家庭共享日志里的游戏。"
                "可能是自有游戏直连游玩，也可能该游戏不支持共享。"
            ),
        },
        "generated_at": int(time.time()),
    }
