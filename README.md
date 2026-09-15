# Steam Family Toolbox

[![Release](https://img.shields.io/github/v/release/tt1bt/steam-family-toolbox?color=2f6fdb&label=release)](https://github.com/tt1bt/steam-family-toolbox/releases/latest)
[![License](https://img.shields.io/github/license/tt1bt/steam-family-toolbox?color=1a9c5b)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-2f6fdb)
![Dependencies](https://img.shields.io/badge/dependencies-none-1a9c5b)

**Steam 家庭组工具箱** —— 一个跑在自己电脑上的小工具：看清 Steam 家庭组里最近都添了什么、
谁在用谁的库、什么时候玩的、以及一家人到底把时间花在了哪。

名字刻意不带「家庭组」限定，后面加与家庭组无关的功能也不会显得别扭。

纯本地运行 —— 不登录、不上传、不需要 API Key、**零第三方依赖**。

[**⬇ 下载 Windows 版（免装 Python）**](https://github.com/tt1bt/steam-family-toolbox/releases/latest)

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

### 方式一：直接下载 exe（Windows，免装 Python）

从 [Releases](https://github.com/tt1bt/steam-family-toolbox/releases/latest) 下载
`steam-family-toolbox-<版本>-windows-x64.exe`，**放到一个你自己能写的文件夹里**
（比如桌面新建一个文件夹），双击运行。

- 会自动打开浏览器，页面里显示采集进度
- **首次运行要抓几百款游戏的商店元数据，约 1–3 分钟**，之后走缓存几秒就好
- 程序会在 exe 同级目录建一个 `data/` 存缓存。这是绿色的，删掉 exe 和 `data/` 就等于完全卸载
- 如果 exe 放在 `Program Files` 这类不能写的目录，缓存会退到
  `%LOCALAPPDATA%\SteamFamilyToolbox`

> ⚠️ 单文件 exe 会被部分杀软/浏览器标记为「未知发布者」——因为没有代码签名证书。
> 这是所有未签名的开源 exe 的常态。你可以选择自己从源码跑，见方式二。

### 方式二：从源码跑（跨平台）

**环境要求**

- **Python 3.9+**（只用标准库，**无需 `pip install` 任何东西**）
- 本机装过 Steam 并登录过，`logs/librarysharing_log.txt` 里有数据
- Windows / macOS / Linux 均可

**Windows**：双击 **`启动.cmd`**，脚本会自动找 Python、采集数据、启动服务并打开浏览器。

**macOS / Linux**：

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
python src/server.py --version       # 打印版本
python src/build.py                  # 只生成 data/snapshot.json 后退出
```

服务**先启动、再在后台采集**，所以浏览器会立刻打开并显示采集进度，
而不是让你对着一个没有浏览器的黑窗口等几分钟。

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
steam-family-toolbox/
├── 启动.cmd              # Windows 一键启动（源码方式）
├── start.sh              # macOS / Linux 启动
├── src/
│   ├── paths.py          # 路径解析（源码运行 / 打包 exe 两种模式）
│   ├── version.py        # 版本号单一来源
│   ├── vdf.py            # 极简 Valve VDF (KeyValues) 解析器
│   ├── steam_data.py     # 定位 Steam、解析日志与家庭组配置
│   ├── steam_play.py     # 采集游玩时长与成就
│   ├── steam_meta.py     # 抓取并缓存游戏元数据
│   ├── analyze.py        # 统计分析（贡献榜 / 热力图 / 趋势 / 冲突 / 成就）
│   ├── build.py          # 聚合成前端用的 JSON
│   └── server.py         # 本地 HTTP 服务（只监听 127.0.0.1）
├── web/
│   └── index.html        # 单文件前端（无外部依赖，图表全内联 SVG）
├── packaging/
│   ├── steam-family-toolbox.spec  # PyInstaller 配置
│   ├── make_icon.py      # 生成 icon.ico
│   └── icon.ico
└── data/                 # 运行时生成，已 gitignore
    ├── appmeta.json      # 游戏元数据缓存
    └── snapshot.json     # 完整快照（含分析结果）
```

前端是一个零依赖的单文件 HTML，后端只用 Python 标准库。整个项目没有第三方依赖。
图表是内联 SVG 和 CSS 画出来的，没有 Chart.js / ECharts 之类的库。

## 出问题了怎么排查

### 第一步：跑一次自检

```bat
cd /d <exe 所在目录>
steam-family-toolbox.exe --selftest
```

会打印一份环境报告：打包模式、数据目录是否可写、前端页面在不在、
**Steam 有没有被检测到**、共享日志大小、以及系统代理设置。
报 bug 时把这段贴出来，八成的问题一眼就能看出来。

### 双击没反应 / 窗口一闪而过

**从 v1.0.2 起，启动失败会在窗口里打出一份完整报告并停住等你按回车**，
同时把同样内容写进 `<exe 同级目录>/data/_server.log`。先去看那个文件。

如果连窗口都没出现过，说明问题发生在程序开始运行之前，最常见的原因是
**杀毒软件或 Windows SmartScreen 拦截**（未签名的 exe 会被拦）。按这个顺序查：

1. 在 cmd 里手动跑，看有没有输出：
   ```bat
   cd /d <exe 所在目录>
   steam-family-toolbox.exe
   ```
2. 检查 `<exe 所在目录>\data\_server.log` 有没有内容
3. 把 exe 加入杀毒软件白名单后重试

### 页面能打开但游戏名都是 AppID

说明抓商店元数据失败了（页面会退化成显示 AppID，不影响其他功能）。

先 `--selftest` 看**系统代理**那一节——本工具用的是 Python 标准库的默认行为，
也就是**会读 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量，Windows 上还会读注册表里的
系统代理设置**。如果你挂着代理，或者在公司网络里，这些请求可能被拦。

排查顺序：

1. 先确认是不是限流。抓 400 款游戏会打很多请求，Steam 返回 **429** 时程序会
   指数退避重试，最后抓不全但不报错。**再跑一次 `--refresh` 通常能补齐**
2. 如果确实是被代理拦了，临时清掉代理再跑：
   ```bat
   set HTTP_PROXY=
   set HTTPS_PROXY=
   steam-family-toolbox.exe --refresh
   ```
3. 也可以看 `data\_server.log`，抓取失败会记在里面

### 端口被占用

程序会自己处理，不用管：

- 如果发现**本工具已经有一个实例在跑** → 直接帮你打开已有页面，然后干净退出
- 如果端口被**别的程序**占用 → 自动往后找，最多试 20 个端口

想强制换端口：`steam-family-toolbox.exe --port 9000`

### 想同时开两个实例

```bat
steam-family-toolbox.exe --port 9001
```

### 采集很慢

首次运行要抓几百款游戏的商店元数据，1–3 分钟是正常的，页面上有进度条。
之后走缓存，**启动到页面可访问约 4 秒**。

### 想重置

删掉 exe 同级的 `data/` 目录即可，下次启动会重新采集。

## 命令行参数

| 参数 | 作用 |
|---|---|
| `--selftest` | 打印环境自检报告后退出（报 bug 用这个） |
| `--port N` | 换端口，默认 8765 |
| `--no-browser` | 不自动开浏览器 |
| `--refresh` | 启动时强制重新采集 |
| `--rebuild` | 只重新生成快照后退出 |
| `--no-pause` | 出错时不等待按键（脚本 / CI 用） |
| `--version` | 打印版本 |

## 自己打包 exe

```bash
python -m venv .venv
.venv/Scripts/pip install pyinstaller pillow

# 图标（已生成过就不用重跑）
python packaging/make_icon.py

# 打包
.venv/Scripts/pyinstaller --clean --noconfirm \
  --distpath dist --workpath build packaging/steam-family-toolbox.spec
```

产物在 `dist/steam-family-toolbox.exe`，约 10–15 MB。在非 Windows 平台上换
PyInstaller 对应平台的 bootloader 即可打出 Linux / macOS 版本。

打包设计上有两点要注意（改 spec 时别踩）：

1. `web/index.html` 必须通过 `datas` 打进去。运行时从 `sys._MEIPASS/web/` 读
   —— 那是 onefile 每次启动解压出的临时目录，**退出即消失**。所以只读资源和可写
   数据必须分开，见 `src/paths.py`
2. **`data/` 绝对不能打包进去**。里面有真实的家庭组成员昵称、账号 ID 和游玩记录，
   任何人解包 exe 都能拿到

## HTTP 接口

服务同时提供 JSON 接口，方便自己再加工：

| 路径 | 说明 |
|---|---|
| `GET /api/timeline` | 完整快照：概览 + 成员 + 游戏 + 全部事件 + `analysis` 分析块 |
| `GET /api/timeline?refresh=1` | 触发后台重新采集 |
| `GET /api/raw` | 只返回原始事件（ts / kind / appid / owner / raw 文本） |
| `GET /api/health` | 存活检查 + 采集状态（`building` / `progress` / `error` / `version`） |

采集还没完成时，`/api/timeline` 返回 **HTTP 503** 而不是空数据：

```json
{"building": true, "error": null,
 "progress": {"stage": "抓取游戏元数据", "done": 128, "total": 402}}
```

前端就是靠这个显示进度条并轮询的。脚本里调用记得处理 503。

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
