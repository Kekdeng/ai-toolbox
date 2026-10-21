#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sse_parser.py — 解析/回放 LLM 流式输出的 SSE 文本（纯标准库，离线）。

把 OpenAI / Anthropic 风格的 Server-Sent Events 文本流（curl 存档、日志、
抓包）解析成事件列表，抽出 JSON payload，拼接增量文本——调试流式接口或
离线回放时用。

SSE 规则（精简版）：事件间以空行分隔；字段 data:/event:/id:/retry:；
同事件多条 data: 行以换行拼接成一个 data；`:` 开头为注释行。

用法：
    python tools/sse_parser.py --selftest
    python tools/sse_parser.py --file stream.log

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import json


def parse_sse(text: str) -> list[dict[str, str]]:
    """SSE 文本 → [{"event":…, "id":…, "data":…}, …]（字段按出现顺序合并）。"""
    events: list[dict[str, str]] = []
    cur: dict[str, str] = {}
    for line in text.splitlines():
        if line == "":
            if cur:
                events.append(cur)
                cur = {}
            continue
        if line.startswith(":"):          # 注释行（如 keep-alive）
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            cur["data"] = cur.get("data", "") + ("\n" if "data" in cur else "") + value
        else:
            cur[field] = value
    if cur:                               # 流末尾没有空行也收尾
        events.append(cur)
    return events


def json_payloads(events: list[dict[str, str]], skip_done: bool = True,
                  ) -> list[object]:
    """每个事件的 data 尝试 json.loads；[DONE] 哨兵跳过；非 JSON 保留原文。"""
    out: list[object] = []
    for ev in events:
        raw = ev.get("data", "")
        if skip_done and raw.strip() == "[DONE]":
            continue
        try:
            out.append(json.loads(raw))
        except ValueError:
            out.append(raw)
    return out


def join_openai_deltas(payloads: list[object]) -> str:
    """OpenAI 风格 payload → 拼接 choices[*].delta.content。"""
    parts: list[str] = []
    for p in payloads:
        if not isinstance(p, dict):
            continue
        for choice in p.get("choices", []):
            content = choice.get("delta", {}).get("content")
            if content:
                parts.append(content)
    return "".join(parts)


def join_anthropic_deltas(payloads: list[object]) -> str:
    """Anthropic 风格 payload → 拼接 content_block_delta 事件的 delta.text。"""
    parts: list[str] = []
    for p in payloads:
        if (isinstance(p, dict) and p.get("type") == "content_block_delta"):
            text = p.get("delta", {}).get("text")
            if text:
                parts.append(text)
    return "".join(parts)


def _selftest() -> None:
    stream = (": keep-alive\n\n"
              "event: delta\nid: 1\ndata: {\"text\": \"你\"}\n\n"
              "event: delta\ndata: {\"text\": \"好\",\ndata:  \"x\": 1}\n\n"
              "data: [DONE]\n\n")
    events = parse_sse(stream)
    assert len(events) == 3                        # 注释组与 [DONE] 均不成事件体
    assert events[0] == {"event": "delta", "id": "1",
                         "data": '{"text": "你"}'}
    assert json.loads(events[1]["data"]) == {"text": "好", "x": 1}  # 多行 data 拼接
    payloads = json_payloads(events)
    assert payloads == [{"text": "你"}, {"text": "好", "x": 1}]

    # OpenAI 回放
    openai_stream = ('data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
                     'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
                     "data: [DONE]\n\n")
    assert join_openai_deltas(json_payloads(parse_sse(openai_stream))) == "你好"

    # Anthropic 回放
    anth_stream = ('data: {"type":"content_block_delta",'
                   '"delta":{"type":"text_delta","text":"你"}}\n\n'
                   'data: {"type":"content_block_delta",'
                   '"delta":{"type":"text_delta","text":"好"}}\n\n')
    assert join_anthropic_deltas(json_payloads(parse_sse(anth_stream))) == "你好"

    # 边界：空输入；无空行收尾；非 JSON data 保留原文
    assert parse_sse("") == []
    assert parse_sse("data: x") == [{"data": "x"}]
    assert json_payloads([{"data": "oops"}]) == ["oops"]

    print("selftest ok: 事件解析/多行 data/[DONE]/两家增量拼接/边界 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="SSE 流式输出解析/回放")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--file", default=None, help="SSE 文本流文件路径")
    args = ap.parse_args()
    if args.selftest or not args.file:
        _selftest()
        if not args.file:
            return
    with open(args.file, encoding="utf-8") as f:
        payloads = json_payloads(parse_sse(f.read()))
    print(f"共 {len(payloads)} 个 payload")
    for joiner in (join_openai_deltas, join_anthropic_deltas):
        text = joiner(payloads)
        if text:
            print(f"拼接文本: {text}")


if __name__ == "__main__":
    main()
