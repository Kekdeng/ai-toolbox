#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""weighted_sample.py — 加权抽样：放回轮盘 + 不放回 Efraimidis–Spirakis。

按权重抽样本，权重大者机会多。两种口径一次给全：

- 放回（with replacement）：轮盘赌 + 前缀和二分，同一元素可重复出现；
- 不放回（without replacement）：Efraimidis–Spirakis 算法——每个元素
  算 key = u^(1/w)（u~U(0,1)），取 key 最大的 k 个。一次排序等价于
  依次做 k 次加权不放回抽取，且与抽取顺序无关。

rng 注入（random.Random），固定种子完全确定可复现；零权重永不入选，
负权重构造期拒绝。

用法：
    python tools/weighted_sample.py --selftest

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import bisect
import random


def _validated(items: list, weights: list[float]) -> None:
    if len(items) != len(weights):
        raise ValueError("items 与 weights 长度不一致")
    if any(w < 0 for w in weights):
        raise ValueError("权重不能为负")


def sample_with_replacement(items: list, weights: list[float], k: int,
                            rng: random.Random) -> list:
    """放回抽样 k 次：轮盘赌前缀和 + 二分定位。"""
    _validated(items, weights)
    total = sum(weights)
    if k < 0:
        raise ValueError("k 不能为负")
    if total <= 0:
        if k == 0:
            return []
        raise ValueError("总权重必须为正（除非 k=0）")
    prefix: list[float] = []
    acc = 0.0
    for w in weights:
        acc += w
        prefix.append(acc)
    out: list = []
    for _ in range(k):
        r = rng.random() * total
        out.append(items[bisect.bisect_right(prefix, r)])
    return out


def sample_without_replacement(items: list, weights: list[float], k: int,
                               rng: random.Random) -> list:
    """不放回抽 k 个：key = u^(1/w) 取最大；零权重不参选。"""
    _validated(items, weights)
    if not 0 <= k <= len(items):
        raise ValueError("k 须在 [0, len(items)]")
    keyed: list[tuple[float, int]] = []
    for i, w in enumerate(weights):
        if w > 0:
            keyed.append((rng.random() ** (1.0 / w), i))
    keyed.sort(key=lambda t: t[0], reverse=True)
    return [items[i] for _, i in keyed[:k]]


def _selftest() -> None:
    items = ["a", "b", "c", "d"]
    weights = [1.0, 2.0, 3.0, 4.0]

    # 确定性：同种子两次完全一致（放回 / 不放回各自成立）
    r1, r2 = random.Random(42), random.Random(42)
    s1 = sample_with_replacement(items, weights, 6, r1)
    s2 = sample_with_replacement(items, weights, 6, r2)
    assert s1 == s2 and len(s1) == 6 and set(s1) <= set(items)
    w1 = sample_without_replacement(items, weights, 2, random.Random(42))
    w2 = sample_without_replacement(items, weights, 2, random.Random(42))
    assert w1 == w2 and len(w1) == 2 and len(set(w1)) == 2

    # 边界：k=0 空；不放回 k=n 时零权重之外全选；零权重永不入选
    assert sample_without_replacement(items, weights, 0, random.Random(1)) == []
    assert set(sample_without_replacement(
        items, weights, 4, random.Random(1))) == set(items)
    zw = sample_without_replacement(["x", "y"], [0.0, 5.0], 1,
                                    random.Random(7))
    assert zw == ["y"]
    for _ in range(50):
        assert "x" not in sample_with_replacement(
            ["x", "y"], [0.0, 1.0], 3, random.Random(7))

    # 倾向性：不放回 k=1 时，权重 100 的远多于权重 1（200 个种子位重放）
    heavy = sum(sample_without_replacement(["big", "small"], [100.0, 1.0],
                                           1, random.Random(t))[0] == "big"
                for t in range(200))
    assert heavy >= 195, heavy

    # 不放回：k 越界 / 负权重 / 长度不齐 → 构造期报错
    for bad_k in (-1, 5):
        try:
            sample_without_replacement(items, weights, bad_k,
                                       random.Random(1))
        except ValueError:
            pass
        else:
            raise AssertionError(f"k={bad_k} 应报错")
    for bad in ((["a"], [1, 2]), (["a", "b"], [1, -2])):
        try:
            sample_without_replacement(bad[0], bad[1], 1, random.Random(1))
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad} 应报错")

    print(f"selftest ok: 确定性/边界/零权重/倾向性 {heavy}/200/构造期报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="加权抽样（放回/不放回）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args()
    _selftest()


if __name__ == "__main__":
    main()
