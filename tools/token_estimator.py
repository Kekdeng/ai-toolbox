#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""token_estimator.py — 不装 tokenizer 粗估 LLM prompt 的 token 量与费用。

启发式口径（±20% 量级的估计，不是精确计数）：
- CJK 字符 ≈ 1 token/字（可调）；其余字符（含空格/标点）≈ 4 字符/token；
- chat 消息每条额外 +4 tokens（role/格式开销）+ 全局 3 tokens。

价格表为 2026-10 快照（USD / 1M tokens），**随时过期**，仅演示计费口径；
精确 token 数请用各家官方 tokenizer（tiktoken / anthropic count-tokens）。

用法：
    python tools/token_estimator.py --selftest
    python tools/token_estimator.py --text "要估的文本" --model gpt-4o --out-tokens 500

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse

# USD / 1M tokens：(输入, 输出)。2026-10 快照，仅演示口径。
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-sonnet": (3.00, 15.00),
    "claude-haiku": (1.00, 5.00),
    "deepseek-chat": (0.27, 1.10),
}

MSG_OVERHEAD = 4      # 每条消息的 role/格式开销
PRIMING = 3           # 一次请求的全局开销


def _is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def estimate_tokens(text: str, cjk_per_token: float = 1.0,
                    ascii_chars_per_token: float = 4.0) -> int:
    """启发式 token 估计；空文本为 0，非空至少 1。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if _is_cjk(ch))
    other = len(text) - cjk
    return max(1, round(cjk * cjk_per_token
                        + other / ascii_chars_per_token))


def estimate_messages(msgs: list[dict[str, str]], cjk_per_token: float = 1.0,
                      ) -> int:
    """chat 消息列表的 token 估计（逐条 content + 每条开销 + 全局开销）。"""
    return (sum(estimate_tokens(m.get("content", ""), cjk_per_token)
                + MSG_OVERHEAD for m in msgs)
            + (PRIMING if msgs else 0))


def estimate_cost(model: str, in_tokens: int, out_tokens: int = 0,
                  table: dict[str, tuple[float, float]] | None = None,
                  ) -> float:
    """按 (USD/1M) 价格表算费用；未知模型抛 ValueError。"""
    tab = table or PRICE_TABLE
    if model not in tab:
        raise ValueError(f"未知模型: {model!r}，可用: {sorted(tab)}")
    p_in, p_out = tab[model]
    return in_tokens / 1e6 * p_in + out_tokens / 1e6 * p_out


def _selftest() -> None:
    # token 估计：空 0；CJK 1:1；ASCII 4:1；混合；非空最小 1
    assert estimate_tokens("") == 0
    assert estimate_tokens("你好") == 2
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("hello") == 1          # 1.25 → 1
    assert estimate_tokens("你好hello") == 3      # 2 + 1.25 → 3
    assert estimate_tokens("a") == 1

    # chat 消息开销：3 条空消息 = 3×(0+4) + 3
    msgs = [{"role": "user", "content": ""} for _ in range(3)]
    assert estimate_messages(msgs) == 15

    # 费用：1M 输入 token 的 gpt-4o = $2.50；各 100k = 0.25 + 1.00
    assert estimate_cost("gpt-4o", 1_000_000) == 2.5
    assert abs(estimate_cost("gpt-4o", 100_000, 100_000) - 1.25) < 1e-9

    # 自定义价格表；未知模型报错
    assert abs(estimate_cost("my", 1e6, 1e6,
                             table={"my": (1.0, 3.0)}) - 4.0) < 1e-9
    try:
        estimate_cost("nope", 1)
    except ValueError:
        pass
    else:
        raise AssertionError("未知模型应抛 ValueError")

    print("selftest ok: token 估计/消息开销/费用计算/未知模型 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="prompt token/费用粗估")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--text", default=None, help="要估算的文本")
    ap.add_argument("--file", default=None, help="要估算的文本文件")
    ap.add_argument("--model", default="gpt-4o-mini",
                    help=f"模型名，可选: {sorted(PRICE_TABLE)}")
    ap.add_argument("--out-tokens", type=int, default=0,
                    help="预估输出 token 数（算费用用）")
    args = ap.parse_args()
    if args.selftest or (not args.text and not args.file):
        _selftest()
        if not args.text and not args.file:
            return
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text or ""
    in_tok = estimate_tokens(text)
    print(f"估计输入 ≈ {in_tok} tokens（启发式 ±20%）")
    print(f"费用({args.model}) ≈ ${estimate_cost(args.model, in_tok, args.out_tokens):.4f}")


if __name__ == "__main__":
    main()
