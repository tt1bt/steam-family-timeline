# Steam 家庭组时间线 · Steam Family Timeline

一个跑在自己电脑上的小工具：**看清 Steam 家庭组里最近都添了什么、谁在用谁的库、什么时候玩的**，
并按时间顺序展开成时间轴。

纯本地运行，不登录、不上传、不需要 API Key。

```
┌─────────────────────────────────────────────────────────────┐
│  kp桑的大家庭                  家庭组 ID 157853             │
│  成员 6 人 · 共享游戏 25 款 · 启动记录 1,237 次 · 跨度 408 天 │
├─────────────────────────────────────────────────────────────┤
│  成员 [饕餮丿传奇(我)] [Nia] [aimb] [你锁头锁身子为什么不] … │
│  事件 [启动共享游戏 1237] [占用共享锁 39] [释放共享锁 26]    │
│  筛选 [搜索游戏名 / AppID / 成员…]        [重置] [重新采集]  │
├─────────────────────────────────────────────────────────────┤
│  2026-08-26 周三 · 2 条事件                                  │
│    19:48  ▸ Palworld / 幻兽帕鲁 #1623730   启动共享游戏      │
│    19:43  ▸ Palworld / 幻兽帕鲁 #1623730   启动共享游戏      │
│  2026-08-17 周一 · 1 条事件                                  │
│    20:51  ▸ Palworld / 幻兽帕鲁 #1623730   启动共享游戏      │
└─────────────────────────────────────────────────────────────┘
```

## 它能看到什么

| 视图 | 内容 |
|---|---|
| **时间线** | 按天分组、倒序展开。每次「启动共享游戏 / 占用共享锁 / 释放共享锁 / 指定出借方」都是一条独立事件，带精确到分钟的时间和归属成员 |
| **游戏库** | 25 款共享游戏卡片，含封面、简介、类型、发售日、首次出现时间、被启动次数 |
| **成员** | 家庭组每个成员提供了几款游戏、本机玩过多少次、具体是哪些游戏 |

筛选：按成员、按事件类型多选，加上游戏名 / AppID / 成员的全文搜索。三个视图都可复用同一套筛选条件。

## 数据从哪来

全部来自本机 Steam 客户端的离线文件，**不联网取私有数据**：

| 文件 | 用途 |
|---|---|
| `logs/librarysharing_log.txt` | 核心来源。Steam 每次从家庭成员库里启动游戏都会记一行，含 appid、所有者 accountid、精确时间戳。也记录共享锁的占用 / 释放 |
| `userdata/<账号>/config/localconfig.vdf` | `FamilyGroup` 段 → 家庭组 ID、名称、全部成员；`Friends` 段 → accountid 到昵称的映射 |
| `config/loginusers.vdf` | 本机登录过的账号，用来判断「我」是谁 |

游戏封面 / 简介 / 类型 / 发售日来自 Steam 商店的公开接口
`store.steampowered.com/api/appdetails`，结果缓存在 `data/appmeta.json`，30 天内不重复请求。

### 关于「近期添加的游戏」的口径

这一点必须说清楚，否则容易误解：

> **Steam 本地并不保存「某款游戏是哪一天加入家庭库」的记录。**

家庭组是服务端状态，客户端只拿到结果。所以本工具用
**该游戏在家庭组内首次被启动的时间** 作为「何时开始能玩到」的近似值。

对绝大多数游戏这已经足够——你第一次玩它，基本就是它出现在你库里的那段时间。
时间线上的每一行都是日志里的原始事件，没有任何推测成分。

## 快速开始

### 环境要求

- **Python 3.9+**（只用标准库，无需 `pip install` 任何东西）
- 本机装过 Steam 并登录过，`logs/librarysharing_log.txt` 里有数据
- Windows / macOS / Linux 均可

### Windows

双击 **`启动.cmd`**。脚本会自动找 Python、采集数据、启动服务并打开浏览器。

### macOS / Linux

```bash
chmod +x start.sh
./start.sh
```

### 手动运行

```bash
python src/server.py                 # 启动服务并自动开浏览器
python src/server.py --no-browser    # 不开浏览器
python src/server.py --refresh       # 强制重新采集
python src/server.py --port 9000     # 换端口
python src/build.py                  # 只生成 data/snapshot.json 后退出
```

启动后访问 <http://127.0.0.1:8765/>。

### Steam 装在非标准路径

工具会依次尝试注册表、`C:\Program Files (x86)\Steam` 等常见位置。都不对就手动指定：

```bash
# Windows (PowerShell)
$env:STEAM_FAMILY_STEAM_PATH = "D:\Steam"
python src/server.py

# macOS / Linux
export STEAM_FAMILY_STEAM_PATH="$HOME/.steam/steam"
python src/server.py
```

## 项目结构

```
steam-family-timeline/
├── 启动.cmd              # Windows 一键启动
├── start.sh              # macOS / Linux 启动
├── src/
│   ├── vdf.py            # 极简 Valve VDF (KeyValues) 解析器
│   ├── steam_data.py     # 定位 Steam、解析日志与家庭组配置
│   ├── steam_meta.py     # 抓取并缓存游戏元数据
│   ├── build.py          # 聚合成前端用的 JSON
│   └── server.py         # 本地 HTTP 服务（只监听 127.0.0.1）
├── web/
│   └── index.html        # 单文件前端（无外部依赖）
└── data/                 # 生成物，已 gitignore
    ├── appmeta.json      # 游戏元数据缓存
    └── snapshot.json     # 完整时间线快照
```

前端是一个零依赖的单文件 HTML，后端只用 Python 标准库。整个项目没有第三方依赖。

## HTTP 接口

服务同时提供 JSON 接口，方便自己再加工：

| 路径 | 说明 |
|---|---|
| `GET /api/timeline` | 完整快照：概览 + 成员 + 游戏 + 全部事件 |
| `GET /api/timeline?refresh=1` | 强制重新采集后返回 |
| `GET /api/raw` | 只返回原始事件（ts / kind / appid / owner / raw 文本） |
| `GET /api/health` | 存活检查 |

```bash
curl http://127.0.0.1:8765/api/timeline | python -m json.tool | head -40
```

## 隐私

- 服务**只监听 `127.0.0.1`**，同一局域网内的其他设备也访问不到
- 不会向任何服务器上传数据。唯一的对外请求是抓取游戏的**公开商店信息**
- `data/` 目录已加入 `.gitignore`。里面有你家家庭组的成员账号 ID 和游玩记录，
  **不要提交到公开仓库**
- 如果你在非本机环境分享，建议先删掉 `data/snapshot.json`

## 已知限制

- **日志会滚动**。`librarysharing_log.txt` 有大小上限，Steam 会自动截断旧记录。
  历史长度取决于你的使用频率，本机目前保留了约 14 个月
- **只有本机视角**。数据来自这台电脑的 Steam 客户端，只看得到在这台机器上发生过的共享行为。
  其他成员在自己电脑上玩的东西不会出现在这里
- **首次启动较慢**。要抓 25 款游戏的商店元数据，约 30 秒。之后走缓存，基本秒开
- **家庭组创建时间无法获取**。服务端状态，本地没有记录，所以时间轴起点是最早的共享行为
- 商店接口偶尔会限流，抓不到的条目会退化成只显示 AppID。点「重新采集」可重试

## License

MIT
