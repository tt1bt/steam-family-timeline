# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：把工具箱打成单文件 Windows exe。

用法（在项目根目录）::

    pyinstaller --clean --noconfirm packaging/steam-family-toolbox.spec

要点：

1. ``web/index.html`` 必须用 ``datas`` 打进去。运行时从 ``sys._MEIPASS/web/``
   读取 —— 见 ``src/paths.py`` 的说明，那是 onefile 的临时解压目录。
2. ``data/`` **绝对不能**打包进来。里面有真实的家庭组成员昵称、账号 ID 和
   游玩记录，会被任何人解包 exe 拿到。缓存文件由程序首次运行时自己在 exe
   同级目录生成。
3. 用 ``console=True``：需要显示启动 banner、采集进度和错误信息。
   这是个要看着日志才知道在干什么的工具，不该做成无窗口的。
"""

import os

# 项目根目录（本文件在 packaging/ 下）
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
SRC = os.path.join(ROOT, "src")

# 排除掉肯定用不到的大块头，能省几 MB。
#
# ⚠️ 不要排除 `email`！虽然咱们没直接用，但 `http.server` 靠它解析请求头，
#    排掉之后 exe 一启动就 ModuleNotFoundError: No module named 'email'。
#    同理别动 `ssl`（urllib 抓商店接口要 https）。
EXCLUDES = [
    "tkinter", "unittest", "doctest", "pydoc", "pydoc_data",
    "distutils", "setuptools", "pip", "wheel", "lib2to3",
    "xmlrpc", "sqlite3", "test", "test.support",
]

a = Analysis(
    [os.path.join(SRC, "server.py")],
    pathex=[SRC],
    binaries=[],
    # 只读资源：打成 _MEIPASS/web/index.html
    datas=[(os.path.join(ROOT, "web", "index.html"), "web")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="steam-family-toolbox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX 常被杀软误报，得不偿失
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "packaging", "icon.ico")
    if os.path.isfile(os.path.join(ROOT, "packaging", "icon.ico")) else None,
)
