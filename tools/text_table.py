#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""text_table.py — 文本表格渲染：自动列宽 + CJK 宽度感知 + 对齐。

终端里打印报表的最小件。列宽按「显示宽度」取各列最大值——中文等
全角字符按 2 格计（Unicode East Asian Width W/F），中西文混排不
错位。对齐三档：l 左（默认）、r 右、auto 数值列自动右对齐（列内
全部匹配 -?d+(.d)? 才算数值，表头不参与）。

输出 ASCII 网格（+---+ 风格），单元格内换行直接拒绝——表格是
单行世界的契约，多行请先自己拆行成多条记录。

用法：
    python tools/text_table.py --selftest
    python tools/text_table.py --headers "名称,数量" --rows "苹果,3|香蕉,20"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re
import unicodedata

_NUM = re.compile(r"-?\d+(\.\d+)?")


def _width(s: str) -> int:
    """显示宽度：East Asian W/F 记 2，其余记 1。"""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
               for c in s)


def _pad(s: str, width: int, align: str) -> str:
    gap = width - _width(s)
    if align == "r":
        return " " * gap + s
    return s + " " * gap                # l（c 居中这里不做，保持最小）


def _check_cell(v: str, where: str) -> str:
    if "\n" in v or "\r" in v:
        raise ValueError(f"{where} 含换行（表格单元格须单行）: {v!r}")
    return v


def render_table(headers: list[str], rows: list[list[str]],
                 align: list[str] | None = None,
                 numeric_right: bool = True) -> str:
    """headers + rows → ASCII 网格表；align 逐列 l/r，缺省 auto/l。"""
    for r in rows:
        if len(r) != len(headers):
            raise ValueError(f"行宽 {len(r)} ≠ 表头 {len(headers)}: {r!r}")
    cells = [[_check_cell(str(v), "单元格") for v in r] for r in rows]
    head = [_check_cell(str(h), "表头") for h in headers]
    ncol = len(head)
    widths = [_width(head[c]) for c in range(ncol)]
    for r in cells:
        widths = [max(w, _width(r[c])) for c, w in enumerate(widths)]
    if align is None:
        align = []
        for c in range(ncol):
            numeric = (numeric_right and rows
                       and all(_NUM.fullmatch(str(r[c])) for r in rows))
            align.append("r" if numeric else "l")
    if len(align) != ncol or any(a not in ("l", "r") for a in align):
        raise ValueError(f"align 须为 {ncol} 个 l/r: {align!r}")

    def border() -> str:
        return "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def line(vals: list[str], als: list[str]) -> str:
        return "|" + "|".join(f" {_pad(v, widths[c], als[c])} "
                              for c, v in enumerate(vals)) + "|"

    out = [border(), line(head, ["l"] * ncol), border()]
    out += [line(r, align) for r in cells]
    out.append(border())
    return "\n".join(out)


def _selftest() -> None:
    # 中西文混排不错位：中文计 2 格，列宽取最大显示宽度（手算全表）
    pic = render_table(["名称", "qty"], [["苹果", "3"], ["banana", "20"]])
    assert pic.splitlines() == [
        "+--------+-----+",
        "| 名称   | qty |",
        "+--------+-----+",
        "| 苹果   |   3 |",
        "| banana |  20 |",
        "+--------+-----+",
    ], pic

    # auto 数值右对齐：列全为数字才右（表头不参与），手算全表
    pic = render_table(["h", "n"], [["x", "3"], ["y", "20"]])
    assert pic.splitlines() == [
        "+---+----+",
        "| h | n  |",
        "+---+----+",
        "| x |  3 |",
        "| y | 20 |",
        "+---+----+",
    ], pic
    # 一列混入非数字 → 整列左对齐
    lines = render_table(["n"], [["3"], ["x"]]).splitlines()
    assert lines[3] == "| 3 |" and lines[4] == "| x |", lines[3:5]

    # 显式 align 覆盖 auto
    lines = render_table(["a"], [["1"]], align=["l"]).splitlines()
    assert lines[3] == "| 1 |", lines[3]

    # 空行：只有表头
    lines = render_table(["a", "b"], []).splitlines()
    assert lines == ["+---+---+", "| a | b |", "+---+---+", "+---+---+"]

    # 报错：行宽不齐 / 单元格换行 / align 非法
    for bad in (lambda: render_table(["a"], [["1"], ["1", "2"]]),
                lambda: render_table(["a"], [["x\ny"]]),
                lambda: render_table(["a"], [["1"]], align=["c"])):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    print("selftest ok: CJK 宽度/auto 右对齐/显式对齐/空表/报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="ASCII 表格渲染")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--headers", default=None, help="逗号分隔的表头")
    ap.add_argument("--rows", default=None,
                    help="行按 | 分隔、单元格按逗号分隔")
    args = ap.parse_args()
    if args.selftest or args.headers is None:
        _selftest()
        if args.headers is None:
            return
    rows = [[c for c in r.split(",")] for r in (args.rows or "").split("|")
            if r]
    print(render_table(args.headers.split(","), rows))


if __name__ == "__main__":
    main()
