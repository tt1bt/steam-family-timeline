"""名称、版本号与项目地址的单一来源。

改名字、改版本、改仓库名都只需要动这里；命令行的 ``--version``、启动 banner、
HTTP 的 ``Server`` 头、前端 ``<title>``、请求外部接口的 User-Agent 都从这里取。
"""

#: 展示用名称。刻意不带「家庭组」限定 —— 这个工具后面会加与家庭组无关的功能，
#: 名字不该被当前功能绑死。
APP_NAME = "Steam Family Toolbox"

__version__ = "1.0.3"

#: 用于 Release tag 与附件名
RELEASE_NAME = f"v{__version__}"

#: 项目主页。改仓库名只动这一行。
REPO_URL = "https://github.com/tt1bt/steam-family-toolbox"

#: 请求外部接口（Steam 商店 / 社区）时带的 User-Agent。
#: 带上版本号和主页，方便对方识别来源、也让限流时能联系到人。
USER_AGENT = f"SteamFamilyToolbox/{__version__} (+{REPO_URL})"
