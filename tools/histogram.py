#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""histogram.py — 频数直方图：Freedman–Diaconis 定宽 + ASCII 渲染。

分布一眼看形状：定宽、数频、画条，三步全离线。

- 定宽：Freedman–Diaconis h = 2·IQR/n^(1/3)（IQR 抗离群值，n^(1/3)
  平衡样本量），bin 数 = ⌈极差/h⌉ 夹在 [1, 100]；IQR 退化（>25% 数据
  挤在同一点）回退 Sturges ⌈log2 n⌉+1；
- 计数约定：左闭右开 [e_i, e_{i+1})，末 bin 右闭吞掉最大值；
  全等数据 → 单 bin；
- render：每行「区间 + █ 条 + 频数」，峰值按 width 参数缩放，
  等频分布即满宽。

用法：
    python tools/histogram.py --selftest
    python tools/histogram.py --values "1,2,2,3,3,3,5,8" --bins 4
    python tools/histogram.py --values "..." --width 60

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import bisect
import math


def _pctl(s: list[float], q: float) -> float:
    """已排序列表的精确分位数（线性插值，h = (n-1)·q）。"""
    h = (len(s) - 1) * q
    lo = math.floor(h)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (h - lo) * (s[hi] - s[lo])


def histogram(values: list[float],
              bins: int | None = None) -> tuple[list[float], list[int]]:
    """频数直方图 → (edges, counts)；bins=None 用 FD 定宽。"""
    if not values:
        raise ValueError("values 为空")
    if bins is not None and bins < 1:
        raise ValueError("bins 须 ≥ 1")
    s = sorted(values)
    lo, hi = s[0], s[-1]
    if hi == lo:                              # 全等 → 单 bin
        return [lo, hi], [len(s)]
    if bins is None:
        iqr = _pctl(s, 0.75) - _pctl(s, 0.25)
        if iqr > 0:                           # Freedman–Diaconis
            h = 2 * iqr / len(s) ** (1 / 3)
            bins = min(100, max(1, math.ceil((hi - lo) / h)))
        else:                                 # 退化 → Sturges
            bins = min(100, math.ceil(math.log2(len(s))) + 1)
    width = (hi - lo) / bins
    edges = [lo + width * k for k in range(bins)] + [hi]
    counts = [0] * bins
    for v in s:
        k = bisect.bisect_right(edges, v) - 1
        counts[min(k, bins - 1)] += 1         # v=hi 落末 bin（右闭）
    return edges, counts


def render(edges: list[float], counts: list[int], width: int = 40) -> str:
    """直方图 → ASCII：区间 + █ 条（峰值 = width）+ 频数。"""
    peak = max(counts)
    last = len(counts) - 1
    lines = []
    for i, c in enumerate(counts):
        close = "]" if i == last else ")"
        bar = "█" * (round(c / peak * width) if c else 0)
        lines.append(f"[{edges[i]:g}, {edges[i + 1]:g}{close} {bar} {c}")
    return "\n".join(lines)


def _selftest() -> None:
    # 手算基线：0..9 分 5 bin（宽 1.8），计数均匀
    edges, counts = histogram(list(range(10)), bins=5)
    assert len(edges) == 6 and edges[0] == 0.0 and edges[-1] == 9.0
    assert counts == [2, 2, 2, 2, 2], counts

    # 边界归属：恰在边上归右 bin，最大值被末 bin 右闭吞掉
    _, counts = histogram([0, 2, 4], bins=2)
    assert counts == [1, 2], counts           # 2 落 [2, 4]

    # FD 规则手算：0..99 → IQR=49.5，h=99/100^(1/3)≈21.33 → 5 bins
    edges, counts = histogram(list(range(100)))
    assert len(counts) == 5, len(counts)
    assert sum(counts) == 100

    # Sturges 回退：IQR=0（0×9 + 100）→ ⌈log2 10⌉+1 = 5
    _, counts = histogram([0] * 9 + [100])
    assert len(counts) == 5, len(counts)

    # 全等 / 单点 → 单 bin
    _, counts = histogram([5, 5, 5])
    assert counts == [3], counts
    edges, counts = histogram([7.0])
    assert counts == [1] and edges == [7.0, 7.0], (edges, counts)

    # 空输入 / bins 非法 → 报错
    for bad in (lambda: histogram([]), lambda: histogram([1], 0)):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    # 渲染：区间标签、█ 条、末 bin 右闭、等频 → 满宽
    edges, counts = histogram(list(range(10)), bins=5)
    pic = render(edges, counts, width=40)
    assert pic.splitlines()[0].startswith("[0, 1.8)")
    assert pic.splitlines()[-1].startswith("[7.2, 9]")
    assert "█" in pic
    bars = [ln.count("█") for ln in pic.splitlines()]
    assert bars == [40, 40, 40, 40, 40], bars

    print("selftest ok: 手算基线/边界归属/FD/Sturges/单bin/报错/渲染 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="频数直方图（FD 定宽 + ASCII）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--values", default=None, help="逗号分隔的数值串")
    ap.add_argument("--bins", type=int, default=None,
                    help="bin 数（默认 Freedman–Diaconis 自动）")
    ap.add_argument("--width", type=int, default=40,
                    help="ASCII 条最大宽度（默认 40）")
    args = ap.parse_args()
    if args.selftest or args.values is None:
        _selftest()
        if args.values is None:
            return
    vals = [float(x) for x in args.values.split(",") if x.strip()]
    edges, counts = histogram(vals, args.bins)
    print(render(edges, counts, args.width))


if __name__ == "__main__":
    main()
