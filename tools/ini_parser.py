#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ini_parser.py — INI 解析：分节 / 类型助手 / 引号剥离（最小件）。

老牌配置格式仍然到处都是（git config、php.ini、各种 .service）。
最小可门口径：

- `[section]` 分节，键在节外直接报错（严格，避免静默丢配置）；
- 分隔符 `=` 优先、`:` 兜底（取首个出现的）；值原样保留字符串，
  类型交给助手：as_int / as_float / as_bool（1/yes/true/on 系）；
- 全行注释 `;` 与 `#`；值两侧引号成对即剥（配 '" 或 \' 两族），
  中间空格保留——INI 惯例里引号不是转义机制，只是边界；
- 同节重复键报错（宁炸不错），同名节合并。

用法：
    python tools/ini_parser.py --selftest
    python tools/ini_parser.py --file settings.ini --show

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse


def _strip_inline(line: str) -> str:
    """剥成对包裹的引号；不成对原样（引号只是边界不是转义）。"""
    if len(line) >= 2 and line[0] == line[-1] and line[0] in "\"'":
        return line[1:-1]
    return line


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    """INI 文本 → {节: {键: 值(字符串)}}；节外键/重复键报错带行号。"""
    data: dict[str, dict[str, str]] = {}
    section: dict[str, str] | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            if not name:
                raise ValueError(f"第 {lineno} 行节名为空")
            section = data.setdefault(name, {})
            continue
        if section is None:
            raise ValueError(f"第 {lineno} 行键在节外: {raw!r}")
        i_eq, i_col = line.find("="), line.find(":")
        if i_eq == -1 and i_col == -1:
            raise ValueError(f"第 {lineno} 行缺分隔符 = 或 :: {raw!r}")
        if i_eq == -1 or (i_col != -1 and i_col < i_eq):
            key, _, val = line.partition(":")
        else:
            key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"第 {lineno} 行键名为空")
        if key in section:
            raise ValueError(f"第 {lineno} 行重复键: {key!r}（节内）")
        section[key] = _strip_inline(val.strip())
    return data


def as_int(v: str) -> int:
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"不是整数: {v!r}") from None


def as_float(v: str) -> float:
    try:
        return float(v)
    except ValueError:
        raise ValueError(f"不是浮点数: {v!r}") from None


_BOOL_TRUE = frozenset({"1", "yes", "true", "on"})
_BOOL_FALSE = frozenset({"0", "no", "false", "off"})


def as_bool(v: str) -> bool:
    """1/yes/true/on（大小写不敏感）→ True，0/no/false/off → False。"""
    low = v.lower()
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False
    raise ValueError(f"不是布尔（须 1/yes/true/on 或 0/no/false/off）: {v!r}")


def _selftest() -> None:
    text = (
        "; 顶部注释\n"
        "# 也算注释\n"
        "[server]\n"
        'host = 0.0.0.0\n'
        "port = 8080\n"
        'title = " 保留空格 "\n'
        "rate = 0.5\n"
        "debug = yes\n"
        "url: http://a.example/b=c\n"
        "raw = kept # 行内文本原样保留\n"
        "\n"
        "[client]\n"
        "retries = 3\n"
        "verbose = OFF\n"
        'name = "quoted"\n'
    )
    d = parse_ini(text)
    assert d["server"]["host"] == "0.0.0.0"
    assert as_int(d["server"]["port"]) == 8080
    assert d["server"]["title"] == " 保留空格 "
    assert as_float(d["server"]["rate"]) == 0.5
    assert as_bool(d["server"]["debug"]) is True
    assert d["server"]["url"] == "http://a.example/b=c"   # : 先出现用 :
    assert d["server"]["raw"] == "kept # 行内文本原样保留"  # 只剥全行注释
    assert as_int(d["client"]["retries"]) == 3
    assert as_bool(d["client"]["verbose"]) is False
    assert d["client"]["name"] == "quoted"                # 引号剥离

    # 同名节合并；单引号族也剥
    d2 = parse_ini("[a]\nx = 1\n[a]\ny = 'lit'\n")
    assert d2 == {"a": {"x": "1", "y": "lit"}}, d2

    # 布尔全表：true 系与 false 系大小写不敏感
    for t in ("1", "yes", "True", "ON"):
        assert as_bool(t) is True
    for f in ("0", "No", "FALSE", "off"):
        assert as_bool(f) is False

    # 报错：节外键 / 缺分隔符 / 重复键 / 空节名 / 类型助手
    for bad in ("x = 1\n",
                "[s]\nnodelim\n",
                "[s]\nk = 1\nk = 2\n",
                "[]\nk = 1\n"):
        try:
            parse_ini(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 应报错")
    for bad_call in (lambda: as_int("abc"), lambda: as_bool("maybe")):
        try:
            bad_call()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    print("selftest ok: 分节/双分隔符/引号剥离/类型助手/节合并/报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="INI 解析 + 类型助手")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--file", default=None, help="INI 文件路径")
    ap.add_argument("--text", default=None, help="INI 文本")
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
    for sec, kv in parse_ini(text).items():
        print(f"[{sec}]")
        for k, v in kv.items():
            print(f"  {k} = {v!r}")


if __name__ == "__main__":
    main()
