#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bloom_filter.py — 布隆过滤器：可误报、零漏报的集合成员判断。

海量集合的「见过没有」判断（爬虫 URL 去重、缓存穿透防护、黑名单粗筛）
不值得为此存全量数据——布隆过滤器用 m 个位 + k 个散列函数，内存只有
精确集合的几十分之一，代价是**可能误报**：说不存在的一定不存在，
说存在的可能不在。本实现用一次 md5 出 h1/h2、按 Kirsch-Mitzenmacher
生成 k 个位（(h1 + i·h2) mod m，步长取奇数避免短周期），并给出
容量/误报率的最优参数公式——建过滤器前先算预算，超容量误报率会失控。

用法：
    python tools/bloom_filter.py --selftest
    python tools/bloom_filter.py --items urls.txt --check candidates.txt

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import hashlib
import math

LN2 = math.log(2)


def optimal_params(n: int, p: float) -> tuple[int, int]:
    """期望装 n 个元素、误报率 p 下的最优位数 m 与散列数 k。

    m = ⌈-n·ln p / (ln2)²⌉，k = round((m/n)·ln2)——教科书公式，手算可验。
    """
    if n <= 0 or not 0 < p < 1:
        raise ValueError("需要 n>0 且 0<p<1")
    m = math.ceil(-n * math.log(p) / (LN2 * LN2))
    k = max(1, round(m / n * LN2))
    return m, k


def _positions(item: str, k: int, m: int) -> list[int]:
    """Kirsch-Mitzenmacher 双散列：一次 md5 出 h1/h2，k 个位坐标。"""
    d = hashlib.md5(item.encode("utf-8")).digest()
    h1 = int.from_bytes(d[:8], "big")
    h2 = int.from_bytes(d[8:], "big") | 1          # 奇数步长
    return [(h1 + i * h2) % m for i in range(k)]


class BloomFilter:
    """m 个位、k 个散列；add/查 membership；误报可控、绝不漏报。"""

    def __init__(self, m: int, k: int) -> None:
        if m <= 0 or k <= 0:
            raise ValueError("m/k 必须为正")
        self.m = m
        self.k = k
        self.bits = bytearray((m + 7) // 8)
        self.count = 0

    def _set(self, pos: int) -> None:
        self.bits[pos // 8] |= 1 << (pos % 8)

    def _get(self, pos: int) -> bool:
        return bool(self.bits[pos // 8] >> (pos % 8) & 1)

    def add(self, item: str) -> None:
        for pos in _positions(item, self.k, self.m):
            self._set(pos)
        self.count += 1

    def __contains__(self, item: str) -> bool:
        return all(self._get(pos) for pos in _positions(item, self.k, self.m))


def _selftest() -> None:
    # 参数公式：n=1000、p=1% → m=9586、k=7（手算：-1000·ln0.01/ln2²=9585.06）
    assert optimal_params(1000, 0.01) == (9586, 7)
    for bad in ((0, 0.01), (100, 0.0), (100, 1.0)):
        try:
            optimal_params(*bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad}")

    # 零漏报：加进去的一定查得到
    bf = BloomFilter(9586, 7)
    for x in ("a", "b", "中文URL", "https://example.com/x?q=1"):
        bf.add(x)
    assert all(x in bf for x in ("a", "b", "中文URL", "https://example.com/x?q=1"))

    # 空过滤器：什么都没加，几乎必然「不存在」
    assert "nope" not in BloomFilter(9586, 7)

    # 误报率实测：满载 1000 条后探 1000 条不存在的，应贴近 p=1% 量级
    m, k = optimal_params(1000, 0.01)
    bf2 = BloomFilter(m, k)
    for i in range(1000):
        bf2.add(f"item-{i}")
    fp = sum(f"probe-{i}" in bf2 for i in range(1000))
    assert fp < 30, f"误报 {fp}/1000 远超 p=1% 的合理波动"   # 期望 ~10
    assert "item-500" in bf2                                  # 漏报仍为零

    print(f"selftest ok: 参数公式/零漏报/空过滤器/实测误报 {fp}/1000≈{fp / 10:.1f}% "
          f"全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="布隆过滤器")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--items", default=None, help="成员清单文件（一行一条）")
    ap.add_argument("--check", default=None, help="待查文件（一行一条）")
    ap.add_argument("--p", type=float, default=0.01, help="目标误报率（默认 0.01）")
    args = ap.parse_args()
    if args.selftest or args.items is None:
        _selftest()
        if args.items is None:
            return
    with open(args.items, encoding="utf-8") as f:
        items = [ln.strip() for ln in f if ln.strip()]
    m, k = optimal_params(len(items) or 1, args.p)
    bf = BloomFilter(m, k)
    for x in items:
        bf.add(x)
    print(f"m={m} k={k}，位图内存 {m / 8192:.1f} KiB，已装 {bf.count} 条")
    if args.check:
        with open(args.check, encoding="utf-8") as f:
            for ln in f:
                x = ln.strip()
                if x:
                    print(f"{'❓可能存在' if x in bf else '✅一定不存在'}  {x}")


if __name__ == "__main__":
    main()
