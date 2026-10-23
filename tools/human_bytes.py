#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""human_bytes.py — 字节数人性化与反向解析（1.5 GiB ↔ 1610612736）。

日志、配额、容量表到处都是字节数。两把刀：

- `format_bytes(n)`：挑最大的单位、去尾零——1610612736 → "1.5 GiB"；
  `style="decimal"` 走 SI 千进制（磁盘厂商标注口径）；
- `parse_bytes(s)`：反向，容大小写与空隙。三套单位约定**一次说清**：
  `KiB/MiB/GiB` 系 = IEC 1024；`KB/MB/GB` 系 = SI 1000；裸字母
  `K/M/G` = Unix 惯例 1024（`ls -lh` 口径）。解析给整数（四舍五入）。

往返只在所选精度可精确表示时无损（1.5 GiB 可逆；1.6 KiB 是舍入值）。

用法：
    python tools/human_bytes.py --selftest
    python tools/human_bytes.py --to 1610612736
    python tools/human_bytes.py --from "1.5 GiB"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re

_BIN = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
_DEC = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
_LETTERS = "KMGTPEZY"
_NUM = re.compile(r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z]*)\s*")


def _trim(s: str) -> str:
    """定点小数字符串去尾零与悬点："1.50" → "1.5"，"1.0" → "1"。"""
    return s.rstrip("0").rstrip(".") if "." in s else s


def format_bytes(n: int, style: str = "binary", precision: int = 1) -> str:
    """字节数 → "1.5 GiB" 形态；style=binary(1024) 或 decimal(1000)。"""
    if n < 0:
        raise ValueError(f"字节数非负: {n}")
    if style not in ("binary", "decimal"):
        raise ValueError(f"style 须 binary 或 decimal: {style!r}")
    base = 1024 if style == "binary" else 1000
    units = _BIN if style == "binary" else _DEC
    v = float(n)
    for i, u in enumerate(units):
        if v < base or i == len(units) - 1:
            return _trim(f"{v:.{precision}f}") + " " + u
        v /= base
    raise AssertionError("不可达")


def _factor(unit: str) -> int:
    """单位 → 字节倍数；三套约定见模块 docstring。"""
    u = unit.upper()
    if u in ("", "B"):
        return 1
    if len(u) == 1 and u in _LETTERS:                        # K = 1024
        return 1024 ** (_LETTERS.index(u) + 1)
    if len(u) == 2 and u[0] in _LETTERS and u[1] == "B":     # KB = 1000
        return 1000 ** (_LETTERS.index(u[0]) + 1)
    if len(u) == 3 and u[0] in _LETTERS and u[1:] == "IB":   # KiB = 1024
        return 1024 ** (_LETTERS.index(u[0]) + 1)
    raise ValueError(f"未知单位: {unit!r}")


def parse_bytes(text: str) -> int:
    """"1.5 GiB" / "1KB" / "1024" → 字节数（整数，四舍五入）。"""
    m = _NUM.fullmatch(text)
    if not m:
        raise ValueError(f"不是可解析的字节数: {text!r}")
    return round(float(m.group(1)) * _factor(m.group(2)))


def _selftest() -> None:
    # 二进制口径：逐级进位、尾零去除
    assert format_bytes(0) == "0 B"
    assert format_bytes(1) == "1 B"
    assert format_bytes(999) == "999 B"
    assert format_bytes(1024) == "1 KiB"
    assert format_bytes(1536) == "1.5 KiB"
    assert format_bytes(1610612736) == "1.5 GiB"
    assert format_bytes(1024 ** 8) == "1 YiB"
    assert format_bytes(1024 ** 9) == "1024 YiB"     # 顶格不再进位
    assert format_bytes(1664) == "1.6 KiB"           # 1.625 → 1 位小数

    # 十进制口径（SI）
    assert format_bytes(1000, style="decimal") == "1 KB"
    assert format_bytes(1500000, style="decimal") == "1.5 MB"
    assert format_bytes(999, style="decimal") == "999 B"

    # 解析：三套单位约定 + 大小写 + 空隙
    assert parse_bytes("1.5GiB") == 1610612736
    assert parse_bytes("1 KiB") == 1024
    assert parse_bytes("1kib") == 1024
    assert parse_bytes("1KB") == 1000
    assert parse_bytes("1kb") == 1000
    assert parse_bytes("1K") == 1024                 # Unix 裸字母
    assert parse_bytes("1k") == 1024
    assert parse_bytes("1024") == 1024               # 裸数字 = 字节
    assert parse_bytes("1 B") == 1
    assert parse_bytes("1.5KB") == 1500
    assert parse_bytes("  1.5 GiB ") == 1610612736
    assert parse_bytes("1YiB") == 1024 ** 8
    assert parse_bytes("1eb") == 1000 ** 6

    # 往返（所选精度可精确表示的值）
    for n in (0, 1, 1024, 1536, 1610612736, 1024 ** 8):
        assert parse_bytes(format_bytes(n)) == n, n

    # 报错：负数 / 坏 style / 无法解析 / 未知单位
    for bad_call in (lambda: format_bytes(-1),
                     lambda: format_bytes(1, style="si"),
                     lambda: parse_bytes(""),
                     lambda: parse_bytes("GiB"),
                     lambda: parse_bytes("-5"),
                     lambda: parse_bytes("1.5.5GB"),
                     lambda: parse_bytes("1QB"),
                     lambda: parse_bytes("1 GiBB")):
        try:
            bad_call()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    print("selftest ok: 二进制/十进制/三套单位解析/往返/顶格/报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="字节数人性化与解析")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--to", type=int, default=None, help="字节数 → 人读形态")
    ap.add_argument("--from", dest="frm", default=None, help="人读形态 → 字节数")
    ap.add_argument("--decimal", action="store_true", help="format 用 SI 千进制")
    args = ap.parse_args()
    if args.selftest or (args.to is None and args.frm is None):
        _selftest()
        if args.to is None and args.frm is None:
            return
    if args.to is not None:
        print(format_bytes(args.to,
                           style="decimal" if args.decimal else "binary"))
    else:
        print(parse_bytes(args.frm or ""))


if __name__ == "__main__":
    main()
