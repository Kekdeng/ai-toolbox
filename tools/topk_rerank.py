#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""topk_rerank.py — 多路检索结果融合重排：RRF / 加权 RRF / top-k（纯标准库）。

RAG 里常见 BM25 一份排序、向量检索一份排序，需要一个不依赖分数口径的
融合办法——RRF（Reciprocal Rank Fusion）：score(d) = Σ w_i / (k + rank_i)，
只用名次、只用倒数，简单且惊人地稳健（k=60 是文献常用值）。

同分一律按「首次出现顺序」稳定排序——融合结果可复现、可测试。

用法：
    python tools/topk_rerank.py --selftest
    python tools/topk_rerank.py --rank1 "a,b,c" --rank2 "b,a,c" --top 2

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse


def rrf(rankings: list[list[str]], k: int = 60,
        weights: list[float] | None = None) -> list[tuple[str, float]]:
    """融合多路排名 → [(doc, score)] 降序；零贡献文档不出现。"""
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("weights 长度必须与 rankings 一致")
    scores: dict[str, float] = {}
    first: dict[str, int] = {}
    for i, ranking in enumerate(rankings):
        w = 1.0 if weights is None else float(weights[i])
        for rank, doc in enumerate(ranking):
            scores[doc] = scores.get(doc, 0.0) + w / (k + rank + 1)
            first.setdefault(doc, len(first))
    return sorted(((d, s) for d, s in scores.items() if s > 0.0),
                  key=lambda x: (-x[1], first[x[0]]))


def top_k(scores: dict[str, float], k: int) -> list[tuple[str, float]]:
    """dict → 前 k 个 (key, score) 降序；同分按插入顺序稳定。"""
    order = {d: i for i, d in enumerate(scores)}
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], order[kv[0]]))
    return ranked[:max(k, 0)]


def _selftest() -> None:
    # 两路都认的文档压过单路的；并列按首次出现稳定
    fused = rrf([["a", "b"], ["c", "b"]])
    assert [d for d, _ in fused] == ["b", "a", "c"], fused
    assert fused[1][1] == fused[2][1]           # a 与 c 恰好同分
    assert abs(fused[0][1] - 2 / 62) < 1e-12

    # 平局经典例：两路首名互换 → 同分，稳定序
    tied = rrf([["a", "b", "c"], ["b", "a", "c"]])
    assert [d for d, _ in tied] == ["a", "b", "c"]
    assert tied[0][1] == tied[1][1]

    # 权重为 0 的路完全不计分（零贡献文档被剔除）
    weighted = rrf([["a", "b"], ["a", "c"]], weights=[1.0, 0.0])
    assert [d for d, _ in weighted] == ["a", "b"]
    assert all(d != "c" for d, _ in weighted)

    # k=0 即 1/rank；两路各自首名同分 1.0，按首次出现稳定排序
    assert rrf([["a"], ["b"]], k=0) == [("a", 1.0), ("b", 1.0)]
    assert rrf([["a", "x"], ["x"]], k=0)[0] == ("x", 1.5)   # 1/1 + 1/2

    # top-k 截断 + 稳定性
    assert top_k({"x": 1.0, "y": 1.0, "z": 0.5}, 2) == [("x", 1.0), ("y", 1.0)]
    assert top_k({"x": 1.0}, 0) == []

    # 参数校验
    try:
        rrf([["a"]], weights=[1.0, 2.0])
    except ValueError:
        pass
    else:
        raise AssertionError("weights 长度不符应抛 ValueError")

    print("selftest ok: 双路融合/平局稳定/加权置零/k=0/top-k 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="多路检索融合重排（RRF）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--rank1", default=None, help="第一路排名，逗号分隔")
    ap.add_argument("--rank2", default=None, help="第二路排名，逗号分隔")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()
    if args.selftest or not args.rank1 or not args.rank2:
        _selftest()
        if not args.rank1 or not args.rank2:
            return
    def split(s: str) -> list[str]:
        return [x.strip() for x in s.split(",") if x.strip()]
    fused = rrf([split(args.rank1), split(args.rank2)])
    for doc, score in top_k(dict(fused), args.top):
        print(f"{doc}  {score:.5f}")


if __name__ == "__main__":
    main()
