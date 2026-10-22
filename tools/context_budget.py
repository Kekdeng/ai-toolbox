#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""context_budget.py — Prompt 预算装填：按优先级塞块、可截断降级、用量审计。

上下文窗口和计费都是硬预算：检索召回的 8 个片段 + few-shot + 历史对话
不可能全塞进去。本工具按「优先级从小到大」装填文本块：整块装得下就装；
装不下时可选尾部截断（二分找最长可行前缀，与估算器严格对齐）；截断有
最小长度下限——半句话的召回没有意义，宁可整块丢弃。最终给出
placed / truncated / skipped 与用量报告，预算决策显式可审计，
而不是「超了就让模型自己看着办」。

Token 估算是内联启发式（与 token_estimator 同口径，单文件自包含）：
CJK 字符 ≈1 token/字，其余 ≈4 字符/token，每块另计 OVERHEAD 定界开销。

用法：
    python tools/context_budget.py --selftest
    python tools/context_budget.py --budget 500 --block "系统提示" --block "召回片段"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import math
import unicodedata

OVERHEAD = 4  # 每块的定界/角色开销（估算口径）


def count_chars(s: str) -> tuple[int, int]:
    """（CJK 字符数, 其他字符数）；宽判定用 east_asian_width（W/F）。"""
    cjk = other = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            cjk += 1
        else:
            other += 1
    return cjk, other


def estimate_tokens(s: str) -> int:
    """启发式 token 估算：CJK 1:1、其余 4:1；空串为 0。"""
    cjk, other = count_chars(s)
    return cjk + math.ceil(other / 4)


def _fit_prefix(text: str, token_room: int) -> str:
    """能塞进 token_room 的最长前缀（对 estimate_tokens 精确，二分）。"""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_tokens(text[:mid]) <= token_room:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo]


def fit(blocks: list[dict], budget: int, allow_truncate: bool = True,
        min_truncate_chars: int = 8) -> dict:
    """按优先级升序（稳定，平局保持输入序）装填文本块。

    块字段：id / text / priority（缺省 0，数字越小越先装）。
    返回 {"placed", "truncated", "skipped", "used", "remaining"}：
    - placed：原块 + tokens；
    - truncated：text 已替换为保留前缀，附 dropped_chars；
    - skipped：附 reason（预算已满 / 截断不足下限）。
    """
    order = sorted(range(len(blocks)),
                   key=lambda i: (blocks[i].get("priority", 0), i))
    used = 0
    placed: list[dict] = []
    truncated: list[dict] = []
    skipped: list[dict] = []
    for i in order:
        b = blocks[i]
        text = b.get("text", "")
        cost = estimate_tokens(text) + OVERHEAD
        if used + cost <= budget:
            used += cost
            placed.append({**b, "tokens": cost})
            continue
        room = budget - used - OVERHEAD
        prefix = _fit_prefix(text, room) if allow_truncate and room >= 1 else ""
        if len(prefix) >= min_truncate_chars:
            pcost = estimate_tokens(prefix) + OVERHEAD
            used += pcost
            truncated.append({**b, "text": prefix, "tokens": pcost,
                              "dropped_chars": len(text) - len(prefix)})
            continue
        skipped.append({**b, "reason": "预算已满" if room < 1
                        else f"截断不足 {min_truncate_chars} 字符下限"})
    return {"placed": placed, "truncated": truncated, "skipped": skipped,
            "used": used, "remaining": budget - used}


def _selftest() -> None:
    # 估算基线：CJK 1:1、ASCII 4:1
    assert estimate_tokens("") == 0
    assert estimate_tokens("一二三") == 3
    assert estimate_tokens("abcdefghij") == 3            # ceil(10/4)
    assert estimate_tokens("hi中") == 2                   # 1 + ceil(2/4)

    b1 = {"id": "sys", "text": "一二三四五六", "priority": 0}   # 6+4=10
    b2 = {"id": "few", "text": "abcdefghij", "priority": 1}    # 3+4=7

    # 恰好装满
    r = fit([b1, b2], budget=17)
    assert [e["id"] for e in r["placed"]] == ["sys", "few"]
    assert (r["used"], r["remaining"]) == (17, 0)
    assert not r["truncated"] and not r["skipped"]

    # 优先级胜出：预算只够一块时低优先级整块出局
    r = fit([b1, b2], budget=10)
    assert [e["id"] for e in r["placed"]] == ["sys"]
    assert [e["id"] for e in r["skipped"]] == ["few"]

    # 截断降级：46 字 CJK 前缀塞满预算，超出计入 dropped_chars
    r = fit([{"id": "doc", "text": "一" * 100, "priority": 0}], budget=50)
    assert len(r["truncated"]) == 1
    t = r["truncated"][0]
    assert t["text"] == "一" * 46 and t["dropped_chars"] == 54, t
    assert (r["used"], r["remaining"]) == (50, 0)

    # 截断下限：前缀不足下限时宁可整块丢弃；放宽下限则截断生效
    short = {"id": "t", "text": "一二三", "priority": 0}
    r = fit([short], budget=6)
    assert [e["id"] for e in r["skipped"]] == ["t"] and r["used"] == 0
    r = fit([short], budget=6, min_truncate_chars=2)
    assert r["truncated"][0]["text"] == "一二" and r["remaining"] == 0

    # 同优先级保持输入顺序；连开销都放不下的预算全数丢弃
    r = fit([{"id": "a", "text": "一二三", "priority": 0},
             {"id": "b", "text": "四五六", "priority": 0}], budget=7)
    assert [e["id"] for e in r["placed"]] == ["a"]
    assert [e["id"] for e in r["skipped"]] == ["b"]
    assert fit([b1], budget=OVERHEAD)["skipped"][0]["reason"] == "预算已满"

    print("selftest ok: 估算基线/恰好装满/优先级/截断与下限/稳定顺序 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="Prompt 预算装填")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--budget", type=int, default=None, help="token 预算")
    ap.add_argument("--block", action="append", default=None,
                    help="文本块（可多次给出，优先级 = 给出顺序）")
    ap.add_argument("--no-truncate", action="store_true",
                    help="关闭尾部截断（装不下整块丢弃）")
    ap.add_argument("--min-chars", type=int, default=8,
                    help="截断保留的最小字符数（默认 8）")
    args = ap.parse_args()
    if args.selftest or args.budget is None or not args.block:
        _selftest()
        if args.budget is None or not args.block:
            return
    blocks = [{"id": str(i), "text": t, "priority": i}
              for i, t in enumerate(args.block)]
    r = fit(blocks, args.budget, allow_truncate=not args.no_truncate,
            min_truncate_chars=args.min_chars)
    for e in r["placed"]:
        print(f"✅ 放行 #{e['id']}  {e['tokens']} tokens")
    for e in r["truncated"]:
        print(f"✂️  截断 #{e['id']}  {e['tokens']} tokens"
              f"（丢弃 {e['dropped_chars']} 字符）")
    for e in r["skipped"]:
        print(f"🚫 丢弃 #{e['id']}（{e['reason']}）")
    print(f"用量: {r['used']}/{args.budget}，余 {r['remaining']}")


if __name__ == "__main__":
    main()
