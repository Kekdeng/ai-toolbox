#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""text_cluster.py — 零模型文本聚类：字符 n-gram Jaccard + 阈值贪心。

没有 embedding 服务、不想拉模型时，用字符 n-gram 的 Jaccard 相似度
做近重复文本的粗聚类（工单归并、FAQ 去重、badcase 分组）。
策略是贪心领袖聚类：每条文本与已有簇的代表比一次，相似度 ≥ 阈值就
进簇，否则自立新簇——O(k) 次比较，簇序 = 首成员出现序，完全确定性；
中文按字切 bigram 即可工作，无需分词。

用法：
    python tools/text_cluster.py --selftest
    python tools/text_cluster.py --texts "订单退款失败" "退款订单失败" "今天天气"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse


def char_ngrams(s: str, n: int = 2) -> set[str]:
    """字符级 n-gram 集合；长度不足 n 的串取整串，空串为空集。"""
    if len(s) <= n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard 相似度 |A∩B| / |A∪B|；双方皆空定义为 0（无可比特征）。"""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def cluster(texts: list[str], threshold: float = 0.5, n: int = 2
            ) -> list[list[int]]:
    """贪心阈值聚类；返回簇列表（每簇是输入下标，按首成员出现顺序）。"""
    grams = [char_ngrams(t, n) for t in texts]
    clusters: list[list[int]] = []
    for i, g in enumerate(grams):
        for c in clusters:
            if jaccard(g, grams[c[0]]) >= threshold:
                c.append(i)
                break
        else:
            clusters.append([i])
    return clusters


def representative(texts: list[str], members: list[int], n: int = 2) -> int:
    """簇代表：与簇内其他成员相似度总和最高的成员（平局取最靠前）。

    用于给簇起名/抽样人工检查——总和最高意味着它离簇心最近。
    """
    grams = [char_ngrams(texts[i], n) for i in members]
    best, best_score = members[0], -1.0
    for j, gj in enumerate(grams):
        score = sum(jaccard(gj, gk) for k, gk in enumerate(grams) if k != j)
        if score > best_score:
            best, best_score = members[j], score
    return best


def _selftest() -> None:
    # n-gram 与 Jaccard 的手算基线
    assert char_ngrams("abcd") == {"ab", "bc", "cd"}
    assert char_ngrams("ab", 2) == {"ab"} and char_ngrams("a", 2) == {"a"}
    assert char_ngrams("", 2) == set()
    g0, g1, g2 = (char_ngrams(t) for t in ("abcdabcd", "abcd", "xyzx"))
    assert abs(jaccard(g0, g1) - 0.75) < 1e-9          # 交 3 / 并 4
    assert jaccard(g0, g2) == 0.0
    assert jaccard(set(), set()) == 0.0

    # 贪心聚类：近重复进同簇，无关自立新簇；阈值升高则拆簇
    texts = ["abcdabcd", "abcd", "xyzx"]
    assert cluster(texts, threshold=0.6) == [[0, 1], [2]]
    assert cluster(texts, threshold=0.8) == [[0], [1], [2]]

    # 中文 bigram + 全同并列时代表元取最靠前
    #   今天天气/明天天气 的 bigram 交 2 并 4 → J=0.5
    zh = ["今天天气", "今天天气", "明天天气", "订单退款"]
    cs = cluster(zh, threshold=0.45)
    assert cs == [[0, 1, 2], [3]], cs
    assert representative(zh, cs[0]) == 0               # 三者得分并列 → 首位

    print("selftest ok: n-gram/Jaccard 基线/贪心聚类/阈值敏感/代表元 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="零模型文本聚类（n-gram Jaccard）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--texts", nargs="+", default=None, help="要聚类的文本")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="进簇阈值（默认 0.5）")
    ap.add_argument("--n", type=int, default=2, help="n-gram 窗口（默认 2）")
    args = ap.parse_args()
    if args.selftest or not args.texts:
        _selftest()
        if not args.texts:
            return
    for ci, members in enumerate(cluster(args.texts, args.threshold, args.n), 1):
        rep = representative(args.texts, members, args.n)
        print(f"簇{ci}（代表: {args.texts[rep]}）: {[args.texts[i] for i in members]}")


if __name__ == "__main__":
    main()
