#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bpe_tokenizer.py — 最小字节级 BPE 分词器（训练/编码/解码，纯标准库）。

BPE（Byte Pair Encoding）是 GPT 系分词器的核心算法：从字节序列出发，反复把
语料中最高频的相邻字节对合并成新 token，直到达到目标合并次数。推理（编码）
时按训练时合并的先后顺序贪心应用同一张合并表。

用法：
    python tools/bpe_tokenizer.py --selftest                  # 内置自测
    python tools/bpe_tokenizer.py --train-corpus "重复语料"    # 训练并看压缩率

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
from collections import Counter


def _count_pairs(ids: list[int]) -> Counter:
    """统计相邻 token 对出现次数。"""
    return Counter(zip(ids, ids[1:]))


def _merge(ids: list[int], pair: tuple[int, int], new_id: int) -> list[int]:
    """把 ids 中所有出现的 pair 替换为 new_id（一次贪心扫描，不重叠配对）。"""
    out: list[int] = []
    i = 0
    while i < len(ids):
        if i + 1 < len(ids) and (ids[i], ids[i + 1]) == pair:
            out.append(new_id)
            i += 2
        else:
            out.append(ids[i])
            i += 1
    return out


class BPETokenizer:
    """字节级 BPE：没有显式词表文件——合并表 (a, b) -> new_id 即词表。"""

    def __init__(self) -> None:
        self.merges: dict[tuple[int, int], int] = {}

    def train(self, text: str, num_merges: int) -> None:
        """训练 num_merges 次合并；频次并列取字典序更大的对，保证结果确定。"""
        ids = list(text.encode("utf-8"))
        self.merges = {}
        for step in range(num_merges):
            pairs = _count_pairs(ids)
            if not pairs:
                break
            pair, _n = max(pairs.items(), key=lambda kv: (kv[1], kv[0]))
            ids = _merge(ids, pair, 256 + step)
            self.merges[pair] = 256 + step

    def encode(self, text: str) -> list[int]:
        """按合并优先级（new_id 从小到大）贪心应用合并，字节 → token 序列。"""
        ids = list(text.encode("utf-8"))
        while len(ids) >= 2:
            pair = min(
                (p for p in zip(ids, ids[1:]) if p in self.merges),
                key=lambda p: self.merges[p],
                default=None,
            )
            if pair is None:
                break
            ids = _merge(ids, pair, self.merges[pair])
        return ids

    def decode(self, ids: list[int]) -> str:
        """token → 字节 → 文本；非法 UTF-8 以 U+FFFD 替换，不抛异常。"""
        vocab = {i: bytes([i]) for i in range(256)}
        for (a, b), nid in self.merges.items():
            vocab[nid] = vocab[a] + vocab[b]
        return b"".join(vocab[i] for i in ids).decode("utf-8", errors="replace")


def _selftest() -> None:
    tok = BPETokenizer()
    corpus = "the quick brown fox jumps over the lazy dog. " * 20 \
        + "the the the the the. "
    tok.train(corpus, num_merges=30)

    # 1) 无损往返：decode(encode(x)) == x（含中文、空串、单字符）
    for sample in ("Hello 你好，世界！", "the quick brown fox", "", "a"):
        assert tok.decode(tok.encode(sample)) == sample, repr(sample)

    # 2) 重复语料确实被压缩：token 数 < 字节数
    n_bytes = len(corpus.encode("utf-8"))
    n_tokens = len(tok.encode(corpus))
    assert n_tokens < n_bytes, (n_tokens, n_bytes)

    # 3) 训练确定性：同语料两次训练合并表一致
    tok2 = BPETokenizer()
    tok2.train(corpus, num_merges=30)
    assert tok2.merges == tok.merges

    # 4) 合并数不超过请求值（语料耗尽会提前停）
    assert len(tok.merges) <= 30

    print(f"selftest ok: {n_bytes} 字节 → {n_tokens} token "
          f"({n_bytes / n_tokens:.2f} B/token), merges={len(tok.merges)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="最小字节级 BPE 分词器")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--train-corpus", default=None,
                    help="用给定文本训练 50 次合并并展示压缩率")
    args = ap.parse_args()
    if args.selftest or not args.train_corpus:
        _selftest()
    if args.train_corpus:
        tok = BPETokenizer()
        tok.train(args.train_corpus, num_merges=50)
        ids = tok.encode(args.train_corpus)
        n = len(args.train_corpus.encode("utf-8"))
        print(f"{n} 字节 → {len(ids)} token ({n / max(len(ids), 1):.2f} B/token)")


if __name__ == "__main__":
    main()
