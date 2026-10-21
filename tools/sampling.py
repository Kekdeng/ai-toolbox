#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sampling.py — LLM 解码采样策略：temperature / top-k / top-p（nucleus）/ 贪心。

同一段 logits，不同的解码策略会给出截然不同的生成风格：
- temperature 越低分布越尖（确定性越强），越高越平（越发散）；
- top-k 只保留概率最大的 k 个候选；
- top-p（nucleus）保留累计概率达到 p 的最小候选集——候选数随分布形状自适应。

用法：
    python tools/sampling.py --selftest
    python tools/sampling.py --logits 2.0,1.0,0.5,0.1 --temperature 0.8 --top-p 0.9 --n 5

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import math
import random


def softmax(logits: list[float], temperature: float = 1.0) -> list[float]:
    """带温度的 softmax（数值稳定：先减最大值）。temperature → 0⁺ 趋近 argmax。"""
    t = max(temperature, 1e-9)
    m = max(logits)
    exps = [math.exp((x - m) / t) for x in logits]
    s = sum(exps)
    return [e / s for e in exps]


def top_k_filter(probs: list[float], k: int) -> list[float]:
    """只保留概率最大的 k 个候选，其余置 0。k<=0 或 k>=n 时原样返回。"""
    if k <= 0 or k >= len(probs):
        return list(probs)
    order = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
    keep = set(order[:k])
    return [p if i in keep else 0.0 for i, p in enumerate(probs)]


def top_p_filter(probs: list[float], p: float) -> list[float]:
    """保留累计概率达到 p 的最小前缀（含跨过 p 的那个候选），其余置 0。"""
    if p >= 1.0:
        return list(probs)
    order = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
    out = [0.0] * len(probs)
    cum = 0.0
    for i in order:
        out[i] = probs[i]
        cum += probs[i]
        if cum >= p:
            break
    return out


def sample(probs: list[float], rng: random.Random) -> int:
    """按概率分布采样一个下标（逆变换法）。"""
    r = rng.random()
    cum = 0.0
    for i, p in enumerate(probs):
        cum += p
        if r < cum:
            return i
    return len(probs) - 1


def greedy(logits: list[float]) -> int:
    """贪心解码：取 logits 最大者（并列取先出现者）。"""
    return max(range(len(logits)), key=lambda i: logits[i])


def _selftest() -> None:
    # softmax：归一化；低温趋近 argmax；高温趋近均匀
    probs = softmax([2.0, 1.0, 0.5, 0.1])
    assert abs(sum(probs) - 1.0) < 1e-12
    sharp = softmax([2.0, 1.0, 0.5, 0.1], temperature=0.01)
    assert sharp[0] > 0.999 and sharp[0] == max(sharp)
    flat = softmax([2.0, 1.0, 0.5, 0.1], temperature=1e3)
    assert max(flat) < 0.3, flat

    # top-k：k=1 即 one-hot；k>=n 原样
    one_hot = top_k_filter(probs, 1)
    assert sum(1 for p in one_hot if p > 0) == 1 and one_hot[0] > 0
    assert top_k_filter(probs, 99) == probs

    # top-p：小 p 只留最高者；中 p 自适应保留前 3 个
    dist = [0.7, 0.2, 0.08, 0.02]
    assert top_p_filter(dist, 0.1) == [0.7, 0.0, 0.0, 0.0]
    kept = top_p_filter(dist, 0.9)
    assert kept == [0.7, 0.2, 0.08, 0.0], kept
    assert top_p_filter(dist, 1.0) == dist

    # 贪心 = argmax
    assert greedy([0.1, 2.0, 1.0]) == 1

    # 采样：固定种子可复现；频率逼近概率（1 万次，容差 ±0.02）
    rng = random.Random(42)
    draws = [sample([0.5, 0.3, 0.2], rng) for _ in range(10_000)]
    freq = [draws.count(i) / len(draws) for i in range(3)]
    for f, p in zip(freq, (0.5, 0.3, 0.2)):
        assert abs(f - p) < 0.02, (freq, p)
    # 同一种子 → 同一采样序列（可复现）
    rng_a, rng_b = random.Random(7), random.Random(7)
    seq_a = [sample([0.5, 0.3, 0.2], rng_a) for _ in range(10)]
    assert seq_a == [sample([0.5, 0.3, 0.2], rng_b) for _ in range(10)]

    print(f"selftest ok: 频率 {[round(f, 3) for f in freq]} vs 目标 [0.5, 0.3, 0.2]")


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM 解码采样策略演示")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--logits", default="2.0,1.0,0.5,0.1",
                    help="逗号分隔的 logits（默认 2.0,1.0,0.5,0.1）")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--top-k", type=int, default=0, help="0 表示不过滤")
    ap.add_argument("--top-p", type=float, default=1.0, help="1.0 表示不过滤")
    ap.add_argument("--n", type=int, default=5, help="采样次数")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if args.selftest or not args.logits:
        _selftest()
        if args.logits == "2.0,1.0,0.5,0.1":
            return

    logits = [float(x) for x in args.logits.split(",")]
    probs = softmax(logits, args.temperature)
    probs = top_k_filter(probs, args.top_k) if args.top_k else probs
    probs = top_p_filter(probs, args.top_p)
    total = sum(probs)
    probs = [p / total for p in probs]          # 过滤后重新归一化

    labels = [f"{p:.3f}" for p in probs]
    print(f"过滤后分布: [{', '.join(labels)}]")
    rng = random.Random(args.seed)
    print(f"{args.n} 次采样(seed={args.seed}): "
          f"{[sample(probs, rng) for _ in range(args.n)]}")


if __name__ == "__main__":
    main()
