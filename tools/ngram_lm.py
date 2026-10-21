#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ngram_lm.py — 字符级 n-gram 语言模型：训练/打分/困惑度/生成（纯标准库）。

最老派也最直白的语言模型：P(ch | 前 n-1 个字符) 由训练文本里的字符 n-gram
计数估计，加 k 平滑（add-k Laplace）兜住未登录组合。生成时逐字符采样、
滑动上下文。适合教学演示与文本的「似然粗尺」（困惑度）。

用法：
    python tools/ngram_lm.py --selftest
    python tools/ngram_lm.py --train-corpus "一些训练文本……" --gen 60 --n 3

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import math
import random
from collections import Counter


class CharNGramLM:
    """字符级 n-gram 模型；vocab 只含训练文本出现过的字符。"""

    def __init__(self, n: int = 3, k: float = 1.0) -> None:
        if n < 1:
            raise ValueError("n 必须 ≥ 1")
        if k < 0:
            raise ValueError("k（平滑强度）必须 ≥ 0")
        self.n = n
        self.k = k
        self.ctx: Counter = Counter()       # (n-1) 元上下文出现次数
        self.ngrams: Counter = Counter()    # n 元组出现次数
        self.vocab: set[str] = set()

    def train(self, text: str) -> None:
        self.vocab.update(text)
        for i in range(len(text) - self.n + 1):
            gram = text[i:i + self.n]
            self.ngrams[gram] += 1
            self.ctx[gram[:-1]] += 1

    def prob(self, ctx: str, ch: str) -> float:
        """P(ch | ctx)，加 k 平滑；分母带词表大小 V，未登录对也有非零概率。"""
        v = len(self.vocab) or 1
        return ((self.ngrams.get(ctx + ch, 0) + self.k)
                / (self.ctx.get(ctx, 0) + self.k * v))

    def perplexity(self, text: str) -> float:
        """exp(平均负对数似然)；text 短于 n 时无完整窗口，返回 inf。"""
        windows = len(text) - self.n + 1
        if windows < 1:
            return math.inf
        log_sum = 0.0
        for i in range(windows):
            log_sum -= math.log(self.prob(text[i:i + self.n - 1],
                                          text[i + self.n - 1]))
        return math.exp(log_sum / windows)

    def generate(self, length: int, rng: random.Random,
                 prompt: str = "") -> str:
        """从 prompt 出发按模型分布逐字符采样 length 个字符（滑动上下文）。"""
        vocab = sorted(self.vocab)
        if not vocab:
            return prompt
        ctx = prompt[-(self.n - 1):] if self.n > 1 else ""
        out = list(prompt)
        for _ in range(length):
            weights = [self.prob(ctx, ch) for ch in vocab]
            ch = rng.choices(vocab, weights=weights, k=1)[0]
            out.append(ch)
            ctx = (ctx + ch)[-(self.n - 1):] if self.n > 1 else ""
        return "".join(out)


def _selftest() -> None:
    # 计数：abab 的 bigram
    lm = CharNGramLM(n=2, k=1.0)
    lm.train("abab")
    assert lm.ngrams["ab"] == 2 and lm.ngrams["ba"] == 1
    assert lm.ctx["a"] == 2 and lm.ctx["b"] == 1

    # 词表上的条件概率和为 1（平滑把质量摊到未登录组合）
    for ctx in ("a", "b"):
        total = sum(lm.prob(ctx, ch) for ch in sorted(lm.vocab))
        assert abs(total - 1.0) < 1e-9

    # 困惑度：见过的文本 < 全新字符的文本
    lm3 = CharNGramLM(n=3, k=0.01)
    lm3.train("the cat sat on the mat. " * 5)
    ppl_seen = lm3.perplexity("the cat sat on the mat.")
    ppl_unseen = lm3.perplexity("zzz qqq xxx jjj")
    assert ppl_seen < ppl_unseen, (ppl_seen, ppl_unseen)

    # 窗口不足 → inf
    assert lm3.perplexity("a") == math.inf

    # 生成：只产出词表字符，且同种子可复现
    g1 = lm3.generate(40, random.Random(7))
    assert len(g1) == 40 and set(g1) <= lm3.vocab
    assert g1 == lm3.generate(40, random.Random(7))

    # n=1（unigram，无上下文）也自洽
    uni = CharNGramLM(n=1)
    uni.train("aabb")
    assert abs(sum(uni.prob("", c) for c in sorted(uni.vocab)) - 1.0) < 1e-9

    # 参数校验
    for bad in (lambda: CharNGramLM(n=0), lambda: CharNGramLM(k=-1)):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError(bad)

    print(f"selftest ok: ppl seen={ppl_seen:.2f} < unseen={ppl_unseen:.1f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="字符级 n-gram 语言模型演示")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--train-corpus", default=None, help="训练文本")
    ap.add_argument("--gen", type=int, default=60, help="生成长度")
    ap.add_argument("--n", type=int, default=3, help="n-gram 阶数")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    if args.selftest or not args.train_corpus:
        _selftest()
        if not args.train_corpus:
            return
    lm = CharNGramLM(n=args.n)
    lm.train(args.train_corpus)
    print(f"ppl(训练文本) = {lm.perplexity(args.train_corpus):.2f}")
    print(f"生成: {lm.generate(args.gen, random.Random(args.seed))!r}")


if __name__ == "__main__":
    main()
