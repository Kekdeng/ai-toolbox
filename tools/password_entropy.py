#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""password_entropy.py — 密码强度/熵估算：字符集空间 + Shannon + 模式惩罚。

两种熵口径取小者（保守）：
- 字符集空间：len × log2(实际用到的字符池大小)——纯暴力破解视角；
- Shannon 熵：按字符频率算——衡量「实际信息量」，重复字符直接掉分。

再做模式惩罚：常见弱口令词、连号/键盘走位、同字符长串。
全程离线，密码不出本机（也请别拿真实主密码来跑，习惯问题）。

用法：
    python tools/password_entropy.py --selftest
    python tools/password_entropy.py --password "x7K#mQ2!vR9@"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import math
import re
import string

COMMON_WORDS = ("password", "passwd", "123456", "12345678", "qwerty",
                "admin", "letmein", "iloveyou", "woaini", "abc123",
                "111111", "000000", "666666", "888888")
_SEQUENCES = ("0123456789", "abcdefghijklmnopqrstuvwxyz",
              "qwertyuiop", "asdfghjkl", "zxcvbnm")


def charset_pool(pw: str) -> int:
    """实际用到的字符池大小（未用到的类别不计入）。"""
    pool = 0
    if any(c in string.ascii_lowercase for c in pw):
        pool += 26
    if any(c in string.ascii_uppercase for c in pw):
        pool += 26
    if any(c.isdigit() for c in pw):
        pool += 10
    if any(c in string.punctuation for c in pw):
        pool += len(string.punctuation)
    return pool or 1


def charset_bits(pw: str) -> float:
    """暴力破解视角：len × log2(池大小)。"""
    if not pw:
        return 0.0
    return len(pw) * math.log2(charset_pool(pw))


def shannon_bits(pw: str) -> float:
    """字符频率视角：每字符 Shannon 熵 × 长度；空串为 0。"""
    if not pw:
        return 0.0
    n = len(pw)
    total = 0.0
    for count in {c: pw.count(c) for c in set(pw)}.values():
        p = count / n
        total -= p * math.log2(p)
    return total * n


def _penalties(pw: str) -> list[tuple[str, float]]:
    """命中哪些弱模式及各自的乘法惩罚。"""
    out: list[tuple[str, float]] = []
    low = pw.lower()
    if any(w in low for w in COMMON_WORDS):
        out.append(("常见弱口令词", 0.4))
    if re.search(r"(.)\1{3,}", pw):
        out.append(("同字符长串", 0.6))
    if any(s[i:i + 4] in low for s in _SEQUENCES for i in range(len(s) - 3)):
        out.append(("连号/键盘走位", 0.7))
    return out


def score_password(pw: str) -> tuple[float, str, list[tuple[str, float]]]:
    """返回（惩罚后比特数, 强弱档位, 命中的惩罚）。

    档位：<28 弱 / <36 中 / <60 强 / 其余 极强。
    """
    bits = min(charset_bits(pw), shannon_bits(pw))
    penalties = _penalties(pw)
    for _name, factor in penalties:
        bits *= factor
    if bits < 28:
        verdict = "弱"
    elif bits < 36:
        verdict = "中"
    elif bits < 60:
        verdict = "强"
    else:
        verdict = "极强"
    return bits, verdict, penalties


def _selftest() -> None:
    # 字符集空间：Password123! 用满 4 类 → 12 × log2(94)
    assert abs(charset_bits("Password123!") - 12 * math.log2(94)) < 1e-9

    # Shannon：全同 0；aabb 每字符 1 bit × 4
    assert shannon_bits("aaaa") == 0.0
    assert abs(shannon_bits("aabb") - 4.0) < 1e-9

    # 弱口令词惩罚：原始 33 bit 级别 → 砍到 弱
    bits, verdict, pens = score_password("password1!")
    assert verdict == "弱" and ("常见弱口令词", 0.4) in pens, (bits, verdict, pens)

    # 高熵无模式 → 强
    bits2, verdict2, pens2 = score_password("x7K#mQ2!vR9@")
    assert verdict2 == "强" and not pens2, (bits2, verdict2, pens2)

    # 同字符长串：Shannon 直接归零，惩罚后仍为 0 → 弱
    bits3, verdict3, _ = score_password("aaaaaaaa")
    assert verdict3 == "弱" and bits3 == 0.0

    # 空串
    assert score_password("") == (0.0, "弱", [])

    print(f"selftest ok: password1!={bits:.1f}bit(弱) "
          f"随机样例={bits2:.1f}bit(强) 熵口径/惩罚/空串 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="密码强度/熵估算（离线）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--password", default=None, help="要评估的密码（不出本机）")
    args = ap.parse_args()
    if args.selftest or args.password is None:
        _selftest()
        if args.password is None:
            return
    bits, verdict, pens = score_password(args.password)
    print(f"{bits:.1f} bits  [{verdict}]")
    for name, factor in pens:
        print(f"  惩罚: {name} ×{factor}")


if __name__ == "__main__":
    main()
