#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""toml_mini.py — TOML 最小子集：解析 / 格式化 / 往返无损。

配置文件里够用的那一刀：`[table]` / `[table.sub]` 分节、裸键、
`key = value`、五种值（基本串/字面串/整数/浮点/布尔）+ 单行数组
（可嵌套）。多行串、内联表、日期、十六进制等明确拒收并报行号
——子集边界诚实：宁可不支持，不要猜。

注释感知引号：`#` 只在引号外生效（`"a#b"` 是字面量）；基本串
转义支持 \\n \\t \\r \\" \\\\ 与 \\uXXXX；字面串（单引号）原样。
dumps 按类型格式化，parse(dumps(x)) == x 往返无损。

用法：
    python tools/toml_mini.py --selftest
    python tools/toml_mini.py --file config.toml --show

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re

_KEY = re.compile(r"[A-Za-z0-9_-]+")
_INT = re.compile(r"[+-]?\d+")
_FLOAT = re.compile(r"[+-]?(\d+\.\d+([eE][+-]?\d+)?|\d+[eE][+-]?\d+)")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _strip_comment(line: str) -> str:
    """去掉引号外的 # 注释（引号内原样保留）。"""
    out: list[str] = []
    in_str: str | None = None
    i = 0
    while i < len(line):
        c = line[i]
        if in_str == '"':
            if c == "\\":
                out.append(line[i:i + 2])
                i += 2
                continue
            if c == '"':
                in_str = None
            out.append(c)
        elif in_str == "'":
            if c == "'":
                in_str = None
            out.append(c)
        else:
            if c == "#":
                break
            if c in "\"'":
                in_str = c
            out.append(c)
        i += 1
    return "".join(out)


def _basic_str(s: str) -> tuple[str, int]:
    """s 以 " 开头：解析到闭引号，返回（值, 闭引号后下标）。"""
    out: list[str] = []
    i = 1
    while i < len(s):
        c = s[i]
        if c == '"':
            return "".join(out), i + 1
        if c == "\\":
            i += 1
            if i >= len(s):
                break
            e = s[i]
            if e == "u":
                out.append(chr(int(s[i + 1:i + 5], 16)))
                i += 5
                continue
            if e not in _ESCAPES:
                raise ValueError(f"不支持的转义: \\{e}")
            out.append(_ESCAPES[e])
            i += 1
            continue
        out.append(c)
        i += 1
    raise ValueError(f"字符串未闭合: {s!r}")


def _lit_str(s: str) -> tuple[str, int]:
    """字面串：以 ' 开头，原样到闭引号。"""
    end = s.find("'", 1)
    if end == -1:
        raise ValueError(f"字符串未闭合: {s!r}")
    return s[1:end], end + 1


def _find_close(s: str) -> int:
    """s 以 [ 开头：返回匹配 ] 的下标（引号感知）。"""
    depth = 0
    in_str: str | None = None
    i = 0
    while i < len(s):
        c = s[i]
        if in_str == '"':
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = None
        elif in_str == "'":
            if c == "'":
                in_str = None
        elif c == '"':
            in_str = '"'
        elif c == "'":
            in_str = "'"
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"数组未闭合: {s!r}")


def _value(s: str) -> object:
    """标量/数组解析；不认识的值明确报错（子集边界诚实）。"""
    s = s.strip()
    if s.startswith('"'):
        v, end = _basic_str(s)
        if s[end:].strip():
            raise ValueError(f"值后有多余内容: {s!r}")
        return v
    if s.startswith("'"):
        v, end = _lit_str(s)
        if s[end:].strip():
            raise ValueError(f"值后有多余内容: {s!r}")
        return v
    if s == "true":
        return True
    if s == "false":
        return False
    if s.startswith("["):
        end = _find_close(s)
        if s[end + 1:].strip():
            raise ValueError(f"值后有多余内容: {s!r}")
        body = s[1:end]
        if not body.strip():
            return []
        parts, depth, in_str, start = [], 0, None, 0
        for i, c in enumerate(body):
            if in_str == '"':
                if c == "\\":
                    continue
                if c == '"':
                    in_str = None
            elif in_str == "'":
                if c == "'":
                    in_str = None
            elif c == '"':
                in_str = '"'
            elif c == "'":
                in_str = "'"
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
            elif c == "," and depth == 0:
                parts.append(body[start:i])
                start = i + 1
        parts.append(body[start:])
        if any(not p.strip() for p in parts):
            raise ValueError(f"数组含空元素（禁尾逗号）: {s!r}")
        return [_value(p) for p in parts]
    if _INT.fullmatch(s):
        return int(s)
    if _FLOAT.fullmatch(s):
        return float(s)
    raise ValueError(f"不支持的值（子集不含日期/十六进制/内联表）: {s!r}")


