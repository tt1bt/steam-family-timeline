"""名称与版本号的单一来源。

改名字或版本只需要动这里；命令行的 ``--version``、启动 banner、HTTP 的
``Server`` 头、前端 ``<title>`` 都从这里取。
"""

#: 展示用名称。刻意不带「家庭组」限定 —— 这个工具后面会加与家庭组无关的功能，
#: 名字不该被当前功能绑死。
APP_NAME = "Steam Family Toolbox"

__version__ = "1.0.1"

#: 用于 Release tag 与附件名
RELEASE_NAME = f"v{__version__}"
