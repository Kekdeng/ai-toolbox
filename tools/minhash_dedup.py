#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""minhash_dedup.py — MinHash 近似 Jaccard 文档去重（纯标准库，确定性）。

语料清洗（尤其 LLM 预训练语料）的第一道闸：把每个文档切成字符 shingle，
用 k 个带盐哈希各取最小值得到签名，两签名的吻合率 ≈ Jaccard 相似度。
再用「与新邻相似度超阈值就丢弃」的贪心去重。MD5 带盐替代随机置换——
不依赖 numpy，且**完全可复现**。

适合中文（按字符 shingle 不用分词）；万级文档内 O(n²·k) 足够，更大规模
请上 datasketch/LSH。

用法：
    python tools/minhash_dedup.py --selftest

依赖：无（Python 3.10+，hashlib 是标准库）。
"""
from __future__ import annotations

import argparse
import hashlib


def shingles(text: str, size: int = 3) -> set[str]:
    """字符级 n-gram 集合；短文本回退为整串，空串为空集。"""
    if len(text) < size:
        return {text} if text else set()
    return {text[i:i + size] for i in range(len(text) - size + 1)}


def _hash(s: str, salt: int) -> int:
    digest = hashlib.md5(f"{salt}:{s}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def minhash_sig(sh: set[str], sig_len: int = 128, seed: int = 0) -> list[int]:
    """k 个盐位各取最小哈希；空集合的签名为全零。"""
    if not sh:
        return [0] * sig_len
    return [min(_hash(s, seed + i) for s in sh) for i in range(sig_len)]


def jaccard_est(sig_a: list[int], sig_b: list[int]) -> float:
    """签名吻合率 ≈ Jaccard 相似度；k 越大越准。"""
    n = len(sig_a)
    if n == 0 or len(sig_b) != n:
        raise ValueError("签名长度须一致且非零")
    return sum(a == b for a, b in zip(sig_a, sig_b)) / n


def jaccard_exact(a: set[str], b: set[str]) -> float:
    """精确 Jaccard（对照用）。"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedup(docs: list[str], threshold: float = 0.7, sig_len: int = 128,
          shingle_size: int = 3) -> list[bool]:
    """贪心去重：返回 keep 标志列表；相似对保留先出现者。"""
    sigs = [minhash_sig(shingles(d, shingle_size), sig_len) for d in docs]
    kept_sigs: list[list[int]] = []
    keep: list[bool] = []
    for sig in sigs:
        if any(jaccard_est(sig, old) >= threshold for old in kept_sigs):
            keep.append(False)
        else:
            keep.append(True)
            kept_sigs.append(sig)
    return keep


def _selftest() -> None:
    doc_a = "机器学习模型训练需要大量数据和算力支持"
    docs = [
        doc_a,
        doc_a,                                   # 完全相同 → 丢
        "completely different content here!!",
        "今天天气不错适合出门散步",
        doc_a[:-1] + "支持呀",                    # 末尾多 1 字的近似重复 → 丢
    ]
    keep = dedup(docs, threshold=0.7, sig_len=128)
    assert keep == [True, False, True, True, False], keep

    # 完全相同的签名精确相等 → est 恰为 1.0
    sig_a = minhash_sig(shingles(doc_a), 128)
    assert jaccard_est(sig_a, sig_a) == 1.0

    # 近似对的估计贴近精确值；不相关对精确为 0、估计接近 0
    near = "机器学习模型训练需要大量数据和算力支持呀"
    exact = jaccard_exact(shingles(doc_a), shingles(near))
    est = jaccard_est(sig_a, minhash_sig(shingles(near), 128))
    assert abs(est - exact) < 0.15, (est, exact)
    dis_est = jaccard_est(sig_a, minhash_sig(shingles(docs[2]), 128))
    assert dis_est < 0.1 and jaccard_exact(shingles(doc_a), shingles(docs[2])) == 0.0

    # 空串/超短串不炸：两个空串互为重复
    assert dedup(["", ""]) == [True, False]
    assert shingles("") == set() and shingles("ab") == {"ab"}

    print(f"selftest ok: 相同丢弃/近似丢弃/无关保留，est={est:.3f} vs exact={exact:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="MinHash 近似去重")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args()
    if args.selftest or True:
        _selftest()


if __name__ == "__main__":
    main()
