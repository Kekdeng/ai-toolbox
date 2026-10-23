#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""duration_fmt.py — 时长格式化与解析："1h2m3s" ↔ 3661.0。

超时配置、任务耗时、监控告警里的时长，两把刀：

- `format_duration(秒)`：紧凑风 `1d1h1m1s`（零单位跳过，0 → "0s"，
  亚秒保留小数 `59.5s`）；`style="clock"` 出 `HH:MM:SS`（小时不封顶，
  亚秒进到秒后 `.500`）；
- `parse_duration("1h 2m 3s")` → 3661.0：容空隙与小数，单位只认
  d/h/m/s 且**必须降序、各至多一次**——`2s1h`、`1h2h` 这类宁可
  报错也不猜；裸数字按秒。

解析全程 float 精度（0.1s 这种喂不进 int 的值照样往返）。

用法：
    python tools/duration_fmt.py --selftest
    python tools/duration_fmt.py --to 3661
    python tools/duration_fmt.py --from "1h1m1s"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re

_PAIR = re.compile(r"(\d+(?:\.\d+)?)([dhms])")
_BARE = re.compile(r"\d+(?:\.\d+)?")
_ORDER = "dhms"
_UNITS = {"d": 86400.0, "h": 3600.0, "m": 60.0, "s": 1.0}
_DESC = (("d", 86400.0), ("h", 3600.0), ("m", 60.0))


def format_duration(seconds: float, style: str = "compact") -> str:
    """秒 → "1h1m1s"（compact）或 "01:01:01"（clock）。"""
    if seconds < 0:
        raise ValueError(f"时长非负: {seconds}")
    if style not in ("compact", "clock"):
        raise ValueError(f"style 须 compact 或 clock: {style!r}")
    if style == "clock":
        h = int(seconds // 3600)
        m = int(seconds % 3600 // 60)
        s = seconds % 60
        sec = f"{int(s):02d}" if s == int(s) else f"{s:06.3f}"
        return f"{h:02d}:{m:02d}:{sec}"
    rem = float(seconds)
    parts = []
    for u, n in _DESC:
        v, rem = divmod(rem, n)
        if v >= 1:
            parts.append(f"{int(v)}{u}")
    if rem or not parts:
        parts.append(f"{rem:g}s")
    return "".join(parts)


def parse_duration(text: str) -> float:
    """"1h 2m 3s" / "1.5h" / "90" → 秒（float）。"""
    s = text.strip()
    if not s:
        raise ValueError("输入为空")
    if _BARE.fullmatch(s):
        return float(s)
    pairs = _PAIR.findall(s)
    if not pairs or "".join(n + u for n, u in pairs) != "".join(s.split()):
        raise ValueError(f"无法整段解析: {text!r}")
    total = 0.0
    last = -1
    for n, u in pairs:
        idx = _ORDER.index(u)
        if idx <= last:
            raise ValueError(f"单位须按 d>h>m>s 降序且各至多一次: {text!r}")
        last = idx
        total += float(n) * _UNITS[u]
    return total


def _selftest() -> None:
    # 紧凑风：零单位跳过、亚秒保留、0 兜底
    assert format_duration(3661) == "1h1m1s"
    assert format_duration(0) == "0s"
    assert format_duration(60) == "1m"
    assert format_duration(90) == "1m30s"
    assert format_duration(90061) == "1d1h1m1s"
    assert format_duration(59.5) == "59.5s"
    assert format_duration(0.5) == "0.5s"

    # clock 风：小时不封顶、亚秒进 .3f
    assert format_duration(3661, style="clock") == "01:01:01"
    assert format_duration(36610, style="clock") == "10:10:10"
    assert format_duration(100000, style="clock") == "27:46:40"
    assert format_duration(0.5, style="clock") == "00:00:00.500"

    # 解析：空隙/小数/裸数字
    assert parse_duration("1h1m1s") == 3661.0
    assert parse_duration("1h 2m 3s") == 3723.0
    assert parse_duration("1.5h") == 5400.0
    assert parse_duration("1.5m") == 90.0
    assert parse_duration("1m30s") == 90.0
    assert parse_duration("90") == 90.0
    assert parse_duration("2d") == 172800.0
    assert parse_duration("0s") == 0.0
    assert parse_duration("59.5s") == 59.5

    # 往返
    for sec in (3661, 90061, 5400, 90, 59.5, 0.5):
        assert parse_duration(format_duration(sec)) == float(sec), sec

    # 报错：空 / 无数字 / 坏单位 / 重复 / 乱序 / 负数 / 坏 style
    for bad in ("", "h", "1x", "1h2h", "2s1h", "-5s", "1h5", "1h m"):
        try:
            parse_duration(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 应报错")
    for bad_call in (lambda: format_duration(-1),
                     lambda: format_duration(1, style="iso")):
        try:
            bad_call()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    print("selftest ok: 紧凑/clock/亚秒/解析空隙/降序校验/往返/报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="时长格式化与解析")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--to", type=float, default=None, help="秒 → 人读形态")
    ap.add_argument("--from", dest="frm", default=None, help="人读形态 → 秒")
    ap.add_argument("--clock", action="store_true", help="format 用 HH:MM:SS")
    args = ap.parse_args()
    if args.selftest or (args.to is None and args.frm is None):
        _selftest()
        if args.to is None and args.frm is None:
            return
    if args.to is not None:
        print(format_duration(args.to, style="clock" if args.clock else "compact"))
    else:
        print(parse_duration(args.frm or ""))


if __name__ == "__main__":
    main()
