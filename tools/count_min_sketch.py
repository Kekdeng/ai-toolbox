#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""count_min_sketch.py — Count-Min Sketch：流式频率估计，只高估不低估。

布隆过滤器管「见过没有」，CMS 管「见了多少」：w×d 的计数网格，每个
元素在每行落一格并累加；点查询取 d 格中的**最小值**——它只可能被
别的元素撞高，不可能比真实值小，所以估计值 ≥ 真值、误差 ≤ ε·N 的
概率 ≥ 1-δ。参数公式：w = ⌈e/ε⌉，d = ⌈ln(1/δ)⌉，内存 O(w·d)
与流中不同元素个数无关——这正是它与精确计数器的本质差异。

逐格相加可合并（merge），分布式聚合各机器 sketch 后汇总即可。
散列同 bloom_filter：一次 md5 出 h1/h2，奇数步长生成各行列。

用法：
    python tools/count_min_sketch.py --selftest

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import hashlib
import math

E = math.e


def optimal_params(epsilon: float, delta: float) -> tuple[int, int]:
    """误差界 ε·N、置信 1-δ 下的最优列数 w 与行数 d。"""
    if epsilon <= 0 or not 0 < delta < 1:
        raise ValueError("需要 epsilon>0 且 0<delta<1")
    w = math.ceil(E / epsilon)
    d = math.ceil(math.log(1 / delta))
    return w, d


class CountMinSketch:
    """w 列 × d 行；add 计数、estimate 点查询（只高估）、merge 可合并。"""

    def __init__(self, w: int, d: int) -> None:
        if w <= 0 or d <= 0:
            raise ValueError("w/d 必须为正")
        self.w = w
        self.d = d
        self.table = [[0] * w for _ in range(d)]
        self.total = 0

    def _cols(self, item: str) -> list[int]:
        digest = hashlib.md5(item.encode("utf-8")).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:], "big") | 1      # 奇数步长
        return [(h1 + j * h2) % self.w for j in range(self.d)]

    def add(self, item: str, n: int = 1) -> None:
        if n <= 0:
            raise ValueError("计数增量须为正")
        for row, col in zip(self.table, self._cols(item)):
            row[col] += n
        self.total += n

    def estimate(self, item: str) -> int:
        """点查询：d 格取最小——保证 ≥ 真值（可能被碰撞推高）。"""
        return min(row[col]
                   for row, col in zip(self.table, self._cols(item)))

    def merge(self, other: "CountMinSketch") -> None:
        """逐格相加；形状必须一致（同 w、同 d → 同散列列）。"""
        if (self.w, self.d) != (other.w, other.d):
            raise ValueError("合并要求形状一致")
        for row, orow in zip(self.table, other.table):
            for i in range(self.w):
                row[i] += orow[i]
        self.total += other.total


def _selftest() -> None:
    # 参数公式：ε=0.05 → w=⌈e/0.05⌉=55；δ=0.01 → d=⌈ln100⌉=5
    assert optimal_params(0.05, 0.01) == (55, 5)
    for bad in ((0.0, 0.1), (0.1, 0.0), (0.1, 1.0)):
        try:
            optimal_params(*bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad}")

    w, d = optimal_params(0.05, 0.01)
    cms = CountMinSketch(w, d)
    heavy = {"gpt": 1000, "embed": 500, "guard": 200}
    for k, n in heavy.items():
        cms.add(k, n)
    for i in range(2000):                        # 2000 个长尾噪声
        cms.add(f"noise-{i}")

    # 重桶：估计值夹在 [真值, 真值 + ε·N]（N = 3700 → 界 185）
    bound = math.ceil(0.05 * cms.total)
    assert cms.total == 3700
    for k, n in heavy.items():
        est = cms.estimate(k)
        assert n <= est <= n + bound, (k, n, est)
    # 长尾：真值 1，同样只可能被高估、不可能被低估
    assert 1 <= cms.estimate("noise-0") <= 1 + bound
    # 未出现过的元素：估计可能 > 0（碰撞），但绝不为负
    assert cms.estimate("never-seen") >= 0

    # 合并：同形状下逐格相加 ≡ 全量重放（散列确定、列位相同）
    #   a、b 各持一半写入，合并后与「一次写全」的 sketch 逐元素相等
    a, b = CountMinSketch(w, d), CountMinSketch(w, d)
    a.add("gpt", 600)
    a.add("embed", 500)
    b.add("gpt", 400)
    b.add("guard", 200)
    for i in range(1000):
        a.add(f"noise-{i}")
        b.add(f"noise-{1000 + i}")
    a.merge(b)
    assert a.total == cms.total == 3700
    assert a.estimate("gpt") == cms.estimate("gpt")
    assert a.estimate("noise-1234") == cms.estimate("noise-1234")
    try:
        a.merge(CountMinSketch(8, 2))
    except ValueError:
        pass
    else:
        raise AssertionError("形状不一致应报错")

    print(f"selftest ok: 参数公式/重桶界 {bound}/长尾不减/合并=重放/形状校验 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="Count-Min Sketch 频率估计")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--epsilon", type=float, default=0.05)
    ap.add_argument("--delta", type=float, default=0.01)
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    w, d = optimal_params(args.epsilon, args.delta)
    print(f"ε={args.epsilon} δ={args.delta} → w={w} 列 × d={d} 行，"
          f"内存 ≈ {w * d * 8 / 1024:.1f} KiB（int64 网格）")


if __name__ == "__main__":
    main()
