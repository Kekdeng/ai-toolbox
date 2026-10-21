#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""json_repair.py — 修复 LLM 输出的「差一点就是合法 JSON」文本（纯标准库）。

LLM 输出 JSON 的常见病：代码围栏、前后废话、尾逗号、单引号、// 注释、
中文智能引号、Python 字面量（True/False/None）。本工具按「保守 → 激进」
顺序逐级修复，**每一级都先试 json.loads**，能解析立刻返回——绝不把
原本合法的输入改坏。

用法：
    python tools/json_repair.py --selftest
    python tools/json_repair.py --text "好的，结果：{'a': 1,}"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import json
import re


def _strip_fences(s: str) -> str:
    """剥掉 ```json ... ``` 代码围栏。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    return m.group(1).strip() if m else s.strip()


def _extract_outer(s: str) -> str:
    """截取第一个 {/[ 到最后一个 }/] 之间的部分（去掉前后废话）。"""
    starts = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if not starts:
        return s
    start = min(starts)
    ends = [i for i in (s.rfind("}"), s.rfind("]")) if i > start]
    if not ends:
        return s
    return s[start:max(ends) + 1]


def _strip_comments(s: str) -> str:
    """删掉 // 与 /* */ 注释（字符串字面量内的 / 不动）。"""
    out: list[str] = []
    i, n = 0, len(s)
    in_str = False
    while i < n:
        ch = s[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
        elif ch == '"':
            in_str = True
            out.append(ch)
            i += 1
        elif ch == "/" and i + 1 < n and s[i + 1] == "/":
            i += 2
            while i < n and s[i] != "\n":
                i += 1
        elif ch == "/" and i + 1 < n and s[i + 1] == "*":
            i += 2
            while i + 1 < n and s[i:i + 2] != "*/":
                i += 1
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _normalize_quotes(s: str) -> str:
    """中文智能引号（“ ”）→ 直引号；字符串内的 “ 保持字面量。"""
    out: list[str] = []
    in_str = False
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                out.append(s[i:i + 2])
                i += 2
                continue
            if ch == '"' or ch == "”":
                in_str = False
                out.append('"' if ch == "”" else ch)
                i += 1
                continue
            out.append(ch)
            i += 1
        elif ch == "“" or ch == '"':
            out.append('"')
            in_str = True
            i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _single_to_double(s: str) -> str:
    """单引号字符串 → 双引号（内容里的 " 转义；字符串外的 ' 不误伤已合法部分）。"""
    out: list[str] = []
    in_dq = False
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if in_dq:
            if ch == "\\" and i + 1 < n:
                out.append(s[i:i + 2])
                i += 2
                continue
            if ch == '"':
                in_dq = False
            out.append(ch)
            i += 1
        elif ch == '"':
            in_dq = True
            out.append(ch)
            i += 1
        elif ch == "'":
            j = i + 1
            body: list[str] = []
            while j < n and s[j] != "'":
                if s[j] == "\\" and j + 1 < n:
                    body.append(s[j:j + 2])
                    j += 2
                elif s[j] == '"':
                    body.append('\\"')
                    j += 1
                else:
                    body.append(s[j])
                    j += 1
            out.append('"' + "".join(body) + '"')
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _drop_trailing_commas(s: str) -> str:
    """删掉 } 或 ] 前的尾逗号。"""
    return re.sub(r",(\s*[}\]])", r"\1", s)


def _python_literals(s: str) -> str:
    """Python 字面量 → JSON 字面量（整词匹配，避免误伤标识符）。"""
    s = re.sub(r"(?<!\w)True(?!\w)", "true", s)
    s = re.sub(r"(?<!\w)False(?!\w)", "false", s)
    s = re.sub(r"(?<!\w)None(?!\w)", "null", s)
    s = re.sub(r"(?<!\w)NaN(?!\w)", "null", s)
    return s


_FIXERS = (_strip_fences, _extract_outer, _strip_comments, _normalize_quotes,
           _single_to_double, _drop_trailing_commas, _python_literals)


def repair(text: str) -> tuple[object | None, str | None]:
    """逐级修复并逐级验证；返回 (解析结果, None) 或 (None, 最后一条错误)。"""
    s = text
    err = ""
    for i in range(len(_FIXERS) + 1):
        try:
            return json.loads(s), None
        except json.JSONDecodeError as exc:
            err = str(exc)
            if i < len(_FIXERS):
                s = _FIXERS[i](s)
    return None, err


def _selftest() -> None:
    cases = [
        ('{"a": 1}', {"a": 1}),                                   # 合法：原样通过
        ('```json\n{"a": 1, "b": [1, 2]}\n```',
         {"a": 1, "b": [1, 2]}),                                  # 代码围栏
        ('好的，结果如下：{"a": 1} 请查收', {"a": 1}),               # 前后废话
        ('{"a": 1, "b": [1, 2,],}', {"a": 1, "b": [1, 2]}),       # 尾逗号
        ("{'a': '张三', 'age': 20}", {"a": "张三", "age": 20}),      # 单引号
        ('{“name”: “李四”, “ok”: true}', {"name": "李四", "ok": True}),  # 智能引号
        ("{'ok': True, 'x': None}", {"ok": True, "x": None}),     # Python 字面量
    ]
    for raw, want in cases:
        obj, err = repair(raw)
        assert obj == want, (raw, obj, err)

    # 注释 + 字符串内的 //（URL）不被误伤
    obj, err = repair('{"a": 1, // 注释\n "url": "https://example.com/x"}')
    assert obj == {"a": 1, "url": "https://example.com/x"}, (obj, err)

    # 彻底不是 JSON → (None, err) 而不是抛异常
    obj, err = repair("这不是 JSON")
    assert obj is None and err

    print("selftest ok: 7 类病况全部修复，合法输入原样通过，垃圾输入优雅失败")


def main() -> None:
    ap = argparse.ArgumentParser(description="修复 LLM 输出的近似 JSON")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--text", default=None, help="待修复的 JSON 文本")
    args = ap.parse_args()
    if args.selftest or args.text is None:
        _selftest()
        if args.text is None:
            return
    obj, err = repair(args.text)
    if obj is None:
        raise SystemExit(f"无法修复: {err}")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
