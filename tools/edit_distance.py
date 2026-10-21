#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""edit_distance.py — Levenshtein 编辑距离 + 对齐路径回放（纯标准库）。

除了「两个字符串差几步」，还回放一条**确定性的**编辑路径（= / 替换 / 删除 /
插入，回溯优先级固定），可以看清每一步怎么改。附带归一化相似度
（1 − 距离/较长串长度）。适合模糊匹配、拼写纠错、OCR/ASR 结果对比。

用法：
    python tools/edit_distance.py --selftest
    python tools/edit_distance.py --a kitten --b sitting

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse

# 操作三元组：(op, a 字符, b 字符)；op ∈ {"=", "sub", "del", "ins"}
Op = tuple[str, str, str]


def edit_ops(a: str, b: str) -> list[Op]:
    """完整 DP + 回溯，返回一条从 a 改成 b 的对齐路径（确定性的）。"""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i - 1][j],
                                   dp[i][j - 1])

    ops: list[Op] = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and a[i - 1] == b[j - 1]:
            ops.append(("=", a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            ops.append(("sub", a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("del", a[i - 1], ""))
            i -= 1
        else:
            ops.append(("ins", "", b[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def levenshtein(a: str, b: str) -> int:
    """编辑距离（= 非替换类操作计数）。"""
    return sum(1 for op, _x, _y in edit_ops(a, b) if op != "=")


def similarity(a: str, b: str) -> float:
    """归一化相似度 ∈ [0, 1]：1 − 距离/max(len(a), len(b), 1)。"""
    return 1.0 - levenshtein(a, b) / max(len(a), len(b), 1)


def _selftest() -> None:
    # 经典答案
    assert levenshtein("", "") == 0
    assert levenshtein("", "ab") == 2
    assert levenshtein("abc", "abc") == 0
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("flaw", "lawn") == 2
    assert levenshtein("机器学习", "机器学习!") == 1
    assert levenshtein("kitten", "sitting") == levenshtein("sitting", "kitten")

    # 对齐路径确实把 a 改成了 b（用 op 序列重放验证）
    for a, b in (("kitten", "sitting"), ("flaw", "lawn"), ("", "abc"),
                 ("abc", ""), ("你好", "你好"), ("abcd", "ac")):
        ops = edit_ops(a, b)
        out: list[str] = []
        ai = 0
        for op, x, y in ops:
            if op in ("=", "sub"):
                assert x == a[ai], (a, b, ops)
                out.append(y)
                ai += 1
            elif op == "del":
                ai += 1
            else:                                   # ins
                out.append(y)
        assert ai == len(a), (a, b, ops)
        assert "".join(out) == b, (a, b, ops)

    # 相似度
    assert similarity("abc", "abc") == 1.0
    assert similarity("abc", "xyz") == 0.0
    assert similarity("", "") == 1.0

    print("selftest ok: kitten→sitting=3、路径重放还原、相似度 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="Levenshtein 编辑距离与对齐")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--a", default=None, help="源字符串")
    ap.add_argument("--b", default=None, help="目标字符串")
    args = ap.parse_args()
    if args.selftest or args.a is None or args.b is None:
        _selftest()
        if args.a is None or args.b is None:
            return
    ops = edit_ops(args.a, args.b)
    print(f"距离 = {levenshtein(args.a, args.b)}，"
          f"相似度 = {similarity(args.a, args.b):.3f}")
    print("路径: " + " ".join(f"{op}:{x}->{y}" if op != "=" else x
                             for op, x, y in ops))


if __name__ == "__main__":
    main()
