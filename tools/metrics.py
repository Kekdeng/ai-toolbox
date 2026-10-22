#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""metrics.py — 进程内指标：计数器 / 仪表 / 时间窗速率（clock 可注入）。

限流器管「能不能过」，这里管「过去了多少」：轻量观测三件套——

- 计数器 inc：单调累计（调用量、错误数），count 给全期总量；
- 仪表 gauge：随时可覆盖的瞬时值（水位、队列深度），未设过给 None；
- 速率 rate(name, window)：滑动窗口内事件量 / 窗口秒数，读时顺带
  裁剪更早事件（内存不随时间膨胀；裁剪只对 ≤ 当前 window 的查询严格）。

clock 注入（() -> float），固定假钟全确定可测；单线程设计，无锁。

用法：
    python tools/metrics.py --selftest
    python tools/metrics.py --demo

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import time
from collections import deque


class Metrics:
    """计数器 + 仪表 + 滑动窗口速率，进程内单线程使用。"""

    def __init__(self, clock=None) -> None:
        self._clock = clock or time.time
        self._counters: dict[str, int] = {}
        self._events: dict[str, deque] = {}
        self._gauges: dict[str, float] = {}

    def inc(self, name: str, n: int = 1) -> None:
        """计数器 +n（n 须 > 0）。"""
        if n <= 0:
            raise ValueError("n 须 > 0")
        self._counters[name] = self._counters.get(name, 0) + n
        self._events.setdefault(name, deque()).append((self._clock(), n))

    def set_gauge(self, name: str, value: float) -> None:
        """仪表设值（覆盖式）。"""
        self._gauges[name] = value

    def count(self, name: str) -> int:
        """计数器全期总量；未见过 → 0。"""
        return self._counters.get(name, 0)

    def gauge(self, name: str) -> float | None:
        """仪表当前值；未设过 → None。"""
        return self._gauges.get(name)

    def rate(self, name: str, window: float) -> float:
        """(now-window, now] 内事件量 / window；顺带裁剪更早事件。"""
        if window <= 0:
            raise ValueError("window 须 > 0")
        cutoff = self._clock() - window
        dq = self._events.get(name)
        if dq is None:
            return 0.0
        while dq and dq[0][0] <= cutoff:
            dq.popleft()
        return sum(n for _, n in dq) / window

    def snapshot(self) -> dict:
        """全量快照（键排序），rate 之类窗口值不含。"""
        return {"counters": dict(sorted(self._counters.items())),
                "gauges": dict(sorted(self._gauges.items()))}


def _selftest() -> None:
    t = [0.0]
    m = Metrics(clock=lambda: t[0])

    # 计数器：累计、未知名给 0
    m.inc("qps")
    m.inc("qps", 2)
    t[0] = 6.0
    m.inc("qps")
    t[0] = 7.0
    m.inc("qps", 2)
    t[0] = 8.0
    m.inc("qps")
    assert m.count("qps") == 7 and m.count("nope") == 0

    # 速率手算：now=10，窗口 (5,10] 含 t=6/7/8 共 4 → 0.8/s
    # （窗口从大到小查：读时裁剪会清走更早事件，见下）
    t[0] = 10.0
    assert abs(m.rate("qps", 5) - 0.8) < 1e-12
    # 窗口 (7,10]：只剩 t=8 的 1 → 1/3
    assert abs(m.rate("qps", 3) - 1 / 3) < 1e-12
    # 窗口 (8,10]：t=8 恰在边界被排除 → 0；此读清走全部事件
    assert m.rate("qps", 2) == 0.0
    # 裁剪生效：事件已清空，放大窗口也是 0
    assert m.rate("qps", 100) == 0.0

    # 仪表：覆盖式取值，未设过给 None
    assert m.gauge("mem") is None
    m.set_gauge("mem", 0.7)
    m.set_gauge("mem", 0.9)
    assert m.gauge("mem") == 0.9

    # 快照：键排序、两舱分立
    m.set_gauge("a", 1)
    m.inc("z")
    assert m.snapshot() == {"counters": {"qps": 7, "z": 1},
                            "gauges": {"a": 1, "mem": 0.9}}

    # 报错：n≤0 / window≤0
    for bad in (lambda: m.inc("x", 0), lambda: m.rate("qps", 0)):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    print("selftest ok: 计数累计/速率手算/边界排除/裁剪/仪表/快照/报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="进程内指标（计数/仪表/速率）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--demo", action="store_true",
                    help="假钟跑一段脚本并打印快照")
    args = ap.parse_args()
    if args.selftest or not args.demo:
        _selftest()
        if not args.demo:
            return
    t = [0.0]
    m = Metrics(clock=lambda: t[0])
    for i in range(10):
        t[0] = i
        m.inc("req")
        if i % 3 == 0:
            m.inc("err")
    m.set_gauge("queue", 3)
    t[0] = 9.9
    print(f"rate(req, 5s) = {m.rate('req', 5):.1f}/s  "
          f"rate(err, 5s) = {m.rate('err', 5):.2f}/s")
    print(m.snapshot())


if __name__ == "__main__":
    main()
