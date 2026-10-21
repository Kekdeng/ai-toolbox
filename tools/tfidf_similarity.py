#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tfidf_similarity.py — 零模型的文本相似度：TF-IDF + 余弦（纯标准库）。

不需要 embedding API、不需要任何模型：中文按单字 + 相邻 bigram 切分，
英文按词切分，TF × smooth-IDF 后做 L2 归一化，算余弦。适合去重、粗排、
「这两段话像不像」的快速判断；要求语义级相似度请用真正的 embedding。

用法：
    python tools/tfidf_similarity.py --selftest
    python tools/tfidf_similarity.py --a "机器学习" --b "深度学习"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def tokenize(text: str) -> list[str]:
    """小写化后：ASCII 连续串按词、汉字按单字；另为相邻汉字对加 bigram。"""
    text = text.lower()
    singles = _TOKEN_RE.findall(text)
    han = [t for t in singles if len(t) == 1 and "一" <= t <= "鿿"]
    bigrams = [a + b for a, b in zip(han, han[1:])]
    return singles + bigrams


def _l2(vec: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def tfidf_vectors(docs: list[str]) -> list[dict[str, float]]:
    """TF × smooth-IDF（ln((1+N)/(1+df)) + 1，sklearn 口径）并 L2 归一化。"""
    tokenized = [tokenize(d) for d in docs]
    n = len(docs)
    df: Counter = Counter()
    for toks in tokenized:
        df.update(set(toks))
    vecs: list[dict[str, float]] = []
    for toks in tokenized:
        tf = Counter(toks)
        vec = {t: c * (math.log((1 + n) / (1 + df[t])) + 1.0)
               for t, c in tf.items()}
        vecs.append(_l2(vec))
    return vecs


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """两个（L2 归一化）向量的余弦；空向量定义为 0。"""
    if not a or not b:
        return 0.0
    if len(b) < len(a):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def similarity(a: str, b: str) -> float:
    """两段文本的相似度 ∈ [0, 1]。"""
    return cosine(*tfidf_vectors([a, b]))


def rank(query: str, docs: list[str]) -> list[tuple[int, float]]:
    """query 对 docs 的粗排：[(下标, 相似度)] 按相似度降序。"""
    vecs = tfidf_vectors([query, *docs])
    q = vecs[0]
    scores = [(i, cosine(q, v)) for i, v in enumerate(vecs[1:])]
    return sorted(scores, key=lambda x: x[1], reverse=True)


def _selftest() -> None:
    # 完全相同 → 1；完全无交集 → 0
    assert abs(similarity("机器学习很有趣", "机器学习很有趣") - 1.0) < 1e-12
    assert similarity("机器学习很有趣", "今天天气不错") == 0.0

    # 半相似 > 无相似
    pair = similarity("我喜欢机器学习", "我讨厌机器学习")
    none = similarity("我喜欢机器学习", "今天天气不错")
    assert pair > 0 and none == 0.0 and pair > none, (pair, none)

    # 粗排：语义最近的文档排第一
    ranked = rank("机器学习", ["深度学习入门", "红烧肉做法", "机器学习实战"])
    assert ranked[0][0] == 2, ranked
    assert ranked[0][1] >= ranked[1][1] >= ranked[2][1]

    # 向量确实 L2 归一化；空输入余弦为 0
    vecs = tfidf_vectors(["你好世界", "hello world"])
    for vec in vecs:
        assert abs(math.sqrt(sum(v * v for v in vec.values())) - 1.0) < 1e-9
    assert cosine({}, {"a": 1.0}) == 0.0

    print("selftest ok: 相同=1 无交集=0，粗排序 [实战, 深度学习, 红烧肉] 正确")


def main() -> None:
    ap = argparse.ArgumentParser(description="TF-IDF 文本相似度（零模型）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--a", default=None, help="文本 A")
    ap.add_argument("--b", default=None, help="文本 B")
    args = ap.parse_args()
    if args.selftest or args.a is None or args.b is None:
        _selftest()
        if args.a is None or args.b is None:
            return
    print(f"相似度 = {similarity(args.a, args.b):.4f}")


if __name__ == "__main__":
    main()
