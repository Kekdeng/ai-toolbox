#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fuzzy_match.py — 字符串模糊匹配：归一化相似度 + 阈值排名（rapidfuzz 口径简版）。

零依赖场景下的 process.extract：给一个 query 和候选列表，返回
[(候选, 相似度, 原下标)] 按相似度降序、同分按下标稳定排序。

相似度口径：1 - 编辑距离/max(len)，手算可验（kitten/sitting =
1 - 3/7 = 4/7）；双空串 = 1.0，单空 = 0.0。score_cutoff 过滤、
limit 截断、CJK 按字符计。

用法：
    python tools/fuzzy_match.py --selftest
    python tools/fuzzy_match.py --query aple --choices "apple,banana,apply"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse


def _levenshtein(a: str, b: str) -> int:
    """编辑距离（单行滚动的经典 DP）。"""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1,          # 删除
                           cur[j - 1] + 1,       # 插入
                           prev[j - 1] + (ca != cb)))   # 替换/继承
        prev = cur
    return prev[-1]


def ratio(a: str, b: str) -> float:
    """归一化相似度 ∈ [0, 1]：1 - 距离/max(长度)；双空 = 1.0。"""
    m = max(len(a), len(b))
    if m == 0:
        return 1.0
    return 1.0 - _levenshtein(a, b) / m


def extract(query: str, choices: list[str], limit: int | None = None,
            score_cutoff: float = 0.0) -> list[tuple[str, float, int]]:
    """候选按相似度排名：[(choice, score, index)]，同分按下标稳定。"""
    hits = [(c, ratio(query, c), i) for i, c in enumerate(choices)]
    hits = [t for t in hits if t[1] >= score_cutoff]
    hits.sort(key=lambda t: (-t[1], t[2]))
    return hits[:limit] if limit is not None else hits


def _selftest() -> None:
    # 相似度手算基线
    assert ratio("kitten", "kitten") == 1.0
    assert abs(ratio("kitten", "sitting") - (1 - 3 / 7)) < 1e-12
    assert ratio("", "") == 1.0 and ratio("", "abc") == 0.0
    assert abs(ratio("微信支付", "微信支村") - 0.75) < 1e-12   # 距离 1 / 4
    assert 0.0 <= ratio("abc", "xyz") < 1.0

    # 排名：aple → apple(0.8) > apply(0.6) > banana
    res = extract("aple", ["apple", "banana", "apply"])
    assert res[0][:2] == ("apple", 0.8), res
    assert [t[0] for t in res] == ["apple", "apply", "banana"]

    # limit 截断与 score_cutoff 过滤（含等号边界）
    assert [t[0] for t in extract("aple", ["apple", "banana", "apply"],
                                  limit=2)] == ["apple", "apply"]
    assert extract("aple", ["banana", "apply"], score_cutoff=0.7) == []
    assert extract("ab", ["ax"], score_cutoff=0.5)[0][0] == "ax"

    # 同分稳定：按下标次序，两次调用一致
    tie = extract("ab", ["ab", "ab", "ax"])
    assert [t[2] for t in tie] == [0, 1, 2], tie
    assert extract("ab", ["ab", "ab", "ax"]) == tie

    print("selftest ok: 手算相似度/排名/limit/阈值含等号/同分稳定 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="字符串模糊匹配（阈值排名）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--query", default=None, help="查询串")
    ap.add_argument("--choices", default=None, help="逗号分隔的候选串")
    ap.add_argument("--cutoff", type=float, default=0.0,
                    help="相似度下限（默认 0.0）")
    ap.add_argument("--limit", type=int, default=None, help="最多返回几个")
    args = ap.parse_args()
    if args.selftest or args.query is None:
        _selftest()
        if args.query is None:
            return
    choices = [c for c in (args.choices or "").split(",") if c]
    for c, s, _ in extract(args.query, choices, args.limit, args.cutoff):
        print(f"{s:.3f}  {c}")


if __name__ == "__main__":
    main()
