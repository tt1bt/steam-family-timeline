"""Steam 家庭组数据采集。

数据来源（全部为本机 Steam 客户端离线数据，无需登录）：

1. ``logs/librarysharing_log.txt``
   - ``Launching shared app <appid> : using preferred/available owner <accountid>``
     每次从家庭组其他成员库里启动游戏都会记一条，是最核心的时间线来源。
   - ``Shared lock for app <appid> changed/removed : ... owner <accountid>``
     共享锁变更（同时只能一人玩某游戏），反映占用与释放。
   - ``Set preferred lender <accountid> for AppID <appid>``
     手动指定了该游戏的出借方。

2. ``userdata/<accountid>/config/localconfig.vdf``
   - ``FamilyGroup`` 段：家庭组 ID、名称、全部成员 accountid 与角色。
   - ``Friends`` 段：好友 accountid -> 昵称，用于把 owner 数字翻译成人名。

3. ``config/loginusers.vdf``：本机登录过的账号，用于识别"我"是谁。

注意：Steam 不会持久化"某游戏是哪天加入家庭库"这种信息，本地也没有可读的
时间戳来源。因此本工具以 **首次在家庭组内启动的时间** 作为"何时开始能玩到"的
近似，这是现有数据能达到的最好精度，页面上会明确标注。
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vdf  # noqa: E402

STEAM_BASE = 76561197960265728

# ---------------------------------------------------------------- 定位 Steam

_CANDIDATE_ROOTS = [
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
    r"D:\Steam",
    r"E:\Steam",
]


def find_steam_root() -> str | None:
    """依次尝试：注册表 -> 常见安装路径。"""
    candidates: list[str] = []
    if os.name == "nt":
        try:
            import winreg

            for hive, sub in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(hive, sub) as key:
                        for name in ("SteamPath", "InstallPath"):
                            try:
                                candidates.append(winreg.QueryValueEx(key, name)[0])
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass

    candidates.extend(_CANDIDATE_ROOTS)
    for path in candidates:
        norm = os.path.normpath(path.replace("/", os.sep))
        if os.path.isfile(os.path.join(norm, "steam.exe")) or os.path.isdir(
            os.path.join(norm, "userdata")
        ):
            return norm
    return None


def read_steam_env() -> str | None:
    """STEAM_FAMILY_STEAM_PATH 环境变量可强制指定路径。"""
    v = os.environ.get("STEAM_FAMILY_STEAM_PATH")
    return os.path.normpath(v.replace("/", os.sep)) if v else None


# ------------------------------------------------------------ 账号 / 昵称


def load_friends_map(root: str) -> dict[str, str]:
    """扫所有 userdata 账号的 Friends 段，汇总 accountid -> 昵称。"""
    mapping: dict[str, str] = {}
    userdata = os.path.join(root, "userdata")
    if not os.path.isdir(userdata):
        return mapping

    for acc in os.listdir(userdata):
        path = os.path.join(userdata, acc, "config", "localconfig.vdf")
        if not os.path.isfile(path):
            continue
        try:
            data = vdf.load(path)
        except Exception:
            continue
        _harvest_friends(data, mapping)
    return mapping


def _harvest_friends(node, out: dict[str, str]) -> None:
    """在任意深度找 { "name": ..., "avatar": ... } 形态的好友条目。"""
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if (
            key.isdigit()
            and key not in out
            and isinstance(value, dict)
            and isinstance(value.get("name"), str)
            and value["name"]
        ):
            out[key] = value["name"]
        if isinstance(value, dict):
            _harvest_friends(value, out)


def load_family(root: str) -> dict:
    """扫描所有 userdata，找到最完整的 FamilyGroup 定义。"""
    userdata = os.path.join(root, "userdata")
    best: dict = {}

    def walk(node):
        if isinstance(node, dict):
            if "groupid" in node and "members" in node:
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    if os.path.isdir(userdata):
        for acc in os.listdir(userdata):
            path = os.path.join(userdata, acc, "config", "localconfig.vdf")
            if not os.path.isfile(path):
                continue
            try:
                data = vdf.load(path)
            except Exception:
                continue
            for group in walk(data):
                members = group.get("members") or {}
                if len(members) > len(best.get("members") or {}):
                    best = group

    members = []
    for value in (best.get("members") or {}).values():
        aid = value.get("accountid")
        if aid:
            members.append({"accountid": str(aid), "role": value.get("role", "1")})

    return {
        "groupid": best.get("groupid", ""),
        "name": best.get("name", ""),
        "members": members,
    }


def load_login_users(root: str) -> dict[str, dict]:
    """loginusers.vdf -> {accountid: {...}}。"""
    path = os.path.join(root, "config", "loginusers.vdf")
    users: dict[str, dict] = {}
    if not os.path.isfile(path):
        return users
    try:
        data = vdf.load(path)
    except Exception:
        return users
    for sid64, info in (data.get("users") or {}).items():
        if not sid64.isdigit() or not isinstance(info, dict):
            continue
        acc = int(sid64) - STEAM_BASE
        users[str(acc)] = {
            "steamid64": sid64,
            "accountid": str(acc),
            "account_name": info.get("AccountName", ""),
            "persona_name": info.get("PersonaName", ""),
            "timestamp": int(info.get("Timestamp") or 0),
        }
    return users


# ---------------------------------------------------------- 时间线事件


def _parse_ts(text: str) -> int:
    """'2025-07-20 08:20:23' -> epoch 秒（按本机时区解释）。"""
    dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    return int(dt.astimezone().timestamp())


class EventLog:
    """一条 librarysharing 事件。"""

    __slots__ = ("ts", "kind", "appid", "owner", "raw")

    def __init__(self, ts: int, kind: str, appid: str | None, owner: str | None, raw: str):
        self.ts = ts
        self.kind = kind
        self.appid = appid
        self.owner = owner
        self.raw = raw

    def as_dict(self) -> dict:
        return {
            "ts": self.ts,
            "kind": self.kind,
            "appid": self.appid,
            "owner": self.owner,
            "raw": self.raw,
        }


RE_LAUNCH = re.compile(
    r"Launching shared app (\d+) : using (preferred|available) owner (\d+)(?: \(preferred owner (\d+)\))?"
)
RE_LOCK_CHANGED = re.compile(
    r"Shared lock for app (\d+) changed : available owner (\d+), preferred owner (\d+), current player (\d+)"
)
RE_LOCK_REMOVED = re.compile(r"Shared lock for app (\d+) removed : preferred owner (\d+)")
RE_LENDER = re.compile(r"Set preferred lender (\d+) for AppID (\d+)")
RE_FAMILY_INFO = re.compile(r"Loaded cached family info for account (\d+) \( groupID=(\d+)")
RE_LINE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(.+?)\s*$")


def parse_library_sharing(root: str) -> list[EventLog]:
    """解析 librarysharing_log.txt（含 .previous 备份）。"""
    events: list[EventLog] = []
    for name in ("librarysharing_log.txt", "librarysharing_log.previous.txt"):
        path = os.path.join(root, "logs", name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        for line in text.splitlines():
            m = RE_LINE.match(line)
            if not m:
                continue
            ts = _parse_ts(m.group(1))
            body = m.group(2)

            if (mm := RE_LAUNCH.match(body)):
                events.append(EventLog(ts, "launch", mm.group(1), mm.group(3), body))
            elif (mm := RE_LOCK_CHANGED.match(body)):
                owner = mm.group(4)
                if owner == "0":
                    owner = mm.group(3)
                events.append(EventLog(ts, "lock_acquire", mm.group(1), owner, body))
            elif (mm := RE_LOCK_REMOVED.match(body)):
                events.append(EventLog(ts, "lock_release", mm.group(1), mm.group(2), body))
            elif (mm := RE_LENDER.match(body)):
                events.append(EventLog(ts, "prefer_lender", mm.group(2), mm.group(1), body))
            elif (mm := RE_FAMILY_INFO.match(body)):
                events.append(EventLog(ts, "family_info", None, None, body))

    events.sort(key=lambda e: e.ts)
    return events


# ------------------------------------------------------------ 汇总


def build_snapshot(root: str, friends: dict[str, str], logins: dict[str, dict]) -> dict:
    """把原始事件聚合成分游戏 / 分成员的统计。"""
    events = parse_library_sharing(root)

    games: dict[str, dict] = {}
    member_stats: dict[str, dict] = {}

    for ev in events:
        if ev.appid:
            g = games.setdefault(
                ev.appid,
                {"appid": ev.appid, "launches": 0, "first_launch": None, "last_launch": None,
                 "lock_events": 0, "owners": {}},
            )
            if ev.kind == "launch":
                g["launches"] += 1
                if g["first_launch"] is None or ev.ts < g["first_launch"]:
                    g["first_launch"] = ev.ts
                if g["last_launch"] is None or ev.ts > g["last_launch"]:
                    g["last_launch"] = ev.ts
            elif ev.kind in ("lock_acquire", "lock_release"):
                g["lock_events"] += 1
            if ev.owner:
                g["owners"][ev.owner] = g["owners"].get(ev.owner, 0) + 1

        if ev.owner:
            s = member_stats.setdefault(
                ev.owner, {"accountid": ev.owner, "as_owner": 0, "launches": 0}
            )
            if ev.kind == "launch":
                s["launches"] += 1
            else:
                s["as_owner"] += 1

    return {"games": games, "member_stats": member_stats}
