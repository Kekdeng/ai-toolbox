#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kv_cache_memory.py — LLM 推理显存估算：模型权重 + KV cache（纯标准库）。

部署 LLM 前最常问的两个问题：
1. 权重占多少显存？  → params × dtype 字节数
2. KV cache 占多少？  → 2(K,V) × layers × batch × seq_len × kv_heads × head_dim × dtype

GQA（分组查询注意力）模型的 kv_heads 远小于注意力头数——这是 KV cache
差数倍量级的来源（如 llama3-8b 是 8 个 KV 头而非 32 个）。

未计入：激活值、CUDA 上下文、框架开销——实际占用会更高，本工具给下界量级。

用法：
    python tools/kv_cache_memory.py --selftest
    python tools/kv_cache_memory.py --preset llama3-8b --seq-len 8192 --batch 1
    python tools/kv_cache_memory.py --params 7e9 --layers 32 --kv-heads 32 \
        --head-dim 128 --seq-len 4096

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse

GIB = 1024 ** 3

# 每参数字节数（fp8/int4 为存储口径，计算精度另计）
DTYPE_BYTES: dict[str, float] = {
    "fp32": 4.0, "fp16": 2.0, "bf16": 2.0, "fp8": 1.0, "int8": 1.0,
    "int4": 0.5,
}

# 常见开源模型的 (参数量, 层数, KV 头数, head_dim)，可 --preset 直接用
PRESETS: dict[str, dict[str, float]] = {
    "gpt2":          {"params": 124e6,  "layers": 12, "kv_heads": 12,
                      "head_dim": 64},
    "llama2-7b":     {"params": 6.74e9, "layers": 32, "kv_heads": 32,
                      "head_dim": 128},
    "llama2-7b-gqa": {"params": 6.74e9, "layers": 32, "kv_heads": 8,
                      "head_dim": 128},
    "llama3-8b":     {"params": 8.03e9, "layers": 32, "kv_heads": 8,
                      "head_dim": 128},
    "qwen2.5-14b":   {"params": 14.7e9, "layers": 48, "kv_heads": 8,
                      "head_dim": 128},
}


def weights_bytes(params: float, dtype: str = "fp16") -> float:
    """模型权重的显存占用。"""
    return params * DTYPE_BYTES[dtype.lower()]


def kv_cache_bytes(layers: int, kv_heads: int, head_dim: int, seq_len: int,
                   batch: int = 1, dtype: str = "fp16") -> float:
    """KV cache 显存：2 × layers × batch × seq_len × kv_heads × head_dim × bytes。"""
    b = DTYPE_BYTES[dtype.lower()]
    return 2.0 * layers * batch * seq_len * kv_heads * head_dim * b


def kv_per_token_bytes(layers: int, kv_heads: int, head_dim: int,
                       dtype: str = "fp16") -> float:
    """每 token 每 batch 的 KV cache 占用（seq_len=1 的特例，方便横向对比）。"""
    return kv_cache_bytes(layers, kv_heads, head_dim, 1, 1, dtype)


def fmt(n: float) -> str:
    """字节数 → GiB 可读字符串。"""
    if n >= GIB:
        return f"{n / GIB:.2f} GiB"
    return f"{n / 1024:.1f} KiB"


def _selftest() -> None:
    # 权重：7B 级 fp16 ≈ 14 GB 量级（手算可验证：6.74e9 × 2 B）
    w = weights_bytes(6.74e9, "fp16")
    assert abs(w - 13.48e9) < 1.0, w
    assert weights_bytes(8.03e9, "int4") == 8.03e9 * 0.5

    # KV per token：llama2-7b MHA（32 KV 头）= 512 KiB/token，GQA（8 头）= 128 KiB/token
    mha = kv_per_token_bytes(32, 32, 128, "fp16")
    gqa = kv_per_token_bytes(32, 8, 128, "fp16")
    assert mha == 2 * 32 * 32 * 128 * 2 == 512 * 1024, mha
    assert gqa == 128 * 1024, gqa
    assert mha / gqa == 4.0            # KV 头数比 = 显存比

    # batch / seq_len 线性放大
    full = kv_cache_bytes(32, 8, 128, seq_len=8192, batch=4, dtype="fp16")
    assert full == gqa * 8192 * 4

    # fmt 边界
    assert fmt(2 * GIB) == "2.00 GiB"
    assert fmt(128 * 1024) == "128.0 KiB"

    print(f"selftest ok: GQA 每 token KV {fmt(gqa)}（MHA 的 1/4），"
          f"7B fp16 权重 {fmt(weights_bytes(6.74e9))}")


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM 推理显存估算（权重 + KV cache）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--preset", choices=sorted(PRESETS), default=None,
                    help="使用预置模型配置")
    ap.add_argument("--params", type=float, default=None, help="参数量，如 7e9")
    ap.add_argument("--layers", type=int, default=None)
    ap.add_argument("--kv-heads", type=int, default=None,
                    help="KV 头数（GQA 模型远小于注意力头数）")
    ap.add_argument("--head-dim", type=int, default=None)
    ap.add_argument("--seq-len", type=int, default=4096)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--dtype", default="fp16", choices=sorted(DTYPE_BYTES))
    args = ap.parse_args()
    if args.selftest or (not args.preset and args.params is None):
        _selftest()
        if not args.preset and args.params is None:
            return

    cfg = dict(PRESETS[args.preset]) if args.preset else {
        "params": args.params, "layers": args.layers,
        "kv_heads": args.kv_heads, "head_dim": args.head_dim,
    }
    if any(v is None for v in cfg.values()):
        ap.error("自定义配置需给出 --params --layers --kv-heads --head-dim 全部四项")

    w = weights_bytes(cfg["params"], args.dtype)
    kv = kv_cache_bytes(cfg["layers"], cfg["kv_heads"], cfg["head_dim"],
                        args.seq_len, args.batch, args.dtype)
    name = args.preset or "custom"
    print(f"[{name}] dtype={args.dtype} batch={args.batch} seq_len={args.seq_len}")
    print(f"  权重:     {fmt(w)}")
    print(f"  KV cache: {fmt(kv)}（每 token {fmt(kv_per_token_bytes(cfg['layers'], cfg['kv_heads'], cfg['head_dim'], args.dtype))} × batch）")
    print(f"  合计下界: {fmt(w + kv)}（未计激活/框架开销）")


if __name__ == "__main__":
    main()
