#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lru_cache_ttl.py — LRU + TTL 缓存：容量驱逐 + 过期失效，双保险。

缓存 prompt→结果、工具调用结果时有两类失效要同时防：无限膨胀
（LRU 驱逐最久未用的）和陈旧数据（TTL 到期作废）。本工具用
OrderedDict 一把抓：尾部是最久未用，命中/set 即移到尾部；过期在
**读时惰性判定**、`prune` 可主动清扫。clock 可注入，自测零等待；
hit/miss/expiry/eviction 四个计数器让命中率成为指标而不是玄学。

用法：
    python tools/lru_cache_ttl.py --selftest

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import math
import time
from collections import OrderedDict
from typing import Callable


class LRUCacheTTL:
    """capacity 条上限；ttl 秒过期（None = 永不过期，只受 LRU 约束）。"""

    def __init__(self, capacity: int, ttl: float | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if capacity <= 0:
            raise ValueError("capacity 必须为正")
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl 必须为正或 None")
        self.capacity = capacity
        self.ttl = ttl
        self._clock = clock
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.expiries = 0
        self.evictions = 0

    def _expiry(self, now: float) -> float:
        return math.inf if self.ttl is None else now + self.ttl

    def set(self, key: str, value: object) -> None:
        """写入/覆盖；覆盖会刷新新鲜度（移到尾部 + 重置到期时间）。"""
        self._data[key] = (self._expiry(self._clock()), value)
        self._data.move_to_end(key)
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)          # 弹出最久未用
            self.evictions += 1

    def get(self, key: str, default: object = None) -> object:
        """命中返回值并移到尾部；过期按未命中处理并顺手清掉。"""
        if key not in self._data:
            self.misses += 1
            return default
        expires, value = self._data[key]
        if self._clock() >= expires:
            del self._data[key]
            self.expiries += 1
            self.misses += 1
            return default
        self._data.move_to_end(key)
        self.hits += 1
        return value

    def prune(self) -> int:
        """主动清掉所有已过期条目，返回清理数（适合定时任务兜底）。"""
        now = self._clock()
        dead = [k for k, (exp, _) in self._data.items() if now >= exp]
        for k in dead:
            del self._data[k]
            self.expiries += 1
        return len(dead)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: str) -> bool:
        """存在性判断：不含过期判定，仅反映存储（测试辅助）。"""
        return key in self._data


def _selftest() -> None:
    state = {"now": 100.0}

    def clock() -> float:
        return state["now"]

    # LRU 驱逐：容量 2，访问 a 后 b 变成最久未用 → set c 驱逐 b
    c = LRUCacheTTL(capacity=2, clock=clock)
    c.set("a", 1)
    c.set("b", 2)
    assert c.get("a") == 1                       # a 变新鲜
    c.set("c", 3)                                # 驱逐 b
    assert "b" not in c and "a" in c and "c" in c
    assert c.evictions == 1

    # 覆盖 = 刷新新鲜度：set a 后 b 才是被驱逐者
    c.set("a", 10)                               # 覆盖，a 仍在尾部之外最新
    c.set("d", 4)
    assert "c" not in c and "a" in c
    assert c.get("a") == 10                      # 值也被覆盖
    assert (c.hits, c.misses) == (2, 0)

    # TTL 过期：读时惰性判定，过期即按未命中并清条目
    t = LRUCacheTTL(capacity=8, ttl=10.0, clock=clock)
    t.set("x", "v")
    state["now"] += 9.9
    assert t.get("x") == "v"                     # 临期仍新鲜
    state["now"] += 0.1
    assert t.get("x") is None                    # 恰好到期判否
    assert t.misses == 1 and t.expiries == 1 and "x" not in t

    # prune：过期条目批量清，未过期的留着
    t.set("y", 1)
    t.set("z", 2)
    state["now"] += 5.0
    assert t.prune() == 0                        # y/z 都还没到期
    state["now"] += 5.0
    assert t.prune() == 2                        # 两个都到 10s 了
    assert len(t) == 0 and t.expiries == 3

    # ttl=None 永不过期，只受容量约束
    p = LRUCacheTTL(capacity=1, ttl=None, clock=clock)
    p.set("k", "v")
    state["now"] += 10_000.0
    assert p.get("k") == "v"

    # 参数校验
    for bad in ((0, None), (4, 0.0)):
        try:
            LRUCacheTTL(*bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad}")

    print("selftest ok: LRU 驱逐/覆盖刷新/TTL 惰性过期/prune/永不过期/参数 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="LRU + TTL 缓存")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.parse_args()
    _selftest()


if __name__ == "__main__":
    main()
