#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""text_chunker.py — RAG 预处理：把长文本切成适合嵌入/检索的小块（纯标准库）。

两种切法：
- chunk_fixed     固定窗口 + 重叠（stride 滑动），适合无结构的原始长文本；
- chunk_recursive 递归分隔符切分（段落 → 换行 → 句号 → … → 单字符），块边界
  尽量落在自然分隔处，且「拼接所有块 == 原文」（无损，可还原）。

用法：
    python tools/text_chunker.py --selftest
    python tools/text_chunker.py --file some.txt --size 200 --mode recursive

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse

DEFAULT_SEPARATORS = ("\n\n", "\n", "。", "！", "？", "；", "，", "")


def chunk_fixed(text: str, size: int, overlap: int = 0) -> list[str]:
    """固定窗口滑动切块；overlap 为相邻块重叠字符数（0 ≤ overlap < size）。"""
    if size < 1:
        raise ValueError("size 必须 ≥ 1")
    if not 0 <= overlap < size:
        raise ValueError("overlap 必须满足 0 ≤ overlap < size")
    if not text:
        return []
    stride = size - overlap
    chunks: list[str] = []
    for i in range(0, len(text), stride):
        if i > 0 and i + overlap >= len(text):
            break        # 尾块完全落在上一块的重叠里，丢弃
        chunks.append(text[i:i + size])
    return chunks


def split_keep_sep(text: str, sep: str) -> list[str]:
    """按 sep 切分并把分隔符保留在前一段尾部；sep 为空串时按单字符切。"""
    if sep == "":
        return list(text)
    parts = text.split(sep)
    return [p + sep for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def chunk_recursive(text: str, size: int,
                    separators: tuple[str, ...] = DEFAULT_SEPARATORS,
                    ) -> list[str]:
    """递归分隔符切块：先按最高级分隔符合并，超长段再用下一级分隔符递归。

    保证：所有块 ≤ size（size ≥ 1 时），且 "".join(块) == 原文。
    """
    if size < 1:
        raise ValueError("size 必须 ≥ 1")
    if not text:
        return []
    sep, rest = separators[0], separators[1:]
    chunks: list[str] = []
    buf = ""
    for piece in split_keep_sep(text, sep):
        if len(piece) > size and rest:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(chunk_recursive(piece, size, rest))
        elif len(buf) + len(piece) > size and buf:
            chunks.append(buf)
            buf = piece
        else:
            buf += piece
    if buf:
        chunks.append(buf)
    return chunks


def _selftest() -> None:
    # chunk_fixed：重叠与去尾块
    assert chunk_fixed("0123456789", 4, 1) == ["0123", "3456", "6789"]
    assert chunk_fixed("0123456789", 4, 0) == ["0123", "4567", "89"]
    fixed = chunk_fixed("0123456789", 4, 1)
    assert fixed[0][-1] == fixed[1][0] == "3"        # 重叠字符衔接
    assert chunk_fixed("", 5) == []

    # chunk_recursive：全部 ≤ size 且无损（拼接 == 原文）
    text = "# 标题\n\n第一段。第二段！\n\n第三段，带逗号；结束" * 3
    chunks = chunk_recursive(text, 20)
    assert chunks
    assert all(len(c) <= 20 for c in chunks), [len(c) for c in chunks]
    assert "".join(chunks) == text

    # 空输入与参数校验
    assert chunk_recursive("", 5) == []
    for bad in (lambda: chunk_fixed("abc", 0),
                lambda: chunk_fixed("abc", 2, 2),
                lambda: chunk_fixed("abc", 2, -1),
                lambda: chunk_recursive("abc", 0)):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError(bad)

    print(f"selftest ok: recursive {len(chunks)} 块全部 ≤20 字符且拼接无损")


def main() -> None:
    ap = argparse.ArgumentParser(description="RAG 文本切块")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--file", default=None, help="要切块的文本文件路径")
    ap.add_argument("--text", default=None, help="要切块的文本（与 --file 二选一）")
    ap.add_argument("--size", type=int, default=200, help="块最大字符数")
    ap.add_argument("--overlap", type=int, default=0, help="fixed 模式重叠字符数")
    ap.add_argument("--mode", choices=("fixed", "recursive"), default="recursive")
    args = ap.parse_args()
    if args.selftest or (not args.file and args.text is None):
        _selftest()
        if not args.file and args.text is None:
            return

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text or ""
    if args.mode == "fixed":
        chunks = chunk_fixed(text, args.size, args.overlap)
    else:
        chunks = chunk_recursive(text, args.size)
    print(f"共 {len(chunks)} 块（size={args.size}, mode={args.mode}）")
    for i, c in enumerate(chunks[:3]):
        print(f"  [{i}] {c[:50]!r}{'…' if len(c) > 50 else ''}")


if __name__ == "__main__":
    main()
