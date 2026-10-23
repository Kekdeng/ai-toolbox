#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""set_expr.py — 布尔查询表达式：AND / OR / NOT / 括号，词集求值。

过滤一万个文档时的那把小刀：`"(cat OR dog) AND NOT mouse"`。
递归下降三优先级（NOT > AND > OR，AND 可省略——相邻词即隐式
AND），关键字大小写不敏感、只认整词（`android` 不会被拆出 AND）。

词集口径：文档给 str 就按空白切词，给 set 就原样用——中英文都
是一个词一个 token，分词是上游的事。求值按布尔：原子 = 词在不在
文档里，NOT 取反、AND/OR 交并，命中 = 整式为真（空文档不含任何
词，「NOT cat」判命中——与检索直觉一致）。

用法：
    python tools/set_expr.py --selftest
    python tools/set_expr.py --expr "cat AND NOT dog" --doc "cat bird"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse


def _tokenize(expr: str) -> list[str]:
    """→ 词元流；关键字归一为大写，括号独立成元。"""
    toks: list[str] = []
    cur: list[str] = []
    for c in expr:
        if c in "()":
            if cur:
                toks.append("".join(cur))
                cur = []
            toks.append(c)
        elif c.isspace():
            if cur:
                toks.append("".join(cur))
                cur = []
        else:
            cur.append(c)
    if cur:
        toks.append("".join(cur))
    out = []
    for t in toks:
        up = t.upper()
        out.append(up if up in ("AND", "OR", "NOT") else t)
    return out


class _Parser:
    """递归下降：or → and → not → atom；每节点求值布尔。"""

    def __init__(self, toks: list[str], words: frozenset) -> None:
        self.toks = toks
        self.i = 0
        self.words = words

    def peek(self) -> str | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self) -> str:
        t = self.toks[self.i]
        self.i += 1
        return t

    def parse(self) -> bool:
        result = self.or_expr()
        if self.peek() is not None:
            raise ValueError(f"多余词元: {self.peek()!r}")
        return result

    def or_expr(self) -> bool:
        acc = self.and_expr()
        while self.peek() == "OR":
            self.take()
            acc = acc | self.and_expr()
        return acc

    def and_expr(self) -> bool:
        acc = self.not_expr()
        while True:
            nxt = self.peek()
            if nxt == "AND":
                self.take()
                acc = acc & self.not_expr()
            elif nxt is not None and nxt not in (")", "OR"):  # 隐式 AND
                acc = acc & self.not_expr()
            else:
                return acc

    def not_expr(self) -> bool:
        if self.peek() == "NOT":
            self.take()
            return not self.not_expr()
        return self.atom()

    def atom(self) -> bool:
        t = self.peek()
        if t is None:
            raise ValueError("表达式意外结束")
        if t == "(":
            self.take()
            inner = self.or_expr()
            if self.peek() != ")":
                raise ValueError("括号不闭合")
            self.take()
            return inner
        if t in (")", "AND", "OR"):
            raise ValueError(f"词元位置不对: {t!r}")
        return self.take() in self.words


def matches(expr: str, doc: set[str] | str) -> bool:
    """文档（词集或空白切词的文本）是否命中表达式。"""
    words = frozenset(doc.split()) if isinstance(doc, str) else frozenset(doc)
    return _Parser(_tokenize(expr), words).parse()


def _selftest() -> None:
    cat_dog = {"cat", "dog"}

    # 三种基本运算
    assert matches("cat AND dog", cat_dog)
    assert not matches("cat AND dog", {"cat"})
    assert matches("cat OR dog", {"cat"})
    assert not matches("cat OR dog", {"bird"})
    assert matches("NOT cat", {"dog"})
    assert not matches("NOT cat", cat_dog)          # 文档含 cat 即不命中
    assert matches("NOT cat", set())                # 空文档不含 cat → 命中

    # 优先级与括号：NOT > AND > OR
    assert matches("cat AND NOT dog", cat_dog) is False
    assert matches("cat OR NOT dog", {"bird"})       # NOT dog = {bird,cat}
    assert matches("cat OR dog AND bird", {"cat"})   # OR 最低：cat | (dog&bird)
    assert not matches("(cat OR dog) AND bird", {"cat"})
    assert matches("(cat OR dog) AND bird", {"cat", "bird"})

    # 隐式 AND、关键字大小写不敏感、整词不误拆
    assert matches("cat dog", cat_dog)
    assert matches("cat and dog", cat_dog)
    assert matches("cat oR dog", cat_dog)
    assert matches("android", {"android"})           # AND 不从词中拆
    assert not matches("cat AND dog", {"android"})

    # 中文词、集合直传
    assert matches("猫 AND 狗", {"猫", "狗", "鸟"})
    assert matches("猫", frozenset(["猫"]))

    # 报错：括号不闭合 / 悬空运算符 / 空表达式 / 多余闭括号
    for bad in ("(cat", "cat)", "cat AND", "AND cat", "", "NOT",
                "cat OR OR dog"):
        try:
            matches(bad, cat_dog)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 应报错")

    print("selftest ok: 三运算/优先级/括号/隐式AND/整词/中文/报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="布尔查询表达式（词集求值）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--expr", default=None, help="查询表达式")
    ap.add_argument("--doc", default=None, help="文档文本（空白切词）")
    args = ap.parse_args()
    if args.selftest or args.expr is None:
        _selftest()
        if args.expr is None:
            return
    hit = matches(args.expr, args.doc or "")
    print("命中" if hit else "未命中")


if __name__ == "__main__":
    main()
