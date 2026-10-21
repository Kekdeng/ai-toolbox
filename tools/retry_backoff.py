#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""retry_backoff.py — 调 LLM API 的重试/指数退避封装（纯标准库，可离线测试）。

429/超时/瞬时 5xx 是调用外部 API 的家常便饭：retry() 提供「指数退避 +
可选抖动 + 异常类型过滤」的最小封装。sleep 与随机源都可注入——测试不真等、
不真随机，延迟序列可以直接断言。

用法：
    python tools/retry_backoff.py --selftest
    （接入真实 API 时：retry(lambda: client.chat(...), attempts=5)）

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import random
import time
from collections.abc import Callable


def compute_delays(attempts: int, base_delay: float, max_delay: float,
                   jitter: bool = False, rng: random.Random | None = None,
                   ) -> list[float]:
    """重试间隔序列（attempts-1 个）：base×2^i 封顶 max；jitter 乘 U(0.5,1)。"""
    if attempts < 1:
        raise ValueError("attempts 必须 ≥ 1")
    out: list[float] = []
    for i in range(attempts - 1):
        d = min(max_delay, base_delay * 2 ** i)
        if jitter:
            d *= (rng or random.Random()).uniform(0.5, 1.0)
        out.append(d)
    return out


def retry(fn: Callable[[], object], attempts: int = 4,
          base_delay: float = 0.1, max_delay: float = 2.0,
          jitter: bool = False, rng: random.Random | None = None,
          sleep: Callable[[float], None] = time.sleep,
          retry_on: tuple[type[BaseException], ...] = (Exception,),
          on_retry: Callable[[int, BaseException], None] | None = None,
          ) -> object:
    """执行 fn()，失败按退避序列重试；耗尽后抛出最后一次异常。

    retry_on 之外的异常**不重试**、直接抛出。
    """
    if attempts < 1:
        raise ValueError("attempts 必须 ≥ 1")
    delays = iter(compute_delays(attempts, base_delay, max_delay,
                                 jitter, rng))
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except retry_on as exc:
            if attempt >= attempts:
                raise
            if on_retry is not None:
                on_retry(attempt, exc)
            sleep(next(delays))
    raise AssertionError("unreachable")   # 上面 raise 已覆盖，占位给类型检查


def _selftest() -> None:
    # 两次失败后成功：调用 3 次，退避 [0.5, 1.0]
    sleeps: list[float] = []
    state = {"n": 0}

    def flaky() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    assert retry(flaky, attempts=5, base_delay=0.5,
                 sleep=sleeps.append) == "ok"
    assert state["n"] == 3 and sleeps == [0.5, 1.0]

    # 永远失败：耗尽后抛原始异常；封顶生效
    sleeps2: list[float] = []

    def bad() -> None:
        raise ValueError("x")

    try:
        retry(bad, attempts=4, base_delay=1.0, max_delay=2.0,
              sleep=sleeps2.append)
    except ValueError:
        pass
    else:
        raise AssertionError("耗尽后应抛原异常")
    assert sleeps2 == [1.0, 2.0, 2.0]

    # retry_on 之外不重试：1 次调用、0 次睡眠
    state3 = {"n": 0}

    def wrong() -> None:
        state3["n"] += 1
        raise ValueError("不该重试")

    try:
        retry(wrong, attempts=5, retry_on=(KeyError,), sleep=sleeps.append)
    except ValueError:
        pass
    else:
        raise AssertionError("非 retry_on 异常应直接抛出")
    assert state3["n"] == 1 and len(sleeps) == 2

    # on_retry 回调与延迟序列（纯函数）
    seen: list[int] = []
    try:
        retry(bad, attempts=3, base_delay=0.0, max_delay=0.0,
              sleep=lambda _d: None, on_retry=lambda a, _e: seen.append(a))
    except ValueError:
        pass
    else:
        raise AssertionError("耗尽后应抛出")
    assert seen == [1, 2]
    assert compute_delays(5, 1.0, 2.0) == [1.0, 2.0, 2.0, 2.0]
    assert compute_delays(4, 0.1, 10.0) == [0.1, 0.2, 0.4]

    # jitter 有界：全部落在 [0.5d, d]
    rng = random.Random(42)
    js = compute_delays(4, 1.0, 100.0, jitter=True, rng=rng)
    assert all(0.5 * d <= v <= d for d, v in zip([1.0, 2.0, 4.0], js)), js

    for bad_call in (lambda: retry(bad, attempts=0),
                     lambda: compute_delays(0, 1.0, 2.0)):
        try:
            bad_call()
        except ValueError:
            continue
        raise AssertionError("attempts<1 应抛 ValueError")

    print("selftest ok: 成功重试/耗尽抛错/类型过滤/回调/延迟序列/jitter 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="重试/指数退避演示")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--demo", action="store_true",
                    help="真实演示：前两次失败第三次成功（真睡 0.2/0.4s）")
    args = ap.parse_args()
    if args.selftest or not args.demo:
        _selftest()
        if not args.demo:
            return
    state = {"n": 0}

    def demo() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("模拟瞬时故障")
        return "成功"

    print(retry(demo, attempts=5, base_delay=0.2))


if __name__ == "__main__":
    main()
