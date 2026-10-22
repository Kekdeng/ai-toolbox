#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""leaky_bucket.py — 漏桶限流：恒定流出速率，把突发整形成平滑流。

限流三兄弟的分工：token_bucket 管「平均速率」、突发放行；
sliding_window_counter 管「统计平滑」、堵边界毛刺；leaky_bucket 管
「输出整形」——请求进桶、桶以恒定速率漏出、满了就拒，下游看到的
是严格均匀的流量。适合限连接数的第三方 API、消费能力固定的队列。

clock/sleep 可注入，测试离线零等待（假时钟随 sleep 前进，见自测）。

用法：
    python tools/leaky_bucket.py --selftest
    python tools/leaky_bucket.py --demo

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import time
from typing import Callable


class LeakyBucket:
    """rate：每秒漏出请求数；capacity：桶深（可积压的上限）。"""

    def __init__(self, rate: float, capacity: float,
                 clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate/capacity 必须为正")
        self.rate = float(rate)
        self.capacity = float(capacity)
        self._water = 0.0                       # 桶内水量（懒结算）
        self._last = clock()
        self._clock = clock
        self._sleep = sleeper

    def _leak(self, now: float) -> None:
        self._water = max(0.0, self._water - (now - self._last) * self.rate)
        self._last = now

    @property
    def level(self) -> float:
        """当前水位——读取时先按流逝时间漏账（懒结算的观测口）。"""
        self._leak(self._clock())
        return self._water

    def try_acquire(self) -> bool:
        """立刻进桶；桶满则拒绝（不等待、不入队）。"""
        now = self._clock()
        self._leak(now)
        if self._water + 1 <= self.capacity:
            self._water += 1
            return True
        return False

    def acquire(self) -> float:
        """进桶，桶满就等水位漏到能容纳；返回实际等待秒数。"""
        self._leak(self._clock())
        waited = 0.0
        if self._water + 1 > self.capacity:
            waited = (self._water + 1 - self.capacity) / self.rate
            self._sleep(waited)
            self._leak(self._clock())
        self._water += 1
        return waited


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.naps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, t: float) -> None:
        self.naps.append(t)
        self.now += t


def _selftest() -> None:
    c = _FakeClock()
    b = LeakyBucket(rate=2, capacity=5, clock=c.time, sleeper=c.sleep)

    # 桶深 5：连进 5 个，第 6 个被拒
    assert [b.try_acquire() for _ in range(5)] == [True] * 5
    assert b.try_acquire() is False
    assert b.level == 5.0

    # 恒速漏出（水位懒结算，进桶/查询时才漏账）：
    #   0.25s 只漏 0.5，还差一点；拒绝前账已漏 → 水位 4.5
    c.now += 0.25
    assert b.try_acquire() is False
    assert abs(b.level - 4.5) < 1e-9
    c.now += 0.25
    assert b.try_acquire() is True
    assert b.level == 5.0

    # acquire 等待：满桶要等 0.5s（漏 1 个的时长），等待后水位恰好回满
    c.now += 0.0
    w = b.acquire()
    assert abs(w - 0.5) < 1e-9 and c.naps == [0.5], (w, c.naps)
    assert b.level == 5.0

    # 久置漏空：3 秒漏 6 个，水位触底为 0（不为负）
    c.now += 3.0
    assert b.level == 0.0
    assert sum(b.try_acquire() for _ in range(6)) == 5

    # 参数校验
    for bad in ((0, 5), (2, 0)):
        try:
            LeakyBucket(*bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad}")

    print("selftest ok: 桶深拒入/恒速漏出/acquire 等待/漏空触底/参数校验 全部通过")


def _demo() -> None:
    """真实时钟演示：rate=2/s、桶深 3，10 发瞬发看下游看到的节奏。"""
    b = LeakyBucket(rate=2, capacity=3)
    t0 = time.monotonic()
    ok = 0
    for _ in range(10):
        b.acquire()
        ok += 1
        print(f"第 {ok} 个放行，距开始 {time.monotonic() - t0:.2f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description="漏桶限流器（恒定流出整形）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--demo", action="store_true",
                    help="真实时钟小演示（10 发约 3.5 秒）")
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
