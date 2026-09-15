"""把 Steam 原始数据组装成前端直接可用的时间线 JSON。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import steam_data as sd  # noqa: E402
import steam_meta as sm  # noqa: E402
import steam_play as sp  # noqa: E402
import analyze as an  # noqa: E402
import paths  # noqa: E402
import console  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
# 元数据缓存要放可写目录：打包成 exe 后项目目录是只读的临时解压目录
CACHE_PATH = paths.META_CACHE

# 角色说明：Steam 家庭组里 role 1 是成人，2 是儿童
ROLE_NAMES = {"1": "成人", "2": "儿童"}

KIND_META = {
    "launch": {"label": "启动共享游戏", "icon": "play", "weight": 1},
    "lock_acquire": {"label": "占用共享锁", "icon": "lock", "weight": 2},
    "lock_release": {"label": "释放共享锁", "icon": "unlock", "weight": 2},
    "prefer_lender": {"label": "指定出借方", "icon": "swap", "weight": 3},
}


def _display_names(root: str, friends: dict[str, str],
                   logins: dict[str, dict], remote: dict[str, str] | None = None):
    """昵称优先级：本机登录名 > 好友列表 > 远程查询结果 > accountid。"""
    def resolve(acc: str) -> str:
        if acc in logins and logins[acc].get("persona_name"):
            return logins[acc]["persona_name"]
        if friends.get(acc):
            return friends[acc]
        if remote and remote.get(acc):
            return remote[acc]
        return acc
    return resolve


def resolve_remote_names(accountids: list[str]) -> dict[str, str]:
    """对本地查不到的 accountid，用 Steam 社区公开 XML 接口补昵称。"""
    import re
    import urllib.request

    out: dict[str, str] = {}
    for acc in accountids:
        if not acc.isdigit():
            continue
        sid64 = int(acc) + sd.STEAM_BASE
        url = f"https://steamcommunity.com/profiles/{sid64}?xml=1"
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "steam-family-timeline/1.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            m = re.search(r"<steamID><!\[CDATA\[(.*?)\]\]></steamID>", text)
            if m:
                out[acc] = m.group(1)
        except Exception:
            continue
    return out


def build(steam_root: str | None = None, refresh_meta: bool = True,
          resolve_names: bool = True, verbose: bool = False,
          progress=None) -> dict:
    """生成完整的数据包。

    ``progress(stage, done, total)`` 可选回调，用于向前端汇报长任务的进度。
    """
    def report(stage: str, done: int, total: int) -> None:
        if progress:
            try:
                progress(stage, done, total)
            except Exception:
                pass

    root = steam_root or sd.read_steam_env() or sd.find_steam_root()
    if not root or not os.path.isdir(root):
        raise RuntimeError(
            "找不到 Steam 安装目录。请设置环境变量 STEAM_FAMILY_STEAM_PATH "
            "指向 Steam 根目录（例如 C:\\Program Files (x86)\\Steam）。"
        )

    family = sd.load_family(root)
    friends = sd.load_friends_map(root)
    logins = sd.load_login_users(root)

    owner_ids = set()
    for m in family["members"]:
        owner_ids.add(m["accountid"])

    # 找出时间线里出现过的、但本地没有昵称的 owner
    events_raw = sd.parse_library_sharing(root)
    for ev in events_raw:
        if ev.owner:
            owner_ids.add(ev.owner)

    remote_names: dict[str, str] = {}
    if resolve_names:
        unknown = [a for a in owner_ids if a not in friends and a not in logins]
        if unknown:
            if verbose:
                print(f"  [info] 远程查询 {len(unknown)} 个未知成员昵称: {unknown}")
            remote_names = resolve_remote_names(unknown)

    name_of = _display_names(root, friends, logins, remote_names)

    # 判定"我"是谁：本机登录过多个账号时，取最近一次登录的那个。
    # 用 loginusers.vdf 里的 Timestamp 排序，最新 = 当前活跃账号。
    current_account = ""
    if logins:
        current_account = max(logins.values(), key=lambda u: u.get("timestamp", 0))["accountid"]

    # 同一人可能在家庭组里有两个 accountid（小号和主号）。
    # 判重规则：同名成员的"主号"优先级 —— 本人 > 有实际共享数据 > 启动次数多 > accountid 小。
    # 其余同名账号标记为别名，前端折叠显示，避免一个人统计成两份。
    def _activity(acc: str) -> tuple:
        launches = 0
        provided = 0
        for ev in events_raw:
            if ev.owner == acc and ev.kind == "launch":
                launches += 1
            if ev.owner == acc and ev.kind != "launch":
                provided += 1
        return (acc == current_account, launches, provided)

    primary_by_name: dict[str, str] = {}
    for m in family["members"]:
        acc = m["accountid"]
        disp = name_of(acc)
        cur = primary_by_name.get(disp)
        if cur is None or _activity(acc) > _activity(cur):
            primary_by_name[disp] = acc
    # 本人优先，避免"我"被判成别名
    if current_account:
        primary_by_name[name_of(current_account)] = current_account

    members = []
    for m in family["members"]:
        acc = m["accountid"]
        disp = name_of(acc)
        members.append({
            "accountid": acc,
            "name": disp,
            "role": m.get("role", "1"),
            "role_name": ROLE_NAMES.get(m.get("role", "1"), "成员"),
            "is_me": acc == current_account,
            "is_alias": primary_by_name.get(disp) != acc,
        })
    members.sort(key=lambda x: (not x["is_me"], x["is_alias"], x["accountid"]))

    # 元数据：先抓时间线里的游戏，再补分析用到的（时长/成就里的游戏）
    appids = sorted({ev.appid for ev in events_raw if ev.appid})

    # 采集本机各账号的游玩时长与成就
    playtime_by_account: dict[str, dict] = {}
    achievements_by_account: dict[str, dict] = {}
    for acc in logins:
        pt = sp.load_playtime(root, acc)
        if pt:
            playtime_by_account[acc] = pt
        ach = sp.load_achievements(root, acc)
        if ach:
            achievements_by_account[acc] = ach

    if verbose:
        print(f"  [info] 有游玩时长数据的账号: {len(playtime_by_account)} 个")
        print(f"  [info] 有成就数据的账号: {len(achievements_by_account)} 个")

    meta_cache = sm.MetaCache(CACHE_PATH)
    if refresh_meta:
        need = sorted(set(appids) | set(an.collect_appids(
            playtime_by_account, achievements_by_account)))
        meta_cache.fetch_missing(need, verbose=verbose, progress=report)
    else:
        meta_cache._load()

    # 事件 -> 前端结构
    timeline = []
    for ev in events_raw:
        info = KIND_META.get(ev.kind)
        if info is None:
            continue  # family_info 是噪音，不进时间线
        meta = meta_cache.get(ev.appid) if ev.appid else {}
        timeline.append({
            "ts": ev.ts,
            "kind": ev.kind,
            "kind_label": info["label"],
            "weight": info["weight"],
            "appid": ev.appid,
            "game": meta.get("name") or (f"AppID {ev.appid}" if ev.appid else None),
            "header": meta.get("header"),
            "capsule": meta.get("capsule"),
            "owner": ev.owner,
            "owner_name": name_of(ev.owner) if ev.owner else None,
            "raw": ev.raw,
        })

    # 按游戏聚合
    games: dict[str, dict] = {}
    for item in timeline:
        if not item["appid"]:
            continue
        g = games.setdefault(item["appid"], {
            "appid": item["appid"],
            "name": item["game"],
            "header": item["header"],
            "capsule": item["capsule"],
            "genres": (meta_cache.get(item["appid"]).get("genres") or []),
            "short_description": meta_cache.get(item["appid"]).get("short_description") or "",
            "release_date": meta_cache.get(item["appid"]).get("release_date"),
            "first_seen": None,
            "last_seen": None,
            "launches": 0,
            "lock_events": 0,
            "owners": {},
        })
        if g["first_seen"] is None or item["ts"] < g["first_seen"]:
            g["first_seen"] = item["ts"]
        if g["last_seen"] is None or item["ts"] > g["last_seen"]:
            g["last_seen"] = item["ts"]
        if item["kind"] == "launch":
            g["launches"] += 1
        else:
            g["lock_events"] += 1
        if item["owner"]:
            key = item["owner"]
            g["owners"][key] = g["owners"].get(key, 0) + 1

    game_list = sorted(games.values(), key=lambda g: g["first_seen"] or 0)
    for g in game_list:
        g["owner_names"] = [
            {"accountid": k, "name": name_of(k), "count": v}
            for k, v in sorted(g["owners"].items(), key=lambda kv: -kv[1])
        ]

    # 按成员聚合
    member_agg = []
    for m in members:
        acc = m["accountid"]
        owned = [g for g in game_list if acc in g["owners"]]
        launched = [t for t in timeline if t["owner"] == acc and t["kind"] == "launch"]
        member_agg.append({
            **m,
            "games_provided": len(owned),
            "launch_count": len(launched),
            "games": [{"appid": g["appid"], "name": g["name"], "capsule": g["capsule"]}
                      for g in owned],
        })

    # 概览
    stamps = [t["ts"] for t in timeline]
    summary = {
        "group_name": family.get("name") or "未知家庭组",
        "group_id": family.get("groupid") or "",
        "member_count": len(members),
        "game_count": len(game_list),
        "launch_count": sum(1 for t in timeline if t["kind"] == "launch"),
        "event_count": len(timeline),
        "first_ts": min(stamps) if stamps else None,
        "last_ts": max(stamps) if stamps else None,
        "steam_root": root,
        "local_accounts": len(playtime_by_account),
    }

    snapshot = {
        "summary": summary,
        "members": member_agg,
        "games": game_list,
        "timeline": timeline,
        "kinds": KIND_META,
        "generated_at": int(__import__("time").time()),
    }

    # 分析块。元数据优先用缓存（覆盖比 game_list 全，含时长/成就里的游戏）。
    meta_cache_map = getattr(meta_cache, "data", {})

    def meta_lookup(appid: str) -> dict:
        cached = meta_cache_map.get(appid) or {}
        if cached.get("name"):
            return cached
        for g in game_list:
            if g["appid"] == appid:
                return g
        return cached

    snapshot["analysis"] = an.build_analysis(
        snapshot, root, playtime_by_account, achievements_by_account,
        meta_lookup=meta_lookup)
    return snapshot


if __name__ == "__main__":
    import json

    console.setup()

    data = build(refresh_meta=True, resolve_names=True, verbose=True)
    out = paths.SNAPSHOT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    s = data["summary"]
    print(f"\n家庭组: {s['group_name']}")
    print(f"成员 {s['member_count']} 人 / 共享游戏 {s['game_count']} 款 / "
          f"启动记录 {s['launch_count']} 次 / 时间线事件 {s['event_count']} 条")
    print(f"已写入 {out}")
