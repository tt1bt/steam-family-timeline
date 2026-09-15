# Steam 家庭组工具箱 · Steam Family Toolbox

一个跑在自己电脑上的小工具：**看清 Steam 家庭组里最近都添了什么、谁在用谁的库、什么时候玩的、
以及一家人到底把时间花在了哪**。

纯本地运行，不登录、不上传、不需要 API Key。

```
┌─────────────────────────────────────────────────────────────┐
│  我的家庭组                      家庭组 ID 123456           │
│  成员 6 人 · 共享游戏 25 款 · 启动记录 1,237 次 · 跨度 408 天 │
├─────────────────────────────────────────────────────────────┤
│  成员 [玩家A(我)] [玩家B] [玩家C] [玩家D] …                 │
│  事件 [启动共享游戏 1237] [占用共享锁 39] [释放共享锁 26]    │
│  筛选 [搜索游戏名 / AppID / 成员…]        [重置] [重新采集]  │
├─────────────────────────────────────────────────────────────┤
│  时间线 │ 游戏库 │ 成员 │ 分析                              │
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
| **游戏库** | 共享游戏卡片，含封面、简介、类型、发售日、首次出现时间、被启动次数 |
| **成员** | 家庭组每个成员提供了几款游戏、本机玩过多少次、具体是哪些游戏 |
| **分析** | 统计数据总览、时长排行、月度趋势、活跃时段热力图、成员贡献表、成就完成度、共享锁占用排行、未走共享的游戏 |

筛选：按成员、按事件类型多选，加上游戏名 / AppID / 成员的全文搜索。
时间线与游戏库复用同一套筛选条件；成员与分析视图展示聚合数据，不受筛选影响。

### 分析视图里有什么

| 模块 | 说明 |
|---|---|
| **概览** | 统计跨度、日均启动、人均共享、峰值月份、近 3 月环比、最活跃时段、共享锁事件数 |
| **时长排行** | 每款游戏的累计 / 近两周时长条形图。条形按账号切分上色，一眼看出「这款是谁在玩」 |
| **月度趋势** | 逐月启动次数折线图，空月份补 0，附带峰值月与近 3 月环比 |
| **活跃时段** | 「星期 × 小时」热力图，定位到具体哪天哪个点最常开游戏；附凌晨 / 上午 / 下午 / 晚上四段占比，以及工作日与周末的日均对比 |
| **成员贡献** | 每个成员贡献了几款游戏、库被用了多少次、自己玩了多久、「被用次数 ÷ 自己玩的小时数」供需比 |
| **成就** | 按账号的完成度、差一点全成就的清单（≥80%）、已全成就游戏 |
| **共享锁** | 哪些游戏被占用最频繁、累计与平均占用时长、出借方是谁 |
| **未走共享** | 本机玩过（≥1 小时）但从未出现在共享日志里的游戏 —— 可能是自有游戏直接玩的 |

## 数据从哪来

全部来自本机 Steam 客户端的离线文件，**不联网取私有数据**：

| 文件 | 用途 |
|---|---|
| `logs/librarysharing_log.txt` | 核心来源。Steam 每次从家庭成员库里启动游戏都会记一行，含 appid、所有者 accountid、精确时间戳。也记录共享锁的占用 / 释放 |
| `userdata/<账号>/config/localconfig.vdf` | `FamilyGroup` 段 → 家庭组 ID、名称、全部成员；`Friends` 段 → accountid 到昵称的映射；**`apps` 段 → 每款游戏的游玩时长、最近两周时长、最后游玩时间、云同步启动 / 退出时间** |
| `userdata/<账号>/config/librarycache/<appid>.json` | 成就数据：总数、已解锁数、每个成就的名称 / 描述 / 解锁时间 |
| `config/loginusers.vdf` | 本机登录过的账号，用来判断「我」是谁 |

游戏封面 / 简介 / 类型 / 发售日来自 Steam 商店的公开接口
`store.steampowered.com/api/appdetails`，结果缓存在 `data/appmeta.json`，30 天内不重复请求。

> ⚠️ `appdetails` 接口**只接受单个 appid**。传逗号分隔的多个会直接返回 HTTP 400，
> 所以抓取是逐个请求、间隔 0.6 秒。

### 关于数据口径，必须说清楚

**1. 「近期添加的游戏」是近似值。**

> **Steam 本地并不保存「某款游戏是哪一天加入家庭库」的记录。**

家庭组是服务端状态，客户端只拿到结果。所以本工具用
**该游戏在家庭组内首次被启动的时间** 作为「何时开始能玩到」的近似值。
对绝大多数游戏这已经足够——你第一次玩它，基本就是它出现在你库里的那段时间。

**2. 游玩时长是「本机视角」。**

`Playtime` 字段是**某账号在本机**的累计值，包含自有游戏和共享游戏，
单看这个字段无法区分来源。而且本机只能读到**登录过的账号**的配置文件 ——
其他成员在自己电脑上玩的东西，这里完全没有。

**3. 日志里没有「谁启动了谁的游戏」的配对信息。**

`librarysharing_log` 只记录**出借方**（游戏是谁提供的），不记录实际启动者。
所以做不到精确的「白嫖榜」。工具用「该成员库被使用的次数」对比
「该成员自己的游玩时长」来近似供需关系，并在界面上明确标注了口径。


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
│   ├── steam_play.py     # 采集游玩时长与成就
│   ├── steam_meta.py     # 抓取并缓存游戏元数据
│   ├── analyze.py        # 统计分析（贡献榜 / 热力图 / 趋势 / 冲突 / 成就）
│   ├── build.py          # 聚合成前端用的 JSON
│   └── server.py         # 本地 HTTP 服务（只监听 127.0.0.1）
├── web/
│   └── index.html        # 单文件前端（无外部依赖，图表全内联 SVG）
└── data/                 # 生成物，已 gitignore
    ├── appmeta.json      # 游戏元数据缓存
    └── snapshot.json     # 完整快照（含分析结果）
```

