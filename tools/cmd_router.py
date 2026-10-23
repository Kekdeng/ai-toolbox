#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cmd_router.py — 迷你子命令路由：注册表分发 + help 自动生成。

git 风格多命令 CLI（`mytool serve`、`mytool migrate`）用 argparse
的子解析器样板很重。这里 60 行把骨架做掉：

- `@rt.command("name", usage="[name]", help="…")` 注册处理器，
  处理器收 `argv`（位置参数列表）自己拆——不重复造参数解析；
- `rt.run(argv)` 分发并返回处理器返回值；`help` 内建（自动列出
  全部命令按名排序）；缺命令/未知命令抛 `UsageError`（ValueError
  子类），消息即完整 usage——打印它、`exit(2)` 都由调用方定；
- 重名注册、保留字 `help`、带空白的命令名一律注册期报错。

用法：
    python tools/cmd_router.py --selftest
    python tools/cmd_router.py greet li

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable


class UsageError(ValueError):
    """缺命令/未知命令；消息即完整 usage 文本。"""


class Router:
    """子命令注册表：name → handler(argv)。"""

    def __init__(self, prog: str, desc: str = "") -> None:
        self.prog = prog
        self.desc = desc
        self._cmds: dict[str, dict] = {}

    def _register(self, name: str, fn: Callable, usage: str, help_: str) -> None:
        if not name or re.search(r"\s", name):
            raise ValueError(f"命令名须非空且无空白: {name!r}")
        if name == "help":
            raise ValueError("help 是保留命令名")
        if name in self._cmds:
            raise ValueError(f"命令重复注册: {name!r}")
        self._cmds[name] = {"fn": fn, "usage": usage, "help": help_}

    def command(self, name: str, usage: str = "",
                help: str = "") -> Callable:  # noqa: A002 与 argparse 对齐
        """装饰器注册。"""
        def deco(fn: Callable) -> Callable:
            self._register(name, fn, usage, help)
            return fn
        return deco

    def add(self, name: str, fn: Callable,
            usage: str = "", help: str = "") -> None:  # noqa: A002
        """非装饰器注册（编程式）。"""
        self._register(name, fn, usage, help)

    def usage(self) -> str:
        """自动 help：命令按名排序，列齐 usage 与说明。"""
        lines = [f"{self.prog} — {self.desc}" if self.desc else self.prog,
                 f"用法: {self.prog} <命令> [参数]", "命令:"]
        for name in sorted(self._cmds):
            c = self._cmds[name]
            head = f"  {name} {c['usage']}".rstrip()
            lines.append(f"{head:<24}{c['help']}".rstrip())
        return "\n".join(lines)

    def run(self, argv: list[str]):
        """分发命令列表，返回处理器返回值。显式 help 返回 usage；
        缺命令/未知命令抛 UsageError（消息即完整 usage）。"""
        if argv and argv[0] == "help":
            return self.usage()
        if not argv:
            raise UsageError(self.usage())
        name, rest = argv[0], list(argv[1:])
        if name not in self._cmds:
            raise UsageError(f"未知命令: {name!r}\n\n{self.usage()}")
        return self._cmds[name]["fn"](rest)


def _selftest() -> None:
    rt = Router(prog="demo", desc="演示路由")

    @rt.command("greet", usage="[name]", help="打招呼")
    def greet(argv):
        return f"hi {argv[0] if argv else 'world'}"

    rt.add("add", lambda a: str(int(a[0]) + int(a[1])),
           usage="A B", help="求和")

    # 分发：返回值透传，rest 以 list 传入
    assert rt.run(["greet", "li"]) == "hi li"
    assert rt.run(["greet"]) == "hi world"
    assert rt.run(["add", "1", "2"]) == "3"

    # help 内建：按名排序、含全部命令
    text = rt.run(["help"])
    assert text.index("add") < text.index("greet")     # 排序
    for frag in ("demo", "用法", "A B", "[name]", "求和", "打招呼"):
        assert frag in text, frag

    # 未知/缺命令 → UsageError（ValueError 子类），消息带 usage
    try:
        rt.run(["nope"])
    except UsageError as e:
        assert "nope" in str(e) and "greet" in str(e)
        assert isinstance(e, ValueError)
    else:
        raise AssertionError("未知命令应 UsageError")
    try:
        Router(prog="x").run([])
    except UsageError:
        pass
    else:
        raise AssertionError("缺命令应 UsageError")

    # 注册期报错：重名 / 保留字 / 坏名
    for bad_reg in (lambda: rt.command("greet")(greet),
                    lambda: rt.add("help", greet),
                    lambda: rt.add("bad name", greet),
                    lambda: rt.add("", greet)):
        try:
            bad_reg()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    print("selftest ok: 分发/help内建排序/UsageError/注册期报错 全部通过")


def main() -> None:
    rt = Router(prog="cmd_router", desc="迷你子命令路由演示")

    @rt.command("greet", usage="[name]", help="打招呼")
    def greet(argv):
        return f"hi {argv[0] if argv else 'world'}"

    ap = argparse.ArgumentParser(description="迷你子命令路由")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("rest", nargs="*", help="命令与参数")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    try:
        result = rt.run(args.rest)
    except UsageError as e:
        print(e, file=sys.stderr)
        raise SystemExit(2) from None
    if result is not None:
        print(result)


if __name__ == "__main__":
    main()
