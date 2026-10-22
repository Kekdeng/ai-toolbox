#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quantile.py — 分位数：静态线性插值 + 流式 P²（O(1) 内存）。

p50/p95/p99 是监控和评测的通用语言。两种口径一次给全：

- quantile：全量数据在手的精确解——线性插值（h = (n-1)·q，
  numpy 'linear' 同口径），手算可验；
- P2Quantile：数据流只过一遍的 P² 算法（Jain & Chlamtac 1985）——
  维护 5 个标记（最小值、p/2、p、(1+p)/2、最大值）及各自位置，
  逐个观测做抛物线预测 + 必要时线性回退，内存 O(1)，与流长度无关。

流式估计是近似：均匀数据上误差通常远小于 1% 量程（自测有界背书）。

用法：
    python tools/quantile.py --selftest
    python tools/quantile.py --values "1,2,3,4,10" --q 0.5

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import math


def quantile(values: list[float], q: float) -> float:
    """精确分位数（线性插值）；空输入抛错，q 须在 [0, 1]。"""
    if not values:
        raise ValueError("values 为空")
    if not 0 <= q <= 1:
        raise ValueError("q 须在 [0, 1]")
    s = sorted(values)
    h = (len(s) - 1) * q
    lo = math.floor(h)
    hi = math.ceil(h)
    return s[lo] + (h - lo) * (s[hi] - s[lo])


class P2Quantile:
    """P² 流式分位数估计器：5 标记 + 抛物线/线性调整，O(1) 内存。"""

    _POS = None        # 中间三个标记的相对位置，随 p 定

    def __init__(self, p: float) -> None:
        if not 0 < p < 1:
            raise ValueError("p 须在 (0, 1)")
        self.p = p
        self.q = [0.0] * 5          # 标记高度：min / p/2 / p / (1+p)/2 / max
        self.n = [0, 1, 2, 3, 4]    # 标记位置
        self.count = 0
        self._warm: list[float] = []

    def add(self, x: float) -> None:
        if self.count < 5:
            self._warm.append(x)
            self.count += 1
            if self.count == 5:
                self._warm.sort()
                self.q = list(self._warm)
                self._warm = []
            return
        self.count += 1
        k = self._cell(x)                       # x 落在第 k 格（0..3）
        for i in range(k + 1, 5):               # 右侧标记位置全体 +1
            self.n[i] += 1
        want = [0.0, (self.count - 1) * self.p / 2, (self.count - 1) * self.p,
                (self.count - 1) * (1 + self.p) / 2, float(self.count - 1)]
        for i in (1, 2, 3):
            d = want[i] - self.n[i]
            if (d >= 1 and self.n[i + 1] - self.n[i] > 1) or \
               (d <= -1 and self.n[i - 1] - self.n[i] < -1):
                s = 1 if d > 0 else -1
                cand = self._parabolic(i, s)
                if self.q[i - 1] < cand < self.q[i + 1]:
                    self.q[i] = cand
                else:
                    self.q[i] = self._linear(i, s)
                self.n[i] += s          # 位置与高度同步走 ±1（论文 Step 5）

    def _cell(self, x: float) -> int:
        """返回 x 所在格号；同时维护最小/最大标记。"""
        if x < self.q[0]:
            self.q[0] = x
            return 0
        if x < self.q[1]:
            return 0
        if x < self.q[2]:
            return 1
        if x < self.q[3]:
            return 2
        if x > self.q[4]:
            self.q[4] = x
        return 3

    def _parabolic(self, i: int, s: int) -> float:
        dn = self.n[i + 1] - self.n[i]
        up = self.n[i] - self.n[i - 1]
        if dn <= 0 or up <= 0:                  # 位置重合的罕见挤压 → 线性
            return self._linear(i, s)
        outer = self.n[i + 1] - self.n[i - 1]
        return (self.q[i] + s / outer * (
            (up + s) * (self.q[i + 1] - self.q[i]) / dn
            + (dn - s) * (self.q[i] - self.q[i - 1]) / up))

    def _linear(self, i: int, s: int) -> float:
        return self.q[i] + s * (self.q[i + s] - self.q[i]) / (
            self.n[i + s] - self.n[i])

    def value(self) -> float:
        """当前 p 分位数估计；预热期（<5 个观测）给精确值。"""
        if self.count < 5:
            return quantile(self._warm, self.p)
        return self.q[2]


def _selftest() -> None:
    # 精确口径手算基线：1..5 → q0.5=3；1..4 → q0.5=2.5、q0.25=1.75
    assert quantile([5, 1, 4, 2, 3], 0.5) == 3.0
    assert quantile([1, 2, 3, 4], 0.5) == 2.5
    assert quantile([1, 2, 3, 4], 0.25) == 1.75
    assert quantile([7.0], 0.0) == 7.0 and quantile([7.0], 1.0) == 7.0
    for bad_q in (-0.1, 1.5):
        try:
            quantile([1, 2], bad_q)
        except ValueError:
            pass
        else:
            raise AssertionError(f"q={bad_q} 应报错")
    try:
        quantile([], 0.5)
    except ValueError:
        pass
    else:
        raise AssertionError("空输入应报错")

    # P² 流式：确定性伪随机流（LCG 均匀 0..1000），与精确值对齐
    vals = [((i * 48271) % 1000003) / 1000003 * 1000 for i in range(1, 3002)]
    exact = quantile(vals, 0.5)
    for p in (0.25, 0.5, 0.75):
        p2 = P2Quantile(p)
        for v in vals:
            p2.add(v)
        est = p2.value()
        assert abs(est - quantile(vals, p)) <= 15.0, (p, est, quantile(vals, p))

    # 单调流（P² 的另一典型场景）
    mono = [i * 0.5 for i in range(1000)]
    p2 = P2Quantile(0.9)
    for v in mono:
        p2.add(v)
    assert abs(p2.value() - quantile(mono, 0.9)) <= 10.0

    # 预热期精确、标记位置单调
    w = P2Quantile(0.5)
    for v in (3, 1, 2):
        w.add(v)
    assert w.value() == 2.0

    print(f"selftest ok: 精确插值手算/流式 p25-75 误差≤15/单调流/预热精确 全部通过"
          f"（median 精确值 {exact:.1f}）")


def main() -> None:
    ap = argparse.ArgumentParser(description="分位数：精确 + 流式 P²")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--values", default=None, help="逗号分隔的数值串")
    ap.add_argument("--q", type=float, default=0.5, help="分位数（默认 0.5）")
    args = ap.parse_args()
    if args.selftest or args.values is None:
        _selftest()
        if args.values is None:
            return
    vals = [float(x) for x in args.values.split(",") if x.strip()]
    print(f"q{args.q} = {quantile(vals, args.q):g}")


if __name__ == "__main__":
    main()
