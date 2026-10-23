#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""template_mini.py — 迷你文本模板：变量 / 点路径 / if-else / for。

拼 prompt、生成配置时只要四种积木，不想要一门新语言：

- 变量：`{{ name }}`、点路径 `{{ a.b.c }}`（只走 dict 键）；
- 条件：`{{ if ok }}…{{ else }}…{{ end }}`——Python 真值（空串/
  0/None/空表为假）；
- 循环：`{{ for u in users }}…{{ end }}`——目标须是 list/tuple，
  循环变量推入内层作用域，出块即还原；
- 严格缺失：变量不存在直接 KeyError 报名点路径——prompt 里漏
  占位符必须炸，而不是静默渲染出空串。

标签统一 `{{ … }}`（首词 if/for/else/end 是保留字），未闭合的
`{{` 保持字面文本。块解析递归下降，嵌套天然正确。

用法：
    python tools/template_mini.py --selftest
    python tools/template_mini.py --template "你好 {{ name }}" --ctx '{"name": "世界"}'

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import json
import re

_TAG = re.compile(r"\{\{(.*?)\}\}")
_IF = re.compile(r"if\s+(\S+)")
_FOR = re.compile(r"for\s+([A-Za-z_]\w*)\s+in\s+(\S+)")
_HEADS = ("if", "for", "else", "end")


class _Scope:
    """作用域链：循环变量推栈，出块弹栈，由内向外解析。"""

    def __init__(self, base: dict) -> None:
        self.stack = [base]

    def push(self, d: dict) -> None:
        self.stack.append(d)

    def pop(self) -> None:
        self.stack.pop()

    def root(self, name: str):
        for d in reversed(self.stack):
            if name in d:
                return d[name]
        raise KeyError(name)


def _lookup(path: str, scope: _Scope):
    """点路径解析（只走 dict 键），缺一环即 KeyError(完整路径)。"""
    parts = path.split(".")
    try:
        node = scope.root(parts[0])
    except KeyError:
        raise KeyError(path) from None
    for p in parts[1:]:
        if isinstance(node, dict) and p in node:
            node = node[p]
        else:
            raise KeyError(path)
    return node


def _tokenize(template: str) -> list[tuple[str, str]]:
    """→ [("text", s) | ("tag", 内文)]；未闭合的 {{ 保持字面。"""
    toks: list[tuple[str, str]] = []
    pos = 0
    for m in _TAG.finditer(template):
        if m.start() > pos:
            toks.append(("text", template[pos:m.start()]))
        toks.append(("tag", m.group(1).strip()))
        pos = m.end()
    if pos < len(template):
        toks.append(("text", template[pos:]))
    return toks


def _head(val: str) -> str:
    return val.split(None, 1)[0] if val else ""


def _match_end(toks: list, start: int) -> int:
    """start 起找配对 end（if/for 嵌套计数），返回 end 下标。"""
    depth = 1
    for j in range(start, len(toks)):
        if toks[j][0] != "tag":
            continue
        head = _head(toks[j][1])
        if head in ("if", "for"):
            depth += 1
        elif head == "end":
            depth -= 1
            if depth == 0:
                return j
    raise ValueError("块缺 {{ end }}")


def _split_else(body: list) -> tuple[list, list | None]:
    """块体按顶层 else 切成（真分支，假分支|None），嵌套不动。"""
    depth = 0
    for k, (kind, val) in enumerate(body):
        if kind != "tag":
            continue
        head = _head(val)
        if head in ("if", "for"):
            depth += 1
        elif head == "end":
            depth -= 1
        elif head == "else" and depth == 0:
            return body[:k], body[k + 1:]
    return body, None


def _seq(toks: list, i: int, scope: _Scope) -> tuple[str, int]:
    """顺序渲染，停在 end/else（不下消费）或文本末尾。"""
    out: list[str] = []
    while i < len(toks):
        kind, val = toks[i]
        if kind == "text":
            out.append(val)
            i += 1
            continue
        head = _head(val)
        if head in ("else", "end"):
            return "".join(out), i
        if head == "if":
            text, i = _if(toks, i, scope)
        elif head == "for":
            text, i = _for(toks, i, scope)
        else:
            text = str(_lookup(val, scope))
            i += 1
        out.append(text)
    return "".join(out), i


def _if(toks: list, i: int, scope: _Scope) -> tuple[str, int]:
    m = _IF.fullmatch(toks[i][1])
    if not m:
        raise ValueError(f"if 标签要条件变量: {toks[i][1]!r}")
    end = _match_end(toks, i + 1)
    true_b, false_b = _split_else(toks[i + 1:end])
    if _lookup(m.group(1), scope):
        return _seq(true_b, 0, scope)[0], end + 1
    return (_seq(false_b, 0, scope)[0] if false_b is not None else "",
            end + 1)


