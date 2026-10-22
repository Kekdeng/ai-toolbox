#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""line_diff.py — 行级 diff：LCS 对齐 + 紧凑补丁 + apply 往返无损。

代码评审和配置变更审计的底层动作：两串行对齐，删的标 `-`、加的
标 `+`、共同的标空格前缀。标准 LCS 动态规划（O(n·m)，千行级够用），
同分时优先删——对齐确定可复现。

补丁即 diff 文本本身（前缀 + 行体，上下文行的前缀是空格）：空格
前缀天然消歧，行内容以 `-`/`+` 开头也不会串行。apply 逐消费原文，
`=`/`-` 行与原文不符即报错——补丁与文档不对账时宁可失败。

用法：
    python tools/line_diff.py --selftest
    python tools/line_diff.py --old-file a.txt --new-file b.txt
    python tools/line_diff.py --old-file a.txt --patch-file p.diff

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse


def diff_ops(a: list[str], b: list[str]) -> list[tuple[str, str]]:
    """LCS 对齐 → [("=", 行) | ("-", 行) | ("+", 行)]，确定可复现。"""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a[i] == b[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    ops: list[tuple[str, str]] = []
    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            ops.append(("=", a[i]))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:     # 同分优先删
            ops.append(("-", a[i]))
            i += 1
        else:
            ops.append(("+", b[j]))
            j += 1
    ops.extend(("-", x) for x in a[i:])
    ops.extend(("+", x) for x in b[j:])
    return ops


def apply(a: list[str], ops: list[tuple[str, str]]) -> list[str]:
    """补丁套到原文：=/- 逐行消费原文并与行体对账，不符即报错。"""
    out: list[str] = []
    ai = 0
    for tag, line in ops:
        if tag in ("=", "-"):
            if ai >= len(a) or a[ai] != line:
                raise ValueError(f"补丁与原文不符: 期待 {line!r}")
            if tag == "=":
                out.append(line)
            ai += 1
        else:
            out.append(line)
    if ai != len(a):
        raise ValueError("补丁未消费完原文")
    return out


def render(ops: list[tuple[str, str]]) -> str:
    """ops → 补丁文本：前缀 = 空格 / `-` / `+`。"""
    pfx = {"=": " ", "-": "-", "+": "+"}
    return "\n".join(pfx[t] + line for t, line in ops)


def parse_patch(text: str) -> list[tuple[str, str]]:
    """补丁文本 → ops；前缀非法报错（空上下文行 = 单个空格）。"""
    ops: list[tuple[str, str]] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw:
            raise ValueError(f"第 {lineno} 行是裸空行（空上下文应为单个空格）")
        tag = {" ": "="}.get(raw[0], raw[0])
        if tag not in ("=", "-", "+"):
            raise ValueError(f"第 {lineno} 行前缀非法: {raw!r}")
        ops.append((tag, raw[1:]))
    return ops


def line_diff(a: list[str], b: list[str]) -> str:
    """一步到位：diff 文本。"""
    return render(diff_ops(a, b))


def patch_text(a: list[str], patch: str) -> list[str]:
    """一步到位：补丁套原文。"""
    return apply(a, parse_patch(patch))


def _selftest() -> None:
    # 手算基线：LCS = x,y，同分一路优先删 → 先删完再加
    a = ["x", "a", "b", "y"]
    b = ["x", "A", "B", "y"]
    ops = diff_ops(a, b)
    assert ops == [("=", "x"), ("-", "a"), ("-", "b"),
                   ("+", "A"), ("+", "B"), ("=", "y")], ops
    pic = line_diff(a, b)
    assert pic.splitlines() == [" x", "-a", "-b", "+A", "+B", " y"]
    assert patch_text(a, pic) == b

    # 相同 / 纯删 / 纯增 / 追加 / 双空
    assert diff_ops(["p", "q"], ["p", "q"]) == [("=", "p"), ("=", "q")]
    assert apply(["p", "q"], diff_ops(["p", "q"], ["p", "q"])) == ["p", "q"]
    assert patch_text(["p", "q"], line_diff(["p", "q"], [])) == []
    assert patch_text([], line_diff([], ["n1", "n2"])) == ["n1", "n2"]
    assert patch_text(["a"], line_diff(["a"], ["a", "b"])) == ["a", "b"]
    assert line_diff([], []) == "" and patch_text([], "") == []

    # 消歧：以 -/+ 开头的行内容不串行；中文行往返
    a2 = ["-del-mark", "第一行", "+add-mark"]
    b2 = ["-del-mark", "改了", "+add-mark", "尾行"]
    assert patch_text(a2, line_diff(a2, b2)) == b2

    # 对账失败：删除行对不上 / 原文有剩余 / 前缀非法 / 裸空行
    for bad in (lambda: apply(["z"], [("-", "q")]),
                lambda: apply(["z"], [("=", "z"), ("=", "extra")]),
                lambda: parse_patch("no-prefix"),
                lambda: parse_patch(" x\n\n+ok")):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    print("selftest ok: 手算基线/往返/消歧/中文/对账失败/前缀非法 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="行级 diff 与补丁 apply")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--old-file", default=None, help="原文文件")
    ap.add_argument("--new-file", default=None, help="新文件（diff 模式）")
    ap.add_argument("--patch-file", default=None, help="补丁文件（apply 模式）")
    args = ap.parse_args()
    if args.selftest or args.old_file is None:
        _selftest()
        if args.old_file is None:
            return
    with open(args.old_file, encoding="utf-8") as f:
        old = f.read().splitlines()
    if args.new_file:
        with open(args.new_file, encoding="utf-8") as f:
            new = f.read().splitlines()
        print(line_diff(old, new))
        return
    if args.patch_file:
        with open(args.patch_file, encoding="utf-8") as f:
            print("\n".join(patch_text(old, f.read())))
        return
    _selftest()


if __name__ == "__main__":
    main()
