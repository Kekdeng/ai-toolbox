#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""token_bucket.py — 令牌桶限流：突发友好，clock/sleep 可注入（离线可测）。

调外部 API（LLM、行情、短信…）的限流层：桶里攒令牌、每请求取一个，
空了就等——攒的过程天然允许突发（capacity 决定上限），平均速率由
rate 锁死。与 retry_backoff 是一对：一个管「别打太快」，一个管
「被打挂了怎么办」。clock/sleep 可注入，测试全程离线零真实等待。

用法：
    python tools/token_bucket.py --selftest
    python tools/token_bucket.py --demo

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import time
from typing import Callable


class TokenBucket:
    """rate：每秒补充令牌数；capacity：桶容量（突发上限）。

    初始满桶。注入的 sleeper 负责真实等待；测试里让假时钟随
    sleep 前进即可复现真实时间流（见 _selftest 的 FakeClock）。
    """

    def __init__(self, rate: float, capacity: float,
                 clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate/capacity 必须为正")
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self._last = clock()
        self._clock = clock
        self._sleep = sleeper

    def _refill(self) -> None:
        now = self._clock()
        self.tokens = min(self.capacity,
                          self.tokens + (now - self._last) * self.rate)
        self._last = now

    @property
    def available(self) -> float:
        """当前可用令牌数（会先按流逝时间补充）。"""
        self._refill()
        return self.tokens

    def try_acquire(self, n: float = 1) -> bool:
        """立刻取 n 个；不够则不动桶（不等待、不透支、不排队）。"""
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def acquire(self, n: float = 1) -> float:
        """取 n 个，不够就睡到够；返回实际等待的秒数。"""
        if n > self.capacity:
            raise ValueError(f"n={n} 超过桶容量 {self.capacity}，永远等不到")
        self._refill()
        waited = 0.0
        if self.tokens < n:
            waited = (n - self.tokens) / self.rate
            self._sleep(waited)
            self._refill()
        self.tokens -= n
        return waited


class _FakeClock:
    """测试用假时钟：sleep 会真实推进时钟，复现时间流。"""

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
    b = TokenBucket(rate=2, capacity=3, clock=c.time, sleeper=c.sleep)

    # 满桶突发：连取 3 个成功，第 4 个立刻失败且不消耗
    assert [b.try_acquire() for _ in range(3)] == [True, True, True]
    assert b.try_acquire() is False
    assert b.available == 0.0

    # 1 秒回 2 个令牌：够 2 个、不够 3 个
    c.now += 1.0
    assert b.available == 2.0
    assert b.try_acquire(2) is True
    assert b.try_acquire(1) is False

    # 空桶 acquire：睡 1/rate = 0.5s 后成功，桶恰好取空
    w = b.acquire(1)
    assert abs(w - 0.5) < 1e-9 and c.naps == [0.5], (w, c.naps)
    assert b.available == 0.0

    # 部分令牌时 acquire：现有 1 个取 2 个 → 只补差价 0.5s
    c.now += 0.5                      # 攒回 1 个
    w2 = b.acquire(2)
    assert abs(w2 - 0.5) < 1e-9 and c.naps[-1] == 0.5
    assert b.available == 0.0

    # 超容量永远等不到 → 构造时就拒绝
    try:
        b.acquire(4)
    except ValueError:
        pass
    else:
        raise AssertionError("n > capacity 应报错")

    # 上限封顶：闲置 10 秒也只有 capacity 个，不会无限攒
    c.now += 10.0
    assert b.available == 3.0

    print("selftest ok: 突发/回补/acquire 等待/超容量拒绝/封顶 全部通过")


def _demo() -> None:
    """真实时钟演示：rate=2/s、容量 3，连发 5 个请求只多等 ~1s。"""
    b = TokenBucket(rate=2, capacity=3)
    t0 = time.monotonic()
    for i in range(5):
        waited = b.acquire()
        print(f"请求 {i + 1}: 等待 {waited:.2f}s"
              f"（距开始 {time.monotonic() - t0:.2f}s）")


def main() -> None:
    ap = argparse.ArgumentParser(description="令牌桶限流器")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--demo", action="store_true",
                    help="真实时钟小演示（约 1.5 秒）")
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
