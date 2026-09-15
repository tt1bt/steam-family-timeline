"""版本号单一来源。

改版本只需要动这里；`src/server.py`、打包脚本、Release 说明都从这里读。
"""

__version__ = "1.0.0"

#: Release 附件与 tag 用的名字
RELEASE_NAME = f"v{__version__}"
