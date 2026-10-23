#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""csv_pipeline.py — 表格一键读取：探方言 → 解析 → 列级类型推断。

csv_sniffer 管方言、csv_json_convert 管转换，这里把两步和类型
补全串成一把刀：read_table(text) 直接给 list[dict]——

- 方言自动判：候选分隔符（, ; Tab |）引号感知计数一致才入围，
  解析全行等宽 >1 列才合格，残留引号判据择优（与 csv_sniffer
  同口径）；判不出给 ValueError；
- 列级类型：整列全匹配才转——全 int 列转 int、全 float 列转
  float、全 true/false 系转 bool；空串一律 None（缺值不冒充 0）；
  混入任一非类型值整列保持 str——列的类型是全列的契约；
- 表头即键：重名/空表头报错；数据行宽与表头不齐报错带行号。

用法：
    python tools/csv_pipeline.py --selftest
    python tools/csv_pipeline.py --text "name;qty\\nx;3"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import csv
import io
import re

_INT = re.compile(r"[+-]?\d+")
_FLOAT = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_BOOL = frozenset({"true", "false"})


def _count_outside_quotes(line: str, delim: str) -> int:
    """引号外的分隔符个数（引号成对开合）。"""
    count = 0
    in_quote: str | None = None
    for ch in line:
        if in_quote is not None:
            if ch == in_quote:
                in_quote = None
        elif ch in "\"'":
            in_quote = ch
        elif ch == delim:
            count += 1
    return count


def sniff(text: str, delimiters: str = ",;\t|") -> tuple[str, str]:
    """→ (分隔符, 引号字符)；两级判定，判不出 ValueError。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("输入为空")
    cands = [d for d in delimiters
             if (counts := [_count_outside_quotes(ln, d) for ln in lines])
             and counts[0] > 0 and len(set(counts)) == 1]
    if not cands:
        raise ValueError("无法判断分隔符：候选在各样本行上的列数不一致或为 0")
    best = None                       # (残留数, 分隔符序, 引号序, d, q)
    for di, d in enumerate(cands):
        for qi, q in enumerate("\"'"):
            parsed = [r for r in csv.reader(io.StringIO(text, newline=""),
                                            delimiter=d, quotechar=q) if r]
            widths = {len(r) for r in parsed}
            if len(widths) != 1 or min(widths) < 2:
                continue
            residual = sum(f.count(o) for r in parsed for f in r
                           for o in "\"'" if o != q)
            key = (residual, di, qi)
            if best is None or key < best[:3]:
                best = (key[0], key[1], key[2], d, q)
    if best is None:
        raise ValueError("解析验证失败：没有候选方言能全行等宽解析")
    return best[3], best[4]


def _typed_column(values: list[str]) -> list[object]:
    """整列全匹配才转类型；空串 → None；混型保持 str。"""
    stripped = [v.strip() for v in values]
    if all(v == "" for v in stripped):
        return [None] * len(stripped)
    non_empty = [v for v in stripped if v != ""]
    low = [v.lower() for v in non_empty]
    if all(v in _BOOL for v in low):
        return [None if v == "" else v.lower() == "true"
                for v in stripped]
    if all(_INT.fullmatch(v) for v in non_empty):
        return [None if v == "" else int(v) for v in stripped]
    if all(_FLOAT.fullmatch(v) for v in non_empty):
        return [None if v == "" else float(v) for v in stripped]
    return stripped


def read_table(text: str) -> list[dict]:
    """一键读表：探方言 → 解析 → 列级类型 → list[dict]。"""
    delim, quote = sniff(text)
    rows = [r for r in csv.reader(io.StringIO(text, newline=""),
                                  delimiter=delim, quotechar=quote) if r]
    header = [h.strip() for h in rows[0]]
    if any(not h for h in header):
        raise ValueError("表头含空列名")
    if len(set(header)) != len(header):
        raise ValueError(f"表头重名: {header}")
    if len(rows) > 1:
        widths = {len(r) for r in rows[1:]}
        if widths != {len(header)}:
            raise ValueError(f"数据行宽与表头不齐: 各行宽 {sorted(widths)}，"
                             f"表头 {len(header)}")
    cols = list(zip(*rows[1:])) if len(rows) > 1 else []
    typed = [_typed_column(list(col)) for col in cols]
    return [dict(zip(header, [typed[c][i] for c in range(len(header))]))
            for i in range(len(rows) - 1)]


def _selftest() -> None:
    # 四方言 + 引号感知 + 列级类型一次到位（手算全量）
    rows = read_table('name;qty;price;ok\n"Smith; J";2;3.5;true\n'
                      "lee;0;;false\n")
    assert rows == [{"name": "Smith; J", "qty": 2, "price": 3.5,
                     "ok": True},
                    {"name": "lee", "qty": 0, "price": None,
                     "ok": False}], rows

    # 逗号方言、中文列名、负整数
    rows = read_table("名称,分\n甲,-3\n乙,+7\n")
    assert rows == [{"名称": "甲", "分": -3}, {"名称": "乙", "分": 7}], rows

    # 混型列保持 str（v 列全 int 转 int，w 列混型整列 str）
    rows = read_table("v,w\n1,x\n2,3\n")
    assert rows == [{"v": 1, "w": "x"}, {"v": 2, "w": "3"}], rows
    rows = read_table("v,w\n1.5,2\n2,3.5\n")  # int+float 混 → float 列
    assert rows == [{"v": 1.5, "w": 2.0}, {"v": 2.0, "w": 3.5}], rows

    # 只有表头 → 空行列表
    assert read_table("a,b\n") == []

    # 报错：单列不可判 / 表头空名 / 表头重名 / 行宽不齐 / 空输入
    for bad in ("a\nb\nc", "", "a,,b\n1,2,3\n", "a,a\n1,2\n",
                "a,b\n1\n"):
        try:
            read_table(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 应报错")

    print("selftest ok: 四方言/引号感知/列级类型/混型退化/表头与行宽报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="表格一键读取（方言+类型）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--text", default=None, help="CSV 文本")
    ap.add_argument("--file", default=None, help="CSV 文件路径")
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
    for row in read_table(text):
        print(row)


if __name__ == "__main__":
    main()
