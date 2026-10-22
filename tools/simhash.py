#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""simhash.py — SimHash 近重复指纹：局部改动 → 相近指纹，海明距离判重。

minhash 管集合层面的 Jaccard，simhash 管整篇「像不像」：每个字符
n-gram 特征哈希成 64 位、按位加权投票（出现 +1 / 未出现 -1），
符号位连成指纹。近重复文本的指纹海明距离小（工程经验阈值 8 以内），
无关文本的距离在 32 上下浮动；比较就是 64 位异或数 1，O(1)。

特征用字符 trigram——中文免分词，与 text_cluster 同一口径。

用法：
    python tools/simhash.py --selftest
    python tools/simhash.py --text "一段文本" --other "另一段文本"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import hashlib
from collections import Counter


def simhash64(text: str, n: int = 3) -> int:
    """文本 → 64 位指纹（重复特征权重更高，用出现次数计票）。"""
    grams = Counter(text[i:i + n] for i in range(max(1, len(text) - n + 1))
                    ) if len(text) > n else Counter([text] if text else [])
    votes = [0] * 64
    for gram, w in grams.items():
        h = int.from_bytes(hashlib.md5(gram.encode("utf-8")).digest()[:8],
                           "big")
        for i in range(64):
            votes[i] += w if (h >> i) & 1 else -w
    out = 0
    for i in range(64):
        if votes[i] > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    """两指纹的海明距离（异或数 1）。"""
    return bin(a ^ b).count("1")


def near(a: int, b: int, max_dist: int = 8) -> bool:
    """距离 ≤ max_dist 判为近重复——阈值按业务调，64 位下 32 是随机线。"""
    return hamming(a, b) <= max_dist


def _selftest() -> None:
    t1 = "这是一段用于测试相似度检测的中文文本，长度适中且主题明确"
    t2 = "这是一段用于测试相似度检测的中文字符文本，长度适中且主题明确"  # 改两字
    t3 = "The quick brown fox jumps over the lazy dog repeatedly at dawn"

    # 完全相同：距离 0；指纹范围 64 位
    h1 = simhash64(t1)
    assert hamming(h1, simhash64(t1)) == 0
    assert 0 <= h1 < 2 ** 64

    # 局部改动：距离很小（近重判定）
    d_near = hamming(h1, simhash64(t2))
    assert d_near <= 8, d_near
    assert near(h1, simhash64(t2))

    # 无关文本：距离远离 0，靠近随机线 32
    d_far = hamming(h1, simhash64(t3))
    assert d_far >= 20, d_far
    assert not near(h1, simhash64(t3))

    # 距离的对称性与自反性
    assert hamming(0, 2 ** 64 - 1) == 64
    assert hamming(12345, 12345) == 0

    # 空文本与超短文本（不足 n 时整串作单特征）不崩、且可区分
    assert simhash64("") == 0
    assert hamming(simhash64("a"), simhash64("b")) > 0

    print(f"selftest ok: 相同=0/局部改动={d_near}≤8/无关={d_far}≥20/对称性/空输入 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="SimHash 近重复指纹")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--text", default=None, help="基准文本")
    ap.add_argument("--other", default=None, help="对比文本")
    ap.add_argument("--max-dist", type=int, default=8,
                    help="近重复的海明距离阈值（默认 8）")
    args = ap.parse_args()
    if args.selftest or args.text is None:
        _selftest()
        if args.text is None:
            return
    h1, h2 = simhash64(args.text), simhash64(args.other or "")
    d = hamming(h1, h2)
    print(f"指纹: {h1:016x} vs {h2:016x}\n"
          f"海明距离 = {d} → {'近重复' if d <= args.max_dist else '不同'}")


if __name__ == "__main__":
    main()
