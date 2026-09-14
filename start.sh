#!/usr/bin/env bash
# Steam 家庭组时间线 - macOS / Linux 启动脚本
set -e
cd "$(dirname "$0")"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo "找不到 Python 3。请先安装：https://www.python.org/downloads/"
  exit 1
fi

echo "使用 $PY 启动 Steam 家庭组时间线..."
exec "$PY" src/server.py "$@"
