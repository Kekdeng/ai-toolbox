#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sliding_window_counter.py — 滑动窗口限流：加权双窗口，平滑边界突发。

固定窗口计数器在窗口边界会放过 2× 突发：上一窗口尾 100 个 + 本窗口
头 100 个，任意 1 秒内实际 200 个。滑动窗口计数器（Cloudflare/nginx
limit_req 一族）用加权估计堵住这个缝：

    est = 上一窗口计数 × 窗口重叠比例 + 本窗口计数

只在内存里留两个计数器（O(1)），粒度是近似——要精确用滑动日志，
那要存时间戳队列。clock 可注入，测试离线确定性。

用法：
    python tools/sliding_window_counter.py --selftest
    python tools/sliding_window_counter.py --demo

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import time
from typing import Callable


class SlidingWindowCounter:
    """window 秒内最多 limit 个请求（加权滑动估计）。"""

    def __init__(self, limit: int, window: float = 1.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if limit <= 0 or window <= 0:
            raise ValueError("limit/window 必须为正")
        self.limit = limit
        self.window = float(window)
        self._clock = clock
        now = clock()
        self._curr_start = now
        self._prev = 0
        self._curr = 0

    def _roll(self, now: float) -> None:
        """推进固定窗口；跨过的完整旧窗口按滑动语义逐个交棒。"""
        while now - self._curr_start >= self.window:
            self._curr_start += self.window
            self._prev = self._curr
            self._curr = 0

    def _estimate(self, now: float) -> float:
        self._roll(now)
        overlap = self.window - (now - self._curr_start)
        return self._prev * (overlap / self.window) + self._curr

    def estimate(self) -> float:
        """当前时刻窗口内请求的加权估计值。"""
        return self._estimate(self._clock())

    def allow(self) -> bool:
        """本次请求是否放行；放行则计数 +1。"""
        now = self._clock()
        if self._estimate(now) + 1 <= self.limit:
            self._curr += 1
            return True
        return False


class _FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def time(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


def _selftest() -> None:
    c = _FakeClock()
    sw = SlidingWindowCounter(limit=10, window=1.0, clock=c.time)

    # 满窗口：恰好 10 个放行，第 11 个拒绝
    assert sum(sw.allow() for _ in range(11)) == 10
    assert sw.estimate() == 10.0

    # 边界突发被平滑：t=+1.5（下一窗口走了一半）
    #   est = 10 × 0.5 + 0 = 5 → 还能放 5 个（5+curr+1 ≤ 10），第 6 个拒绝
    c.advance(1.5)
    assert sw.estimate() == 5.0
    assert sum(sw.allow() for _ in range(6)) == 5
    assert sw.estimate() == 10.0

    # 新窗口交棒：t=+2.0 时上一窗口的 5 个以 100% 重叠起算
    #   est = 5 × 1.0 + 0 = 5 → 又能放 5 个，随后拒绝
    c.advance(0.5)
    assert sw.estimate() == 5.0
    assert sum(sw.allow() for _ in range(6)) == 5

    # 久置归零：跨 3 个完整窗口后历史计数全部过期
    c.advance(3.0)
    assert sw.estimate() == 0.0
    assert sum(sw.allow() for _ in range(11)) == 10

    # 参数校验
    for bad in ((0, 1.0), (5, 0.0)):
        try:
            SlidingWindowCounter(*bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad}")

    print("selftest ok: 满窗/边界平滑/交棒/久置归零/参数校验 全部通过")


def _demo() -> None:
    """真实时钟演示：limit=5、window=1s，瞬间打 20 发看放行节奏。"""
    sw = SlidingWindowCounter(limit=5, window=1.0)
    accepted = [sw.allow() for _ in range(20)]
    print(f"20 发瞬发放行 {sum(accepted)} 个（第 1 秒配额），"
          f"1 秒后恢复：{sum(sw.allow() for _ in range(3))}/3")


def main() -> None:
    ap = argparse.ArgumentParser(description="滑动窗口限流器")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--demo", action="store_true",
                    help="真实时钟小演示（约 1 秒）")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    if args.demo:
        _demo()
        return
    _selftest()


if __name__ == "__main__":
    main()
