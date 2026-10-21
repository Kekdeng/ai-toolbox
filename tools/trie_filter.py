#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trie_filter.py — Trie 敏感词/关键词过滤：最长匹配、逐位置贪心（纯标准库）。

内容审核、关键词打标的最朴素高效做法：把词表建成 Trie，文本从每个位置
向右探最长匹配，命中即整体遮罩。复杂度 O(文本长 × 最长词长)，词表量级
到数万仍然够用；需要大规模流式场景再升级 Aho-Corasick。

注意：默认大小写敏感（英文词请自行先 lower）；无后缀跳转，极端重叠词表
不影响正确性（最长匹配优先）。

用法：
    python tools/trie_filter.py --selftest
    python tools/trie_filter.py --words "敏感词,坏词" --text "含敏感词的话"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse


class WordFilter:
    """词表 Trie；命中替换为等长遮罩，返回（遮罩文本, 命中词列表）。"""

    def __init__(self, words: list[str]) -> None:
        self.root: dict = {}
        for w in words:
            if not w:
                continue
            node = self.root
            for ch in w:
                node = node.setdefault(ch, {})
            node["$"] = True          # 词尾标记（值 True，非 dict）

    def scan_at(self, text: str, i: int) -> int:
        """从位置 i 出发的最长匹配长度（无匹配返回 0）。"""
        node = self.root
        best = 0
        for j in range(i, len(text)):
            node = node.get(text[j])
            if not isinstance(node, dict):   # 词尾标记 True 会在此被挡住
                break
            if node.get("$") is True:
                best = j - i + 1
        return best

    def apply(self, text: str, mask_ch: str = "*",
              ) -> tuple[str, list[str]]:
        hits: list[str] = []
        out: list[str] = []
        i = 0
        while i < len(text):
            n = self.scan_at(text, i)
            if n:
                hits.append(text[i:i + n])
                out.append(mask_ch * n)
                i += n
            else:
                out.append(text[i])
                i += 1
        return "".join(out), hits


def _selftest() -> None:
    # 最长匹配：同一位置「敏感」和「敏感词」都命中时取长者
    f = WordFilter(["敏感词", "敏感", "坏词"])
    masked, hits = f.apply("这是敏感词和坏词")
    assert masked == "这是***和**", masked
    assert hits == ["敏感词", "坏词"], hits

    # 重叠词表：ab 与 abc，取 abc
    f2 = WordFilter(["ab", "abc"])
    masked2, _ = f2.apply("xabc")
    assert masked2 == "x***", masked2

    # 命中后跳过整段：剩余位置的 "ab" 独立命中
    masked3, hits3 = f2.apply("abcab")
    assert masked3 == "*****" and hits3 == ["abc", "ab"], (masked3, hits3)

    # 自定义遮罩字符；空词表原样返回；不含词的文本不变
    assert WordFilter(["敏感"]).apply("敏感", mask_ch="#")[0] == "##"
    assert WordFilter([]).apply("原样") == ("原样", [])
    assert f.apply("正常文本") == ("正常文本", [])

    print("selftest ok: 最长匹配/重叠/跳段/空表/正常文本 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="Trie 敏感词过滤")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--words", default=None, help="词表，逗号分隔")
    ap.add_argument("--text", default=None, help="待过滤文本")
    ap.add_argument("--mask", default="*", help="遮罩字符（默认 *）")
    args = ap.parse_args()
    if args.selftest or not args.words or args.text is None:
        _selftest()
        if not args.words or args.text is None:
            return
    words = [w.strip() for w in args.words.split(",") if w.strip()]
    masked, hits = WordFilter(words).apply(args.text, args.mask)
    print(masked)
    print(f"--- 命中 {len(hits)} 处: {hits}")


if __name__ == "__main__":
    main()
