#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cron_next.py — cron 表达式解析与下一次执行时间（5 字段，纯标准库）。

Agent 定时任务、报表调度里 cron 无处不在，但验证「这条表达式到底什么
时候跑」往往只能靠线上试。本工具做最小完整的 cron 语义：

- 五字段：分(0-59) 时(0-23) 日(1-31) 月(1-12) 星期(0-6, 0=周日)；
- 每字段支持 `*`、单值、列表（a,b）、区间（a-b）、步进（`*/n`、a-b/n）；
- 星期 7 按 Sunday 惯例归一为 0；
- 日 与 星期 同时受限（都不是 `*`）时按 Vixie cron 经典语义取**或**——
  「13 号或每周五」是有效且常见的表达。

搜索是朴素逐分钟前进（合法表达式一天内必命中，实现短、可读性优先），
一年内无匹配（如 2 月 30 日）显式报错。

用法：
    python tools/cron_next.py --selftest
    python tools/cron_next.py --expr "30 9 * * 1-5" --count 3

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta

_MAX_SCAN_MINUTES = 366 * 24 * 60       # 闰年一年，覆盖「明年今天」场景


def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    """解析一个字段 → 命中值集合；越界/空集/坏语法报 ValueError。"""
    out: set[int] = set()
    for part in field.split(","):
        rng, step = part, 1
        if "/" in part:
            rng, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(f"步进须为正: {part!r}")
        if rng == "*":
            start, end = lo, hi
        elif "-" in rng:
            a, b = rng.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = int(rng)
            end = hi if "/" in part else start   # Vixie: "5/15" = 5,20,35,50
        if not (lo <= start <= hi and lo <= end <= hi) or start > end:
            raise ValueError(f"越界或区间反了: {part!r}（合法 {lo}-{hi}）")
        out.update(range(start, end + 1, step))
    if not out:
        raise ValueError(f"字段没有命中任何值: {field!r}")
    return out


def parse_cron(expr: str) -> dict:
    """解析 5 字段表达式；返回各字段命中集 + 日/星期是否受限的标记。"""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron 需要 5 个字段: 分 时 日 月 星期")
    dows = _parse_field(parts[4], 0, 7)
    if 7 in dows:                       # Sunday 惯例：7 与 0 等价
        dows |= {0}
        dows.discard(7)
    return {
        "minute": _parse_field(parts[0], 0, 59),
        "hour": _parse_field(parts[1], 0, 23),
        "dom": _parse_field(parts[2], 1, 31),
        "month": _parse_field(parts[3], 1, 12),
        "dow": dows,
        "dom_star": parts[2] == "*",
        "dow_star": parts[4] == "*",
    }


def matches(cron: dict, dt: datetime) -> bool:
    """某时刻（分钟精度）是否命中。"""
    if (dt.minute not in cron["minute"] or dt.hour not in cron["hour"]
            or dt.month not in cron["month"]):
        return False
    dom_ok = dt.day in cron["dom"]
    dow_ok = ((dt.weekday() + 1) % 7) in cron["dow"]    # Mon=0 → cron 1
    if cron["dom_star"] and cron["dow_star"]:
        return True
    if cron["dom_star"]:
        return dow_ok
    if cron["dow_star"]:
        return dom_ok
    return dom_ok or dow_ok             # Vixie 经典：日与星期同限取或


def next_run(expr: str, after: datetime) -> datetime:
    """严格晚于 after 的下一个执行时刻（秒/微秒被抹平到分钟精度）。"""
    cron = parse_cron(expr)
    t = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(_MAX_SCAN_MINUTES):
        if matches(cron, t):
            return t
        t += timedelta(minutes=1)
    raise ValueError(f"一年内无匹配（检查日/月组合是否永假）: {expr!r}")


def _selftest() -> None:
    # 每天 09:30：周四 10:00 之后 → 周五 09:30；恰在执行时刻 → 顺延一天
    assert next_run("30 9 * * *", datetime(2026, 10, 22, 10, 0)) == \
        datetime(2026, 10, 23, 9, 30)
    assert next_run("30 9 * * *", datetime(2026, 10, 22, 9, 30)) == \
        datetime(2026, 10, 23, 9, 30)

    # 步进：10:07 之后，每 15 分钟 → 10:15
    assert next_run("*/15 * * * *", datetime(2026, 10, 22, 10, 7)) == \
        datetime(2026, 10, 22, 10, 15)

    # 工作日 09:00：周五 12:00 之后跳过周末 → 下周一
    assert next_run("0 9 * * 1-5", datetime(2026, 10, 23, 12, 0)) == \
        datetime(2026, 10, 26, 9, 0)

    # Vixie 或语义：「13 号或每周五」→ 周四之后最近的命中的是周五
    assert next_run("0 0 13 * 5", datetime(2026, 10, 22, 0, 0)) == \
        datetime(2026, 10, 23, 0, 0)

    # 区间小时 + 纯日字段：09:30 之后 → 当天 10:00；月初 → 11 月 1 日
    assert next_run("0 8-10 * * *", datetime(2026, 10, 22, 9, 30)) == \
        datetime(2026, 10, 22, 10, 0)
    assert next_run("0 0 1 * *", datetime(2026, 10, 22, 0, 0)) == \
        datetime(2026, 11, 1, 0, 0)

    # 星期 7 = 周日：周四之后 → 10 月 25 日（周日）
    assert next_run("0 0 * * 7", datetime(2026, 10, 22, 0, 0)) == \
        datetime(2026, 10, 25, 0, 0)

    # 2 月 29 日：2027 年底回看，下一个闰年在扫描窗口内
    assert next_run("0 0 29 2 *", datetime(2027, 12, 31, 12, 0)) == \
        datetime(2028, 2, 29, 0, 0)

    # 步进与 Vixie 起点："*/10" 从 0 起；"30/10" = 30,40,50
    assert next_run("*/10 * * * *", datetime(2026, 10, 22, 10, 5)) == \
        datetime(2026, 10, 22, 10, 10)
    assert next_run("30/10 * * * *", datetime(2026, 10, 22, 10, 5)) == \
        datetime(2026, 10, 22, 10, 30)

    # 坏表达式显式报错
    for bad in ("61 * * * *", "* * * *", "*/0 * * * *", "0 0 32 * *",
                "* * * * 8-9"):
        try:
            parse_cron(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad!r}")

    print("selftest ok: 日/步进/周末跳过/或语义/7=周日/闰日/Vixie 起点/坏表达式 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="cron 下一次执行时间")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--expr", default=None, help="5 字段 cron 表达式")
    ap.add_argument("--after", default=None,
                    help="起始时刻 YYYY-MM-DD[ HH:MM[:SS]]（默认现在）")
    ap.add_argument("--count", type=int, default=1, help="连看几次（默认 1）")
    args = ap.parse_args()
    if args.selftest or args.expr is None:
        _selftest()
        if args.expr is None:
            return
    if args.after is None:
        base = datetime.now().replace(second=0, microsecond=0)
    elif len(args.after) == 10:
        base = datetime.strptime(args.after, "%Y-%m-%d")
    elif len(args.after) == 16:
        base = datetime.strptime(args.after, "%Y-%m-%d %H:%M")
    else:
        base = datetime.strptime(args.after, "%Y-%m-%d %H:%M:%S")
    t = base
    for _ in range(max(1, args.count)):
        t = next_run(args.expr, t)
        print(t.strftime("%Y-%m-%d %H:%M (%a)"))


if __name__ == "__main__":
    main()
