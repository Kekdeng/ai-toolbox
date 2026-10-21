#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pii_masker.py — 把文本中的常见 PII 替换成占位符（发给 LLM API 前的粗筛）。

正则近似识别，覆盖国内场景最高频的五类：手机号 / 身份证 / 邮箱 / 银行卡 / IP。
身份证不做校验码验证、不做姓名/地址识别——这是「粗筛」不是合规级脱敏，
误报漏报都可能，高风险场景请叠加人工审核或专业工具。

用法：
    python tools/pii_masker.py --selftest
    python tools/pii_masker.py --text "联系 13812345678" --only 手机号,邮箱

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re
from collections import Counter

# 顺序即执行顺序：身份证（18 位）必须在银行卡（16-19 位）之前，避免被吞
PATTERNS: list[tuple[str, str]] = [
    ("身份证",
     r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])"
     r"(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"),
    ("手机号", r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    ("邮箱", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("银行卡", r"(?<!\d)\d{16,19}(?!\d)"),
    ("IP", r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"),
]


def mask(text: str, categories: set[str] | None = None,
         ) -> tuple[str, list[tuple[str, str]]]:
    """脱敏；返回 (替换后文本, [(类别, 原文), …] 按出现顺序)。"""
    findings: list[tuple[str, str]] = []

    def _sub(m: re.Match[str], name: str = "") -> str:
        findings.append((name, m.group(0)))
        return f"[{name}]"

    for name, pat in PATTERNS:
        if categories and name not in categories:
            continue
        text = re.sub(pat, lambda m, name=name: _sub(m, name), text)
    return text, findings


def _selftest() -> None:
    # 混合文本：手机号 / 邮箱 / 身份证各就各位
    masked, found = mask("联系 13812345678 或 zhang.san@example.com，"
                         "身份证 11010119900307777X")
    assert masked == ("联系 [手机号] 或 [邮箱]，身份证 [身份证]"), masked
    assert {f[0] for f in found} == {"手机号", "邮箱", "身份证"}

    # 19 位卡号 → 银行卡（不被身份证/手机号吞掉）
    masked2, found2 = mask("卡号 6222020200112233456 转账")
    assert masked2 == "卡号 [银行卡] 转账", masked2
    assert found2 == [("银行卡", "6222020200112233456")]

    # 12 位编号不误伤（既非手机也非卡号）
    masked3, found3 = mask("编号 123456789012 保留")
    assert masked3 == "编号 123456789012 保留" and not found3

    # 日期不误伤
    masked4, found4 = mask("出生日期 1990-03-07")
    assert masked4 == "出生日期 1990-03-07" and not found4

    # IP
    masked5, _ = mask("来源 10.0.0.1 日志")
    assert masked5 == "来源 [IP] 日志"

    # 分类过滤：只脱敏手机号
    masked6, found6 = mask("13812345678 a@b.com", categories={"手机号"})
    assert masked6 == "[手机号] a@b.com" and len(found6) == 1

    print(f"selftest ok: {len(found)} 项命中、3 类边界不误伤、分类过滤生效")


def main() -> None:
    ap = argparse.ArgumentParser(description="中文 PII 脱敏（正则粗筛）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--text", default=None, help="要脱敏的文本")
    ap.add_argument("--file", default=None, help="要脱敏的文本文件路径")
    ap.add_argument("--only", default=None,
                    help="只处理这些类别，逗号分隔（如 手机号,邮箱）")
    args = ap.parse_args()
    if args.selftest or (not args.text and not args.file):
        _selftest()
        if not args.text and not args.file:
            return

    cats = set(args.only.split(",")) if args.only else None
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text or ""
    masked, found = mask(text, cats)
    print(masked)
    if found:
        summary = ", ".join(f"{name}×{n}"
                            for name, n in Counter(name for name, _ in found)
                            .items())
        print(f"--- 已脱敏: {summary}")


if __name__ == "__main__":
    main()
