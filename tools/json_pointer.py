#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""json_pointer.py — JSON Pointer（RFC 6901）：get / add / delete。

嵌套 JSON 的寻址标准：`/a/0/b` 一路走 dict 键和 list 下标。
三操作全按 RFC 6901 语义：

- get：逐 token 下钻；根指针是空串；`~1` 解成 `/`、`~0` 解成 `~`
  （顺序不可换）；数组下标禁前导零（"01" 非法，"0" 合法）；
- add：dict 键直接置；list 下标 0..len（==len 即尾部插入），
  `"-"` 是 RFC 惯例的 append；中间节点缺就造 dict（顺手糖，
  RFC 本要求容器已存在，工程上加它省事）；
- delete：父容器须存在、下标须在界内（list 删位移）；根不可删。

原地修改并返回文档本身；寻址失败（缺键/越界/穿标量）抛
ValueError 带完整指针路径。

用法：
    python tools/json_pointer.py --selftest
    python tools/json_pointer.py --doc '{"a": {"b": 1}}' --pointer /a/b
    python tools/json_pointer.py --doc '{"a": [1]}' --add /a/- '"x"'

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import json


def _decode(token: str) -> str:
    """~1 → / ，~0 → ~（先替 ~1 再替 ~0，顺序不可换）。"""
    return token.replace("~1", "/").replace("~0", "~")


def _encode(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"指针须以 / 开头或为空串: {pointer!r}")
    return [_decode(t) for t in pointer.split("/")[1:]]


def _descend(node, token: str, path: str):
    """走一步：dict 查键 / list 查无前导零下标；失败带完整路径。"""
    where = f"{path}/{_encode(token)}"
    if isinstance(node, dict):
        if token not in node:
            raise ValueError(f"键不存在: {where}")
        return node[token]
    if isinstance(node, list):
        if not token.isdigit():
            raise ValueError(f"数组下标非法: {where}")
        if token != str(int(token)):
            raise ValueError(f"数组下标禁前导零: {where}")
        i = int(token)
        if not 0 <= i < len(node):
            raise ValueError(f"下标越界: {where}")
        return node[i]
    raise ValueError(f"试图穿过标量: {where}")


def get(doc, pointer: str):
    """按指针取值；根指针（空串）取整个文档。"""
    node = doc
    path = ""
    for token in _tokens(pointer):
        node = _descend(node, token, path)
        path = f"{path}/{_encode(token)}"
    return node


def add(doc, pointer: str, value) -> object:
    """RFC add：dict 置键；list 插入（len 处=尾插，"-"=append）；
    中间缺 dict 自动创建。原地改并返回 doc。"""
    toks = _tokens(pointer)
    if not toks:
        return value                      # 根指针 = 整体替换
    node = doc
    path = ""
    for token in toks[:-1]:
        nxt = f"{path}/{_encode(token)}"
        if isinstance(node, dict) and token not in node:
            node[token] = {}              # 中间节点顺手造
        node = _descend(node, token, path)
        path = nxt
    last = toks[-1]
    where = f"{path}/{_encode(last)}"
    if isinstance(node, dict):
        node[last] = value
        return doc
    if isinstance(node, list):
        if last == "-":
            node.append(value)
            return doc
        if not last.isdigit():
            raise ValueError(f"数组下标非法: {where}")
        i = int(last)
        if last != str(i):
            raise ValueError(f"数组下标非法（禁前导零）: {where}")
        if not 0 <= i <= len(node):
            raise ValueError(f"插入位置越界（须 ≤ len）: {where}")
        node.insert(i, value)
        return doc
    raise ValueError(f"容器不是 dict/list: {where}")


