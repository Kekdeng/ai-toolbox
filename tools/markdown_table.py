#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""markdown_table.py — Markdown 管道表格：解析 / 渲染 / 往返无损。

LLM 输出表格、程序消费表格的高频格式。做三件事：
- parse：管道表格文本 →（表头, 行, 对齐规格），容忍首尾空格与可省略
  的首尾管道，识别 :--- / :--: / ---: 对齐行；
- render：表头 + 行 + 对齐 → 等宽补齐的表格文本，单元格内的管道
  自动转义；
- 往返：render(parse(t)) 再 parse 回来与原解析结果等值（自测背书）。

列宽按 len() 计算——CJK 双宽字符在等宽字体下会略超，这里追求的是
「生成合法、可解析」而不是终端像素级对齐。

用法：
    python tools/markdown_table.py --selftest
    python tools/markdown_table.py --render "名称,数值" "a,3" "中文,12"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re

_ALIGN_RE = re.compile(r"^:?-+:?$")
_DASH = {"left": "---", "center": ":--:", "right": "--:"}


def escape_cell(s: str) -> str:
    """单元格文本 → 表格内安全文本（管道转义）。"""
    return s.replace("|", "\\|")


def _split_row(line: str) -> list[str]:
    """按管道切一行；\\| 不算分隔符并还原为 |，单元格去首尾空白。"""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    out: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            buf.append("|")
            i += 2
        elif ch == "|":
            out.append("".join(buf).strip())
            buf = []
            i += 1
        else:
            buf.append(ch)
            i += 1
    out.append("".join(buf).strip())
    return out


def _align_of(cell: str) -> str | None:
    """分隔行单元格 → 对齐名；不是分隔行单元格则 None。"""
    c = cell.strip()
    if not _ALIGN_RE.match(c):
        return None
    if c.endswith(":"):
        return "center" if c.startswith(":") else "right"
    return "left"


def parse(text: str) -> tuple[list[str], list[list[str]], list[str]]:
    """解析管道表格 →（表头, 行, 对齐列表，缺省 left）。

    不合形状（无分隔行/列数不齐）抛 ValueError——静默容错只会把
    坏数据悄悄传下去。
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError("表格至少要有表头行和分隔行")
    header = _split_row(lines[0])
    aligns_raw = [_align_of(c) for c in _split_row(lines[1])]
    if None in aligns_raw or len(aligns_raw) != len(header):
        raise ValueError("第二行不是合法分隔行（形如 | --- | :--: | ---: |）")
    rows: list[list[str]] = []
    for ln in lines[2:]:
        cells = _split_row(ln)
        if len(cells) != len(header):
            raise ValueError(f"列数不齐: {ln!r}（{len(cells)} != {len(header)}）")
        rows.append(cells)
    return header, rows, aligns_raw


def render(header: list[str], rows: list[list[str]],
           aligns: list[str] | None = None) -> str:
    """表头 + 行 + 对齐 → 等宽补齐的表格文本（列宽取最长单元格）。"""
    n = len(header)
    if aligns is None:
        aligns = ["left"] * n
    if len(aligns) != n or any(a not in _DASH for a in aligns):
        raise ValueError(f"对齐规格不合法: {aligns!r}")
    esc_header = [escape_cell(h) for h in header]
    esc_rows = [[escape_cell(c) for c in r] for r in rows]
    widths = [len(h) for h in esc_header]
    for r in esc_rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))

    def _row(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[i])
                                 for i, c in enumerate(cells)) + " |"

    lines = [_row(esc_header),
             _row([_DASH[a].ljust(widths[i])
                   for i, a in enumerate(aligns)])]
    lines += [_row(r) for r in esc_rows]
    return "\n".join(lines)


def _selftest() -> None:
    # 基本解析：表头/行/对齐
    t = "| 名称 | 数值 |\n| --- | --: |\n| a-b | 3 |\n| 中文 | 12 |"
    header, rows, aligns = parse(t)
    assert header == ["名称", "数值"]
    assert rows == [["a-b", "3"], ["中文", "12"]]
    assert aligns == ["left", "right"]

    # 容忍省略首尾管道与多余空白
    h2, r2, a2 = parse("x | y\n :-: | ---\n  1 | 2 ")
    assert (h2, r2, a2) == (["x", "y"], [["1", "2"]], ["center", "left"])

    # 管道转义：单元格里的 | 不切开，渲染时再转回去
    t3 = "| k | v |\n| --- | --- |\n| a\\|b | c |"
    h3, r3, _ = parse(t3)
    assert r3 == [["a|b", "c"]]
    assert "a\\|b" in render(h3, r3)                # 渲染时管道重新转义
    h4, r4, _ = parse(render(h3, r3))
    assert (h4, r4) == (h3, r3)                     # 渲染→解析 往返等值

    # 渲染结果可被原样解析回去，且补齐列宽
    canonical = render(["id", "name"], [["1", "张三"], ["2", "bob"]],
                       ["right", "left"])
    assert parse(canonical) == (["id", "name"],
                                [["1", "张三"], ["2", "bob"]],
                                ["right", "left"])
    assert "| --- |" not in canonical               # 分隔行也是补齐的

    # 坏输入显式报错
    for bad in ("| a |\n| b |", "| a | b |\n| --- |\n| 1 | 2 |",
                "| a | b |\n| --- | --- |\n| 1 |"):
        try:
            parse(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad!r}")

    print("selftest ok: 解析/对齐/省略管道/管道转义/往返/坏输入报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="Markdown 管道表格解析/渲染")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--file", default=None, help="解析该 Markdown 文件")
    ap.add_argument("--render", nargs="+", default=None,
                    help="每行一条记录，逗号分隔；首条为表头")
    args = ap.parse_args()
    if args.selftest or (args.file is None and args.render is None):
        _selftest()
        if args.file is None and args.render is None:
            return
    if args.file is not None:
        with open(args.file, encoding="utf-8") as f:
            header, rows, aligns = parse(f.read())
        print(f"表头: {header}\n对齐: {aligns}")
        for r in rows:
            print(r)
    if args.render is not None:
        records = [ln.split(",") for ln in args.render]
        print(render(records[0], records[1:]))


if __name__ == "__main__":
    main()