前端是一个零依赖的单文件 HTML，后端只用 Python 标准库。整个项目没有第三方依赖。
图表是内联 SVG 和 CSS 画出来的，没有 Chart.js / ECharts 之类的库。

## HTTP 接口

服务同时提供 JSON 接口，方便自己再加工：

| 路径 | 说明 |
|---|---|
| `GET /api/timeline` | 完整快照：概览 + 成员 + 游戏 + 全部事件 + `analysis` 分析块 |
| `GET /api/timeline?refresh=1` | 强制重新采集后返回 |
| `GET /api/raw` | 只返回原始事件（ts / kind / appid / owner / raw 文本） |
| `GET /api/health` | 存活检查 |

`analysis` 里的字段：

```
analysis.overview       概览卡片与派生指标
analysis.playtime       {items: 按游戏合并, by_account: 按账号明细}
analysis.heatmap        {buckets: 7×24 二维数组, peak_cell, span_totals, …}
analysis.trend          {series: 逐月, peak, momentum}
analysis.contribution   {rows: 每成员的贡献与被使用情况}
analysis.conflicts      {rows: 每个游戏的锁会话}
analysis.achievements   {items, by_account, perfect, almost, counts}
analysis.never_shared   {items: 玩过但未走共享的游戏}
```

```bash
curl http://127.0.0.1:8765/api/timeline | python -m json.tool | head -40

# 只看时长排行前 5
curl -s http://127.0.0.1:8765/api/timeline \
  | python -c "import json,sys;d=json.load(sys.stdin);[print(x['name'],x['minutes_text']) for x in d['analysis']['playtime']['items'][:5]]"
```

## 隐私

- 服务**只监听 `127.0.0.1`**，同一局域网内的其他设备也访问不到
- 不会向任何服务器上传数据。唯一的对外请求是抓取游戏的**公开商店信息**
- `data/` 目录已加入 `.gitignore`。里面有你家家庭组的成员账号 ID、昵称和游玩记录，
  **不要提交到公开仓库**
- 成员昵称来自 `localconfig.vdf` 的 `Friends` 段和本机登录名，是真实昵称。
  如果你想分享截图，注意遮挡
- 如果你在非本机环境分享，建议先删掉 `data/snapshot.json`

## 已知限制

- **日志会滚动**。`librarysharing_log.txt` 有大小上限，Steam 会自动截断旧记录。
  历史长度取决于你的使用频率，本机目前保留了约 14 个月
- **游玩时长与成就只有本机视角**。只有在本机登录过的账号才有 `localconfig.vdf`，
  其余成员在分析里显示为「—」。这是数据源的硬限制，不是 bug
- **共享锁看不到占用者**。日志只记录出借方，因此「谁抢了谁的锁」无法还原
- **成就覆盖不全**。只有本机同步过成就的游戏才有数据（本机约 220/534 款），
  所以整体完成度百分比只能作为参考
- **首次启动较慢**。要抓几百款游戏的商店元数据，视数量约 3–8 分钟。之后走缓存基本秒开
- **家庭组创建时间无法获取**。服务端状态，本地没有记录，所以时间轴起点是最早的共享行为
- 商店接口偶尔会限流，抓不到的条目会退化成只显示 AppID。点「重新采集」可重试

## License

MIT
