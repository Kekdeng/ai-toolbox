#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chat_template.py — 把 chat 消息列表渲染成各家模型的 prompt 模板（纯标准库）。

调试本地模型 / 复现请求时经常需要「消息列表 → 原始 prompt 字符串」：
- chatml   ChatML（Qwen 等）：`<|im_start|>role … <|im_end|>`
- llama3   Llama 3：`<|start_header_id|>role<|end_header_id|> … <|eot_id|>`
- alpaca   Alpaca 单轮：### Instruction / ### Response

渲染均以「生成提示」收尾（模型接着写 assistant 段）。

用法：
    python tools/chat_template.py --selftest
    python tools/chat_template.py --system "你是助手" --user "你好" --style chatml

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse

ROLES = {"system", "user", "assistant"}


def _check(messages: list[dict[str, str]]) -> None:
    if not messages:
        raise ValueError("messages 不能为空")
    for m in messages:
        if m.get("role") not in ROLES:
            raise ValueError(f"未知 role: {m.get('role')!r}，允许 {sorted(ROLES)}")


def render_chatml(messages: list[dict[str, str]]) -> str:
    _check(messages)
    out = "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
                  for m in messages)
    return out + "<|im_start|>assistant\n"


def render_llama3(messages: list[dict[str, str]]) -> str:
    _check(messages)
    out = "<|begin_of_text|>" + "".join(
        f"<|start_header_id|>{m['role']}<|end_header_id|>\n\n"
        f"{m['content']}<|eot_id|>" for m in messages)
    return out + "<|start_header_id|>assistant<|end_header_id|>\n\n"


def render_alpaca(messages: list[dict[str, str]]) -> str:
    _check(messages)
    rest = list(messages)
    system = ""
    if rest[0]["role"] == "system":
        system = rest[0]["content"]
        rest = rest[1:]
    if len(rest) != 1 or rest[0]["role"] != "user":
        raise ValueError("alpaca 仅支持 [system?] + 单条 user")
    prefix = f"{system}\n\n" if system else ""
    return f"{prefix}### Instruction:\n{rest[0]['content']}\n### Response:\n"


_RENDERERS = {"chatml": render_chatml, "llama3": render_llama3,
              "alpaca": render_alpaca}


def render(messages: list[dict[str, str]], style: str = "chatml") -> str:
    """按模板名渲染；未知模板抛 ValueError。"""
    if style not in _RENDERERS:
        raise ValueError(f"未知模板: {style!r}，可选 {sorted(_RENDERERS)}")
    return _RENDERERS[style](messages)


def _selftest() -> None:
    msgs = [{"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"}]

    assert render_chatml(msgs) == (
        "<|im_start|>system\n你是助手<|im_end|>\n"
        "<|im_start|>user\n你好<|im_end|>\n"
        "<|im_start|>assistant\n")

    assert render_llama3(msgs) == (
        "<|begin_of_text|>"
        "<|start_header_id|>system<|end_header_id|>\n\n你是助手<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n你好<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n")

    assert render_alpaca(msgs) == "你是助手\n\n### Instruction:\n你好\n### Response:\n"
    assert render_alpaca(msgs[1:]) == "### Instruction:\n你好\n### Response:\n"

    # 多轮也保持形状；dispatch 与错误路径
    multi = msgs + [{"role": "assistant", "content": "你好！需要什么？"}]
    assert "<|im_start|>assistant\n你好！需要什么？<|im_end|>\n" in render_chatml(multi)
    assert render(multi, "llama3") == render_llama3(multi)
    for bad, exc in ((lambda: render(msgs, "nope"), "nope"),
                     (lambda: render([], "chatml"), "空"),
                     (lambda: render([{"role": "tool", "content": "x"}], "chatml"), "role")):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError(exc)
    try:
        render_alpaca(multi)
    except ValueError:
        pass
    else:
        raise AssertionError("alpaca 多轮应报错")

    print("selftest ok: chatml/llama3/alpaca 精确形状 + 错误路径 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="chat 消息模板渲染")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--system", default=None, help="system 消息内容")
    ap.add_argument("--user", default=None, help="user 消息内容")
    ap.add_argument("--style", default="chatml", choices=sorted(_RENDERERS))
    args = ap.parse_args()
    if args.selftest or args.user is None:
        _selftest()
        if args.user is None:
            return
    msgs = ([{"role": "system", "content": args.system}] if args.system else [])
    msgs.append({"role": "user", "content": args.user})
    print(render(msgs, args.style), end="")


if __name__ == "__main__":
    main()