def _for(toks: list, i: int, scope: _Scope) -> tuple[str, int]:
    m = _FOR.fullmatch(toks[i][1])
    if not m:
        raise ValueError(f"for 标签要『for 变量 in 路径』: {toks[i][1]!r}")
    end = _match_end(toks, i + 1)
    body = toks[i + 1:end]
    items = _lookup(m.group(2), scope)
    if not isinstance(items, (list, tuple)):
        raise ValueError(f"for 目标须是 list/tuple: {m.group(2)}")
    pieces = []
    for item in items:
        scope.push({m.group(1): item})
        pieces.append(_seq(body, 0, scope)[0])
        scope.pop()
    return "".join(pieces), end + 1


def render(template: str, ctx: dict) -> str:
    """模板 + 上下文 → 文本；缺失变量 KeyError，标签失衡 ValueError。"""
    toks = _tokenize(template)
    out, i = _seq(toks, 0, _Scope(ctx))
    if i != len(toks):
        raise ValueError(f"多余的 {{{{ {toks[i][1]} }}}} 标签")
    return out


def _selftest() -> None:
    # 变量：带空格/不带/点路径/数字转字符串
    assert render("Hello {{ name }}!", {"name": "世界"}) == "Hello 世界!"
    assert render("{{name}}", {"name": "x"}) == "x"
    assert render("{{ a.b.c }}", {"a": {"b": {"c": 3}}}) == "3"
    assert render("{{ n }}|{{ f }}", {"n": 7, "f": 0.5}) == "7|0.5"

    # if/else 两分支（Python 真值：0/空串/None 为假）
    t = "{{ if ok }}是{{ else }}否{{ end }}"
    assert render(t, {"ok": True}) == "是"
    assert render(t, {"ok": 0}) == "否"
    assert render("{{ if ok }}是{{ end }}", {"ok": ""}) == ""
    assert render("{{ if a.b }}深{{ end }}", {"a": {"b": [1]}}) == "深"

    # for：循环变量 + 点路径 + 空列表 + 作用域推还原
    assert render("{{ for u in users }}{{ u.name }},{{ end }}",
                  {"users": [{"name": "a"}, {"name": "b"}]}) == "a,b,"
    assert render("{{ for x in none }}X{{ end }}", {"none": []}) == ""
    assert render("{{ x }}{{ for x in xs }}{{ x }}{{ end }}{{ x }}",
                  {"x": "O", "xs": ["i"]}) == "OiO"

    # 嵌套：if 进 for、外层变量循环内可见
    assert render("{{ for x in xs }}{{ if x.hot }}!{{ end }}.{{ end }}",
                  {"xs": [{"hot": 1}, {"hot": 0}]}) == "!.."  # 每项尾一个点
    assert render("{{ for y in ys }}{{ g }}{{ y }}{{ end }}",
                  {"ys": [1, 2], "g": "G"}) == "G1G2"

    # 严格缺失：变量/中间环 KeyError 报路径
    for bad_t, bad_c in (("{{ nope }}", {}), ("{{ a.z }}", {"a": {}}),
                         ("{{ a.z }}", {})):
        try:
            render(bad_t, bad_c)
        except KeyError as e:
            assert "nope" in str(e) or "a.z" in str(e)
        else:
            raise AssertionError(f"{bad_t} 应报 KeyError")

    # 标签失衡 / for 目标非列表 / 未闭合花括号字面保留
    for bad in (lambda: render("{{ end }}", {}),
                lambda: render("{{ else }}", {}),
                lambda: render("{{ for x in s }}{{ end }}", {"s": "abc"}),
                lambda: render("{{ if }}y{{ end }}", {})):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("应报 ValueError")
    assert render("a {{ b", {"b": 1}) == "a {{ b"

    # JSON 上下文端到端（CLI 同路径）
    assert render("{{ for t in tags }}#{{ t }}{{ end }}",
                  json.loads('{"tags": ["ai", "llm"]}')) == "#ai#llm"

    print("selftest ok: 变量/点路径/if-else/for/嵌套/严格缺失/失衡/字面括号 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="迷你文本模板渲染")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--template", default=None, help="模板文本")
    ap.add_argument("--ctx", default="{}", help="JSON 上下文（默认 {}）")
    args = ap.parse_args()
    if args.selftest or args.template is None:
        _selftest()
        if args.template is None:
            return
    print(render(args.template, json.loads(args.ctx)), end="")


if __name__ == "__main__":
    main()
