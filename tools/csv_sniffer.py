#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""csv_sniffer.py — CSV 方言探测：分隔符 + 引号字符，两级判定。

拿到未知来源的表格文本，先回答「这是什么方言」再谈解析。两级判定：

1. 计数级：对每个候选分隔符（默认 `,` `;` Tab `|`），quote 感知地数每行
   「引号外」出现次数——各行相等且 >0 才入围。引号感知防止
   `"Doe, John"` 里的逗号把分号数据带偏；
2. 解析级：入围分隔符 × 候选引号字符逐一真解析（csv.reader），
   全行等宽且 >1 列才合格；合格里选「字段残留对方引号字符最少」的，
   再并列按候选顺序（逗号优先，双引号优先）。

启发式有边界：散文式撇号（it's）可能干扰引号感知；解析级兜底常见误判，
两级都失守时按计数级最优者 + 默认双引号尽力返回。

用法：
    python tools/csv_sniffer.py --selftest
    python tools/csv_sniffer.py --text $'name;age\n"Doe, John";30'
    python tools/csv_sniffer.py --file data.csv --show-rows

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import csv
import io


def _count_outside_quotes(line: str, delim: str, quotes: str = "\"'") -> int:
    """数一行里「引号外」的分隔符个数；引号字符成对开合。"""
    count = 0
    in_quote: str | None = None
    for ch in line:
        if in_quote is not None:
            if ch == in_quote:
                in_quote = None
        elif ch in quotes:
            in_quote = ch
        elif ch == delim:
            count += 1
    return count


def _parse(text: str, delim: str, quotechar: str) -> list[list[str]]:
    """按给定方言解析，跳过空行（csv 模块负责引号内嵌分隔符/转义）。"""
    return [r for r in csv.reader(io.StringIO(text, newline=""),
                                  delimiter=delim, quotechar=quotechar) if r]


def sniff(text: str, delimiters: str = ",;\t|",
          quotes: str = "\"'") -> dict[str, str]:
    """探测方言 → {"delimiter": …, "quotechar": …}；判不出抛 ValueError。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("输入为空")
    cands = []
    for d in delimiters:
        counts = [_count_outside_quotes(ln, d) for ln in lines]
        if counts[0] > 0 and len(set(counts)) == 1:
            cands.append(d)
    if not cands:
        raise ValueError("无法判断分隔符：候选在各样本行上的列数不一致或为 0")
    best = None                       # (残留数, 分隔符序, 引号序, d, q)
    for di, d in enumerate(cands):
        for qi, q in enumerate(quotes):
            parsed = _parse(text, d, q)
            widths = {len(r) for r in parsed}
            if len(widths) != 1 or min(widths) < 2:
                continue
            residual = sum(f.count(o) for r in parsed for f in r
                           for o in quotes if o != q)
            key = (residual, di, qi)
            if best is None or key < best[:3]:
                best = (key[0], key[1], key[2], d, q)
    if best is None:                  # 解析级全部失守 → 计数级尽力返回
        return {"delimiter": cands[0], "quotechar": quotes[0]}
    return {"delimiter": best[3], "quotechar": best[4]}


def rows(text: str, **kw) -> list[list[str]]:
    """一步到位：先探方言，再全量解析。"""
    d = sniff(text, **kw)
    return _parse(text, d["delimiter"], d["quotechar"])


def _selftest() -> None:
    # 四种方言：分隔符各就各位
    assert sniff("a,b,c\n1,2,3\n4,5,6") == {"delimiter": ",", "quotechar": '"'}
    assert sniff("a;b;c\n1;2;3") == {"delimiter": ";", "quotechar": '"'}
    assert sniff("a\tb\tc\n1\t2\t3") == {"delimiter": "\t", "quotechar": '"'}
    assert sniff("a|b|c\n1|2|3") == {"delimiter": "|", "quotechar": '"'}

    # 引号感知："Doe, John" 的逗号不把分号数据带偏
    r = sniff('name;age\n"Doe, John";30')
    assert r["delimiter"] == ";", r

    # 引号字符识别：单引号方言嵌逗号——双引号口径会把列撕开，残留判据选单引号
    assert sniff("'a,b',c\n'd,e',f") == {"delimiter": ",", "quotechar": "'"}

    # 双引号内嵌分隔符 + 成对转义，解析往返无损
    text2 = 'name,note\n"say ""hi""",ok\n"see, ya",fine'
    r = sniff(text2)
    assert r == {"delimiter": ",", "quotechar": '"'}, r
    assert _parse(text2, ",", '"')[1] == ['say "hi"', "ok"]

    # CRLF 行尾不碍事
    assert sniff("a,b\r\n1,2\r\n")["delimiter"] == ","

    # 判不出：单列文本 / 空输入 → 报错
    for bad in ("a\nb\nc", ""):
        try:
            sniff(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 应报错")

    # rows() 一步到位且等宽
    rs = rows("x,y\n1,2\n3,4")
    assert rs == [["x", "y"], ["1", "2"], ["3", "4"]]
    assert len({len(r) for r in rs}) == 1

    print("selftest ok: 四方言/引号感知/引号字符/转义往返/CRLF/报错/rows 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="CSV 方言探测（分隔符/引号字符）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--text", default=None, help="待探测的 CSV 文本")
    ap.add_argument("--file", default=None, help="待探测的 CSV 文件路径")
    ap.add_argument("--show-rows", action="store_true", help="顺带打印解析结果")
    args = ap.parse_args()
    if args.selftest or (args.text is None and args.file is None):
        _selftest()
        if args.text is None and args.file is None:
            return
    text = (open(args.file, encoding="utf-8").read() if args.file
            else args.text)
    d = sniff(text)
    print(f"delimiter={d['delimiter']!r} quotechar={d['quotechar']!r}")
    if args.show_rows:
        for r in rows(text):
            print(r)


if __name__ == "__main__":
    main()
