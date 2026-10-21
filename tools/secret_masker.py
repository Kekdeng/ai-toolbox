#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""secret_masker.py — 日志里的密钥/凭证脱敏（纯标准库）。

日志采集常把 Authorization 头、API key、JWT 原样落盘——这是泄漏事故的
最大来源之一。本工具按模式把常见凭证替换为占位符：
Bearer token / JWT / sk- 风格 API key / password·token 等键值对 / Cookie。

正则近似（键值对按 `键[=: ] 值` 的形状识别），覆盖不了自定义协议头；
请把它放在「日志写出」这一层兜底，密钥本身优先走环境变量。

用法：
    python tools/secret_masker.py --selftest
    python tools/secret_masker.py --text "Authorization: Bearer abc..."

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re

# 顺序即执行顺序：具体形态在前，泛化键值对在后
PATTERNS: list[tuple[str, str, str]] = [
    # Bearer token（可带 Authorization: 头前缀，整段替换）
    ("Bearer", r"(?i)\b(authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/=-]{8,}",
     r"\g<1>Bearer ***"),
    # JWT：三段 base64url（eyJ 开头是 JWT 头的强特征）
    ("JWT", r"(?<![A-Za-z0-9._-])eyJ[A-Za-z0-9_-]{4,}\."
            r"[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}", "[JWT]"),
    # sk- 风格 API key（16 位以上）
    ("API_KEY", r"\bsk-[A-Za-z0-9]{16,}\b", "[API_KEY]"),
    # 键值对：password/secret/token/api_key 后跟 值
    # （不含 authorization——已由 Bearer 规则覆盖，避免二次吞掉遮罩后的值）
    ("KV", r"(?i)\b(password|passwd|secret|token|api[_-]?key)"
           r"\s*([=:])\s*\S+", r"\1\2***"),
    # Cookie 头
    ("Cookie", r"(?i)\bcookie\s*:\s*\S+", "Cookie: ***"),
]


def mask(text: str) -> tuple[str, list[tuple[str, str]]]:
    """脱敏；返回（替换后文本, [(类别, 命中原文), …] 按出现顺序）。"""
    findings: list[tuple[str, str]] = []

    def _sub(m: re.Match[str], name: str = "", repl: str = "") -> str:
        findings.append((name, m.group(0)))
        if repl.startswith("\\"):        # 反向引用保留原键名/分隔符
            return m.expand(repl)
        return repl

    for name, pat, repl in PATTERNS:
        text = re.sub(pat, lambda m, n=name, r=repl: _sub(m, n, r), text)
    return text, findings


def _selftest() -> None:
    # Bearer 头整段遮罩（保留头名）
    masked, found = mask("Authorization: Bearer abc123XYZ.def_456 end")
    assert masked == "Authorization: Bearer *** end", masked
    assert found == [("Bearer", "Authorization: Bearer abc123XYZ.def_456")]
    # 裸 Bearer（无头前缀）也遮
    assert mask("Bearer tok12345678")[0] == "Bearer ***"

    # JWT：query 串里的三段式令牌
    masked2, _ = mask("GET /cb?access_token=eyJhbGciOiJFUzI1NiJ9."
                      "eyJzdWIiOiJ1c2VyIn0.sig1234567890abcd HTTP/1.1")
    assert masked2 == "GET /cb?access_token=[JWT] HTTP/1.1", masked2

    # sk- key：达标才遮，短的放过
    masked3, _ = mask("key sk-abcdefghijklmnop1234 ok")
    assert masked3 == "key [API_KEY] ok"
    assert mask("sk-short")[0] == "sk-short"

    # 键值对：保留原键名与分隔符；_ 连接的键（api_key）也认
    masked4, _ = mask("password=hunter2")
    assert masked4 == "password=***"
    masked5, _ = mask("db connect api_key: abc123 done")
    assert masked5 == "db connect api_key:*** done", masked5

    # access_token 下划线前缀不触发 \btoken（无整词边界）
    masked6, _ = mask("access_token=abc123")
    assert masked6 == "access_token=abc123", masked6

    # Cookie 头：只遮值，后面的参数保留
    masked7, _ = mask("Set-Cookie: session=xyz123; Path=/")
    assert masked7 == "Set-Cookie: *** Path=/", masked7

    # 正常日志不误伤
    plain = "2026-10-21 10:00 user=42 login ok from 10.0.0.1"
    assert mask(plain) == (plain, [])

    print("selftest ok: Bearer/JWT/sk-key/KV/Cookie/不误伤 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="日志密钥/凭证脱敏")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--text", default=None, help="要脱敏的日志文本")
    ap.add_argument("--file", default=None, help="要脱敏的日志文件")
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
    masked, found = mask(text)
    print(masked)
    if found:
        print(f"--- 已遮蔽 {len(found)} 处: {[n for n, _ in found]}")


if __name__ == "__main__":
    main()
