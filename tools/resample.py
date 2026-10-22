#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resample.py — 时间序列桶聚合：乱序点 → 固定窗口的 sum/mean/min/max/count。

监控指标、行情 K 线、token 用量日报——本质都是「把乱序观测点按固定
窗口聚合」。本工具窗口取**左闭右开** [t, t+size)，支持 origin 对齐
起点（如从整点开始而不是从首条数据开始）；输入可乱序，内部按时间
排序后聚合，输出按窗口升序确定可复现。

用法：
    python tools/resample.py --selftest
    python tools/resample.py --points "[[0,1],[0.5,2],[1.2,3]]" --size 1 --agg sum

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import json
import math

_AGGS = ("sum", "mean", "min", "max", "count")


def bucket_start(ts: float, size: float, origin: float = 0.0) -> float:
    """ts 所在窗口的起点（左闭右开 [start, start+size)）。"""
    if size <= 0:
        raise ValueError("size 必须为正")
    return origin + math.floor((ts - origin) / size) * size


def resample(points: list[tuple[float, float]], size: float,
             agg: str = "mean", origin: float = 0.0
             ) -> list[tuple[float, float]]:
    """聚合点序列 → [(窗口起点, 聚合值)]；空输入 → 空。"""
    if agg not in _AGGS:
        raise ValueError(f"agg 须为 {'/'.join(_AGGS)}，收到 {agg!r}")
    buckets: dict[float, list[float]] = {}
    for ts, v in points:
        buckets.setdefault(bucket_start(ts, size, origin), []).append(v)
    out: list[tuple[float, float]] = []
    for start in sorted(buckets):
        vals = buckets[start]
        if agg == "sum":
            a = sum(vals)
        elif agg == "mean":
            a = sum(vals) / len(vals)
        elif agg == "min":
            a = min(vals)
        elif agg == "max":
            a = max(vals)
        else:
            a = len(vals)                       # count
        out.append((start, a))
    return out


def ohlc(points: list[tuple[float, float]], size: float,
         origin: float = 0.0) -> list[dict]:
    """K 线聚合：每窗 {start, open, high, low, close}（按 ts 排序取首尾）。"""
    ordered = sorted(points, key=lambda p: p[0])
    buckets: dict[float, list[float]] = {}
    for ts, v in ordered:
        buckets.setdefault(bucket_start(ts, size, origin), []).append(v)
    out: list[dict] = []
    for start in sorted(buckets):
        vals = buckets[start]
        out.append({"start": start, "open": vals[0], "high": max(vals),
                    "low": min(vals), "close": vals[-1]})
    return out


def _selftest() -> None:
    pts = [(0.0, 1.0), (0.5, 2.0), (1.0, 3.0), (1.5, 4.0), (2.4, 5.0)]

    # 左闭右开：ts=1.0 落在 [1,2) 而不是 [0,1)
    assert resample(pts, size=1.0, agg="sum") == [(0.0, 3.0), (1.0, 7.0),
                                                  (2.0, 5.0)]
    assert resample(pts, size=1.0, agg="mean") == [(0.0, 1.5), (1.0, 3.5),
                                                   (2.0, 5.0)]
    assert resample(pts, size=1.0, agg="max") == [(0.0, 2.0), (1.0, 4.0),
                                                  (2.0, 5.0)]
    assert resample(pts, size=1.0, agg="count") == [(0.0, 2), (1.0, 2),
                                                    (2.0, 1)]

    # origin 对齐：窗口从 0.5 切 → 0.4 与 0.6 分属两窗
    assert resample([(0.4, 10.0), (0.6, 20.0)], size=1.0,
                    origin=0.5) == [(-0.5, 10.0), (0.5, 20.0)]

    # 乱序输入结果一致（聚合内排序）；单点窗口 min=max=该值
    shuffled = [(1.5, 4.0), (0.0, 1.0), (2.4, 5.0), (1.0, 3.0), (0.5, 2.0)]
    assert resample(shuffled, size=1.0, agg="min") == \
        resample(pts, size=1.0, agg="min")

    # OHLC：开=首点、收=末点（按 ts 序），高低取极值
    k = ohlc([(0.0, 10.0), (0.7, 9.0), (0.5, 12.0), (1.0, 11.0)], size=1.0)
    assert k == [
        {"start": 0.0, "open": 10.0, "high": 12.0, "low": 9.0, "close": 9.0},
        {"start": 1.0, "open": 11.0, "high": 11.0, "low": 11.0, "close": 11.0},
    ], k

    # 空输入与坏参数
    assert resample([], size=1.0) == []
    assert ohlc([], size=1.0) == []
    try:
        resample(pts, size=1.0, agg="median")
    except ValueError:
        pass
    else:
        raise AssertionError("未知 agg 应报错")
    try:
        bucket_start(1.0, size=0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("size=0 应报错")

    print("selftest ok: 五种聚合/左闭右开/origin 对齐/乱序一致/OHLC/空与坏输入 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="时间序列桶聚合")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--points", default=None,
                    help='点序列 JSON，如 "[[0,1],[0.5,2],[1.2,3]]"')
    ap.add_argument("--size", type=float, default=1.0, help="窗口宽")
    ap.add_argument("--agg", default="mean",
                    help="sum/mean/min/max/count（默认 mean）")
    ap.add_argument("--origin", type=float, default=0.0, help="窗口对齐起点")
    args = ap.parse_args()
    if args.selftest or args.points is None:
        _selftest()
        if args.points is None:
            return
    pts = [(float(t), float(v)) for t, v in json.loads(args.points)]
    for start, val in resample(pts, args.size, args.agg, args.origin):
        print(f"[{start:g}, {start + args.size:g})  {val:g}")


if __name__ == "__main__":
    main()
