#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""date_range.py — 日期区间：解析 / 迭代 / 分块 / 交集（含首尾）。

回测窗口、报表周期、调度跨度的公共底座。区间一律**闭区间**
[start, end]，length 按含首尾天数计：

- parse_range："2026-01-01..2026-01-31" → (date, date)，start>end
  报错；分隔符可配；
- iter_days / iter_months：逐日；逐月给覆盖到的 (年, 月) 列表；
- chunk：按 n 天切块，末块截断——调度按批拉数的标准动作；
- overlap：交集闭区间，不相交给 None；
- 闰年正确性靠 datetime.date 本身（2024-02-29 存在），自测锁定。

用法：
    python tools/date_range.py --selftest
    python tools/date_range.py --range 2026-01-01..2026-01-07 --chunk 3

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

_DAY = timedelta(days=1)
_FMT = "%Y-%m-%d"


def parse_range(s: str, sep: str = "..") -> tuple[date, date]:
    """'YYYY-MM-DD<sep>YYYY-MM-DD' → (start, end)；次序颠倒报错。"""
    left, _, right = s.partition(sep)
    if not _:
        raise ValueError(f"缺分隔符 {sep!r}: {s!r}")
    start, end = date.fromisoformat(left), date.fromisoformat(right)
    if start > end:
        raise ValueError(f"start 晚于 end: {s!r}")
    return start, end


def length(r: tuple[date, date]) -> int:
    """含首尾的天数。"""
    return (r[1] - r[0]).days + 1


def iter_days(r: tuple[date, date]):
    """逐日迭代（含首尾）。"""
    cur = r[0]
    while cur <= r[1]:
        yield cur
        cur += _DAY


def iter_months(r: tuple[date, date]) -> list[tuple[int, int]]:
    """覆盖到的月份 → [(年, 月)]，升序去重。"""
    out: list[tuple[int, int]] = []
    cur = date(r[0].year, r[0].month, 1)
    while cur <= r[1]:
        out.append((cur.year, cur.month))
        cur = (cur + timedelta(days=32)).replace(day=1)
    return out


def chunk(r: tuple[date, date], days: int) -> list[tuple[date, date]]:
    """按 days 天切块（闭区间），末块截断；days 须 ≥ 1。"""
    if days < 1:
        raise ValueError("days 须 ≥ 1")
    out: list[tuple[date, date]] = []
    cur = r[0]
    while cur <= r[1]:
        nxt = min(cur + timedelta(days=days - 1), r[1])
        out.append((cur, nxt))
        cur = nxt + _DAY
    return out


def overlap(a: tuple[date, date],
            b: tuple[date, date]) -> tuple[date, date] | None:
    """交集闭区间；不相交 → None。"""
    start, end = max(a[0], b[0]), min(a[1], b[1])
    return (start, end) if start <= end else None


def _selftest() -> None:
    r = parse_range("2026-01-01..2026-01-31")

    # 解析与长度：含首尾
    assert r == (date(2026, 1, 1), date(2026, 1, 31))
    assert length(r) == 31
    assert length((date(2026, 1, 1), date(2026, 1, 1))) == 1   # 单日

    # 闰年：2024-02-29 存在，2026 平年 28 天
    assert length(parse_range("2024-02-01..2024-02-29")) == 29
    assert length(parse_range("2026-02-01..2026-02-28")) == 28

    # 逐日：数量与首尾一致
    days = list(iter_days(r))
    assert len(days) == 31 and days[0] == r[0] and days[-1] == r[1]

    # 逐月：跨年跨月覆盖
    assert iter_months(parse_range("2026-01-20..2026-03-10")) == \
        [(2026, 1), (2026, 2), (2026, 3)]
    assert iter_months(parse_range("2025-12-15..2026-01-05")) == \
        [(2025, 12), (2026, 1)]

    # 分块：31 天按 7 切 → 5 块，末块 3 天
    ks = chunk(r, 7)
    assert len(ks) == 5 and ks[0] == (date(2026, 1, 1), date(2026, 1, 7))
    assert ks[-1] == (date(2026, 1, 29), date(2026, 1, 31))
    assert sum(length(k) for k in ks) == 31                   # 无缝无叠
    for a, b in zip(ks, ks[1:]):                              # 相邻衔接
        assert (a[1] + _DAY) == b[0]
    assert chunk(r, 31) == [r] and chunk(r, 100) == [r]       # 一块容纳

    # 交集：部分相交 / 包含 / 不相交
    a = parse_range("2026-01-10..2026-01-20")
    assert overlap(a, parse_range("2026-01-15..2026-02-05")) == \
        (date(2026, 1, 15), date(2026, 1, 20))
    assert overlap(a, r) == a                                 # 包含
    assert overlap(a, parse_range("2026-02-01..2026-02-28")) is None
    assert overlap(a, parse_range("2026-01-20..2026-01-25")) == \
        (date(2026, 1, 20), date(2026, 1, 20))                # 单日相触

    # 报错：缺分隔符 / 次序颠倒 / days<1
    for bad in (lambda: parse_range("2026-01-01"),
                lambda: parse_range("2026-01-31..2026-01-01"),
                lambda: chunk(r, 0)):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    print("selftest ok: 解析/含首尾/闰年/逐月跨年/分块衔接/交集/报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="日期区间工具（闭区间）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--range", default=None, help="YYYY-MM-DD..YYYY-MM-DD")
    ap.add_argument("--chunk", type=int, default=None, help="按 n 天分块")
    args = ap.parse_args()
    if args.selftest or args.range is None:
        _selftest()
        if args.range is None:
            return
    r = parse_range(args.range)
    if args.chunk:
        for a, b in chunk(r, args.chunk):
            print(f"{a.isoformat()}..{b.isoformat()}  ({length((a, b))} 天)")
        return
    print(f"长度 {length(r)} 天  覆盖月份 {iter_months(r)}")


if __name__ == "__main__":
    main()
