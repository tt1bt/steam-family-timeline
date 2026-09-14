"""极简 Valve VDF (KeyValues) 解析器。

Steam 的 localconfig.vdf / loginusers.vdf 都是这套格式：
    "key"      "value"
    "parent"   { ... }
    // 注释

只需要读到嵌套 dict + 字符串值即可，不做类型推断。
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[{}]|//[^\n]*')
_ESCAPES = {"\\n": "\n", "\\t": "\t", "\\\\": "\\", '\\"': '"'}


def _unquote(tok: str) -> str:
    body = tok[1:-1]
    out = []
    i = 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            pair = body[i : i + 2]
            out.append(_ESCAPES.get(pair, pair[1]))
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def loads(text: str) -> dict[str, Any]:
    """把 VDF 文本解析成嵌套 dict。"""
    tokens = _TOKEN.findall(text)

    def parse_block(pos: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while pos < len(tokens):
            tok = tokens[pos]
            if tok == "}":
                return result, pos + 1
            if tok.startswith("//"):
                pos += 1
                continue
            if tok in "{}":
                # 松散的裸花括号，跳过
                pos += 1
                continue

            key = _unquote(tok)
            pos += 1
            if pos >= len(tokens):
                break

            nxt = tokens[pos]
            if nxt == "{":
                value, pos = parse_block(pos + 1)
                result[key] = value
            elif nxt.startswith("//"):
                pos += 1
            elif nxt in "{}":
                pos += 1
            else:
                result[key] = _unquote(nxt)
                pos += 1
        return result, pos

    # 顶层可能有多个并列的 key，取其第一个完整块
    start = 0
    while start < len(tokens) and (tokens[start].startswith("//") or tokens[start] in "{}"):
        start += 1
    if start >= len(tokens):
        return {}
    root_key = _unquote(tokens[start])
    if start + 1 < len(tokens) and tokens[start + 1] == "{":
        block, _ = parse_block(start + 2)
        return {root_key: block}
    return {}


def load(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return loads(fh.read())
