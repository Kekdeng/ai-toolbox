#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dotenv.py — .env 解析 / 变量展开 / 格式化往返。

12-factor 应用的环境配置入口。三件事一次给全：

- parse：逐行 KEY=VALUE——`#` 注释行、可选 `export ` 前缀、双引号值
  转义（\\n \\t \\r \\" \\\\）、单引号字面量、裸值去行内注释
  （空格+# 起算，`a#b` 不算）；键名 [A-Za-z_] 开头非法即报错带行号；
- expand：只认 `${VAR}` 与 `${VAR:-default}`（`$VAR` 裸写不动，
  避免误伤字面量）；无值无缺省 → 空串；引用的值递归展开，循环
  （含自引用）报错——「PATH=$PATH:/x」式追加请先显式取出再拼；
- dumps：按需加引号（空白/#/引号/=）转义往返无损；load：读文件
  并可选写入给定 environ（override 控制覆盖），不给 environ 就纯读。

parse 不做展开、expand 不做解析——两步显式组合，口径不打架。

用法：
    python tools/dotenv.py --selftest
    python tools/dotenv.py --file .env --show
    python tools/dotenv.py --text 'A=1' --expand '${A}/x'

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re

_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _unquote(value: str) -> str:
    """值端处理：双引号转义 / 单引号字面量 / 裸值去行内注释。"""
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        body = value[1:-1]
        out: list[str] = []
        i = 0
        while i < len(body):
            c = body[i]
            if c == "\\" and i + 1 < len(body):
                out.append(_ESCAPES.get(body[i + 1], "\\" + body[i + 1]))
                i += 2
            else:
                out.append(c)
                i += 1
        return "".join(out)
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1]
    for sep in (" #", "\t#"):                  # 行内注释：空格+# 起算
        idx = value.find(sep)
        if idx != -1:
            value = value[:idx]
    return value.strip()


def parse(text: str) -> dict[str, str]:
    """.env 文本 → dict（保文件序）；坏行 ValueError 带行号。"""
    out: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            raise ValueError(f"第 {lineno} 行缺 '=': {raw!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        if not _KEY.fullmatch(key):
            raise ValueError(f"第 {lineno} 行键名非法: {raw!r}")
        out[key] = _unquote(value.strip())
    return out


def expand(value: str, env: dict | None = None,
           _seen: set[str] | None = None) -> str:
    """展开 ${VAR} / ${VAR:-default}；引用值递归，循环报错。"""
    env = env or {}
    seen = _seen if _seen is not None else set()

    def repl(m: re.Match) -> str:
        name, default = m.group(1), m.group(2)
        if name in seen:
            raise ValueError(f"循环引用: {name}")
        if name in env:
            return expand(str(env[name]), env, seen | {name})
        return default if default is not None else ""

    return _REF.sub(repl, value)


def dumps(data: dict[str, str]) -> str:
    """dict → .env 文本；含空白/注释/引号/= 的值加双引号转义。"""
    lines = []
    for k, v in data.items():
        if v == "" or any(c in v for c in " \t\n\r#\"'=") or v != v.strip():
            v = '"' + v.replace("\\", "\\\\").replace('"', '\\"') \
                       .replace("\n", "\\n").replace("\r", "\\r") \
                       .replace("\t", "\\t") + '"'
        lines.append(f"{k}={v}")
    return "\n".join(lines) + ("\n" if lines else "")


def load(path: str, environ: dict | None = None,
         override: bool = False) -> dict[str, str]:
    """读 .env 文件；environ 给定时写入（override 决定覆盖已有键）。"""
    with open(path, encoding="utf-8") as f:
        data = parse(f.read())
    if environ is not None:
        for k, v in data.items():
            if override or k not in environ:
                environ[k] = v
    return data


def _selftest() -> None:
    import os
    import tempfile

    # parse：注释/export/双引号转义/单引号字面量/尾注释/空白/空值
    d = parse('A=1\n# 注释行\nexport B="two words"\nC=\'lit #eral\'\n'
              "D=4 # 尾注释\nE=  spaced  \nF=\n")
    assert d == {"A": "1", "B": "two words", "C": "lit #eral", "D": "4",
                 "E": "spaced", "F": ""}, d
    assert parse(r'G="line1\nline2"') == {"G": "line1\nline2"}
    assert parse(r"H='a\nb'") == {"H": r"a\nb"}      # 单引号不转义
    assert parse("I=a#b") == {"I": "a#b"}            # 无空格的 # 是字面量

    # expand：基本/缺省/无值空串/裸 $ 不动/嵌套/循环报错
    assert expand("${A}/x", {"A": "1"}) == "1/x"
    assert expand("${MISS:-d}", {}) == "d"
    assert expand("${MISS}", {}) == ""
    assert expand("$HOME- literal", {}) == "$HOME- literal"
    assert expand("${A}", {"A": "${B}", "B": "2"}) == "2"
    for cyc in ({"A": "${A}"}, {"A": "${B}", "B": "${A}"}):
        try:
            expand("${A}", cyc)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{cyc} 应报循环错")

    # dumps 往返无损（含引号/换行/tab/中文/=）
    tricky = {"B": "two words", "C": "lit #eral", "Q": 'say "hi"', "E": "",
              "T": "tab\there", "N": "new\nline", "Z": "中文", "EQ": "a=b"}
    assert parse(dumps(tricky)) == tricky, dumps(tricky)

    # load：默认不动 environ；override 才覆盖
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, ".env")
        with open(p, "w", encoding="utf-8") as f:
            f.write("A=1\nB=from-file\n")
        env = {"A": "old"}
        load(p, env)
        assert env == {"A": "old", "B": "from-file"}, env
        load(p, env, override=True)
        assert env == {"A": "1", "B": "from-file"}, env
        assert load(p) == {"A": "1", "B": "from-file"}

    # 坏行：缺 = / 键名非法 → 报错带行号
    for bad in ("NOEQ", "=novalue", "1BAD=2"):
        try:
            parse(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 应报错")

    print("selftest ok: 解析八例/转义/展开六例/循环/往返/load/坏行 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description=".env 解析/展开/格式化")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--text", default=None, help=".env 文本")
    ap.add_argument("--file", default=None, help=".env 文件路径")
    ap.add_argument("--expand", default=None, metavar="TPL",
                    help="对给定模板做变量展开（配合 --text/--file）")
    ap.add_argument("--show", action="store_true", help="打印解析结果")
    args = ap.parse_args()
    if args.selftest or (args.text is None and args.file is None):
        _selftest()
        if args.text is None and args.file is None:
            return
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text
    data = parse(text)
    if args.expand:
        print(expand(args.expand, data))
        return
    print(dumps(data), end="")
    if args.show:
        for k, v in data.items():
            print(f"{k}={v!r}")


if __name__ == "__main__":
    main()