def delete(doc, pointer: str) -> object:
    """RFC remove：父容器须在、目标须在；list 删后位移；根不可删。"""
    toks = _tokens(pointer)
    if not toks:
        raise ValueError("根不可删除")
    parent = get(doc, _encode_path(toks[:-1]))
    last = toks[-1]
    where = pointer
    if isinstance(parent, dict):
        if last not in parent:
            raise ValueError(f"键不存在: {where}")
        del parent[last]
        return doc
    if isinstance(parent, list):
        if not last.isdigit() or last != str(int(last)):
            raise ValueError(f"数组下标非法: {where}")
        i = int(last)
        if not 0 <= i < len(parent):
            raise ValueError(f"下标越界: {where}")
        parent.pop(i)
        return doc
    raise ValueError(f"容器不是 dict/list: {where}")


def _encode_path(toks: list[str]) -> str:
    return "".join(f"/{_encode(t)}" for t in toks)


def _selftest() -> None:
    # RFC 6901 §5 官方示例文档，全部向量逐一对齐
    doc = {"foo": ["bar", "baz"], "": 0, "a/b": 1, "c%d": 2, "e^f": 3,
           "g|h": 4, "i\\j": 5, 'k"l': 6, " ": 7, "m~n": 8}
    assert get(doc, "") == doc
    assert get(doc, "/foo") == ["bar", "baz"]
    assert get(doc, "/foo/0") == "bar"
    assert get(doc, "/") == 0
    assert get(doc, "/a~1b") == 1
    assert get(doc, "/c%d") == 2
    assert get(doc, "/e^f") == 3
    assert get(doc, "/g|h") == 4
    assert get(doc, "/i\\j") == 5
    assert get(doc, '/k"l') == 6
    assert get(doc, "/ ") == 7
    assert get(doc, "/m~0n") == 8

    # add：dict 置键 / 中间自动建 / 尾插 / "-" append / 根替换
    d = {"foo": ["bar"]}
    assert add(d, "/foo/-", "qux")["foo"] == ["bar", "qux"]
    assert add(d, "/foo/0", "first")["foo"] == ["first", "bar", "qux"]
    assert add(d, "/a/b/c", 1) == {"a": {"b": {"c": 1}},
                                   "foo": ["first", "bar", "qux"]}
    assert add(d, "", 9) == 9            # 根指针整体替换（返回新值）

    # delete：dict 键 / list 位移 / 根不可删
    d = {"foo": ["a", "b", "c"], "k": 1}
    assert delete(d, "/foo/0") == {"foo": ["b", "c"], "k": 1}
    assert delete(d, "/k") == {"foo": ["b", "c"]}
    for bad in (lambda: delete({}, ""), lambda: delete(d, "/nope"),
                lambda: delete(d, "/foo/9")):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    # get 失败：越界 / 前导零 / 穿标量 / 非法指针
    d = {"a": [0, {"b": 1}]}
    for ptr in ("/a/5", "/a/01", "/a/0/b/c", "a"):
        try:
            get(d, ptr)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{ptr} 应报错")

    # 往返：add 后 delete 回原状
    d = {"x": 1}
    add(d, "/y", [1, 2])
    add(d, "/y/0", 0)
    delete(d, "/y/0")
    assert delete(d, "/y") == {"x": 1}

    print("selftest ok: RFC6901 官方向量/add 语义/delete/自动建/往返/报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="JSON Pointer（RFC 6901）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--doc", default=None, help="JSON 文档文本")
    ap.add_argument("--pointer", default="", help="指针（默认根）")
    ap.add_argument("--add", default=None, metavar="PTR=JSON",
                    help="add: 指针=JSON 值")
    ap.add_argument("--delete", default=None, metavar="PTR",
                    help="delete: 指针")
    args = ap.parse_args()
    if args.selftest or args.doc is None:
        _selftest()
        if args.doc is None:
            return
    doc = json.loads(args.doc)
    if args.add:
        ptr, _, raw = args.add.partition("=")
        add(doc, ptr, json.loads(raw))
    if args.delete:
        delete(doc, args.delete)
    print(json.dumps(doc if args.add or args.delete
                     else get(doc, args.pointer),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