def parse(text: str) -> dict:
    """TOML 子集文本 → dict；坏行 ValueError 带行号。"""
    root: dict = {}
    cur = root
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("["):
            m = re.fullmatch(r"\[([A-Za-z0-9_.-]+)\]", line)
            if not m:
                raise ValueError(f"第 {lineno} 行表头非法: {raw!r}")
            cur = root
            for seg in m.group(1).split("."):
                if not _KEY.fullmatch(seg):
                    raise ValueError(f"第 {lineno} 行段名非法: {raw!r}")
                cur = cur.setdefault(seg, {})
            continue
        if "=" not in line:
            raise ValueError(f"第 {lineno} 行缺 '=': {raw!r}")
        key, _, val = line.partition("=")
        key = key.strip()
        if not _KEY.fullmatch(key):
            raise ValueError(f"第 {lineno} 行键名非法: {raw!r}")
        try:
            cur[key] = _value(val)
        except ValueError as e:
            raise ValueError(f"第 {lineno} 行 {e}") from None
    return root


def _fmt(v: object) -> str:
    """值 → TOML 文本（与 parse 对偶）。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        body = v.replace("\\", "\\\\").replace('"', '\\"') \
                .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
        return f'"{body}"'
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)                        # int / float


def dumps(doc: dict) -> str:
    """dict → TOML 子集文本；顶层标量在前，dict 递归成分节。"""
    lines: list[str] = []
    for k, v in doc.items():
        if not isinstance(v, dict):
            lines.append(f"{k} = {_fmt(v)}")

    def walk(table: dict, prefix: str) -> None:
        for k, v in table.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                lines.append("")
                lines.append(f"[{path}]")
                for kk, vv in v.items():
                    if not isinstance(vv, dict):
                        lines.append(f"{kk} = {_fmt(vv)}")
                walk(v, path)

    walk(doc, "")
    return "\n".join(lines) + ("\n" if lines else "")


def _selftest() -> None:
    text = (
        "# 全注释行\n"
        'title = "Demo"          # 尾注释\n'
        "count = 42\n"
        "ratio = 0.5\n"
        "on = true\n"
        r"path = 'C:\raw\dir'" + "\n"
        'tags = ["a", "b", 3, [1, 2]]\n'
        'note = "行\\n转义"\n'
        'hash = "a#b"\n'
        "\n"
        '[server]\n'
        'host = "0.0.0.0"\n'
        "port = 8080\n"
        "\n"
        "[server.tls]\n"
        "enabled = false\n"
    )
    d = parse(text)
    assert d == {"title": "Demo", "count": 42, "ratio": 0.5, "on": True,
                 "path": "C:\\raw\\dir",
                 "tags": ["a", "b", 3, [1, 2]], "note": "行\n转义",
                 "hash": "a#b",
                 "server": {"host": "0.0.0.0", "port": 8080,
                            "tls": {"enabled": False}}}, d

    # 往返无损（含嵌套数组/中文/转义）
    assert parse(dumps(d)) == d, dumps(d)
    # 空文档 / 纯标量
    assert parse("") == {} and dumps({}) == ""
    assert parse(dumps({"a": 1})) == {"a": 1}

    # 子集边界：未闭合数组/不支持值/坏键/缺等号/未闭合串/坏表头
    for bad in ("k = [1, 2", "k = 0x1F", "k = 2026-01-01",
                "k.1 = 2", "= 2",
                "k =", 'k = "oops', "[unclosed", "[a..b]", "k = [1,]"):
        try:
            parse(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 应报错")

    print("selftest ok: 五类标量/嵌套数组/注释感知/分节/往返/子集边界 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="TOML 最小子集解析/格式化")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--file", default=None, help="TOML 文件路径")
    ap.add_argument("--text", default=None, help="TOML 文本")
    args = ap.parse_args()
    if args.selftest or (args.file is None and args.text is None):
        _selftest()
        if args.file is None and args.text is None:
            return
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text
    print(dumps(parse(text)), end="")


if __name__ == "__main__":
    main()
