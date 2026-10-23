#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xpath_mini.py — XPath 最小子集：/ 与 // 轴、通配、下标与属性谓词。

XML 抓取最常用的那几招（xml.etree.ElementTree 只认它自己的有限
语法，谓词支持更弱），这里自解析一个明确的子集：

- `/a/b` 逐层子节点；`//b` 后代轴；`*` 通配一层；首步按文档节点
  口径评估（根元素是文档的独子：`/catalog` 抓得到根，`//book`
  连根是 book 也算），后续后代轴取真后代（`.//` 语义）；
- 谓词挂在步上，可叠用：`[2]` 1 基下标、`[@k='v']` 属性等于、
  `[@k]` 属性存在——下标按「每个父节点各自的子序列」计，与
  XPath 每步谓词语义一致（`//book[1]` = 各自父下的第一本），
  越界给空列表；`[0]` 视同越界；
- 结果保持文档序；`text_of` 取文本的顺手封装。

路径里空段即后代轴（`a//b`），`a///b`、悬空 `//` 这类畸形明确
报错；未知标签给空列表（抓不到 ≠ 错）。标签名支持 CJK（首字符
非数字的 word 字符）。

用法：
    python tools/xpath_mini.py --selftest
    python tools/xpath_mini.py --xml doc.xml --path "//book[@id='2']/title"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET

_STEP = re.compile(
    r"(\*|[^\W\d][\w.-]*)((?:\[\d+\]|\[@[\w.-]+(?:='[^']*')?\])*)")
_PRED = re.compile(r"\[(\d+)\]|\[@([\w.-]+)(?:='([^']*)')?\]")


def _parse_path(path: str) -> list[tuple[bool, str, list[tuple]]]:
    """路径 → [(是否后代轴, 名/通配, 谓词列表)]；畸形明确报错。"""
    if not path:
        raise ValueError("路径为空")
    parts = path.split("/")
    if parts[0] == "":                    # 开头的绝对 /
        parts = parts[1:]
        if not parts:
            raise ValueError(f"路径畸形: {path!r}")
    steps: list[tuple[bool, str, list[tuple]]] = []
    i = 0
    while i < len(parts):
        seg = parts[i]
        if seg == "":                     # 空段 = 后代轴，作用于下一段
            if i + 1 >= len(parts) or parts[i + 1] == "":
                raise ValueError(f"路径畸形（连续空段）: {path!r}")
            nxt = parts[i + 1]
            m = _STEP.fullmatch(nxt)
            if not m:
                raise ValueError(f"步语法非法: {nxt!r}")
            steps.append((True, m.group(1), _preds(m.group(2))))
            i += 2
            continue
        m = _STEP.fullmatch(seg)
        if not m:
            raise ValueError(f"步语法非法: {seg!r}")
        steps.append((False, m.group(1), _preds(m.group(2))))
        i += 1
    return steps


def _preds(s: str) -> list[tuple]:
    """谓词串 → [("idx", n) | ("attr", k) | ("eq", k, v)]。"""
    out: list[tuple] = []
    pos = 0
    while pos < len(s):
        m = _PRED.match(s, pos)
        if not m:
            raise ValueError(f"谓词语法非法: {s!r}")
        if m.group(1) is not None:
            out.append(("idx", int(m.group(1))))
        elif m.group(3) is None:
            out.append(("attr", m.group(2)))
        else:
            out.append(("eq", m.group(2), m.group(3)))
        pos = m.end()
    return out


def _name_match(el: ET.Element, name: str) -> bool:
    return name == "*" or el.tag == name


def _apply_preds(els: list[ET.Element],
                 preds: list[tuple]) -> list[ET.Element]:
    """谓词作用于单个父节点下的候选序列（下标 1 基，越界/0 → 空）。"""
    for p in preds:
        if p[0] == "idx":
            if not 1 <= p[1] <= len(els):
                return []
            els = [els[p[1] - 1]]
        elif p[0] == "attr":
            els = [e for e in els if p[1] in e.attrib]
        else:
            els = [e for e in els
                   if e.attrib.get(p[1]) == p[2]]
    return els


def _select(els: list[ET.Element], desc: bool,
            name: str, preds: list[tuple]) -> list[ET.Element]:
    """常规步：子轴或真后代轴（.// 语义），谓词按每父节点的子序列施。"""
    out: list[ET.Element] = []
    for ctx in els:
        for n in (ctx.iter() if desc else (ctx,)):
            cand = [e for e in n if _name_match(e, name)]
            out.extend(_apply_preds(cand, preds))
    return out


def _select_first(root: ET.Element, desc: bool,
                  name: str, preds: list[tuple]) -> list[ET.Element]:
    """首步按文档节点口径：root 是文档的独子（/catalog 抓得到根）；
    后代轴再对全树每层孩子施谓词（//x = descendant-or-self/child）。"""
    out: list[ET.Element] = []
    if _name_match(root, name):
        out.extend(_apply_preds([root], preds))
    if desc:
        for n in root.iter():
            out.extend(_apply_preds(
                [e for e in n if _name_match(e, name)], preds))
    return out


def find_all(xml_text: str, path: str) -> list[ET.Element]:
    """XML 文本 + 子集路径 → 元素列表（文档序）。"""
    root = ET.fromstring(xml_text)
    order = {id(e): i for i, e in enumerate(root.iter())}
    steps = _parse_path(path)
    desc, name, preds = steps[0]
    context = _select_first(root, desc, name, preds)
    for desc, name, preds in steps[1:]:
        if not context:
            return []
        context = _select(context, desc, name, preds)
    if not context:
        return []
    context.sort(key=lambda e: order[id(e)])  # 文档序不变式
    return context


def text_of(el: ET.Element) -> str:
    """元素直接文本（strip 前后空白；不含子元素文本）。"""
    return (el.text or "").strip()


def _selftest() -> None:
    xml = ("""<catalog>
  <book id="1" lang="en"><title>A</title><price>30</price></book>
  <book id="2"><title>B</title><price>20</price><title>B2</title></book>
  <shelf><book id="3"><title>C</title></book></shelf>
</catalog>""")

    # / 逐层：子轴、按父计数的下标、文档序
    assert len(find_all(xml, "/catalog/book")) == 2
    assert text_of(find_all(xml, "/catalog/book[2]/title")[0]) == "B"
    assert text_of(find_all(xml, "/catalog/book/title")[0]) == "A"

    # // 后代轴：嵌套在 shelf 里的也算；下标按父各自计数（XPath 语义）
    assert len(find_all(xml, "//book")) == 3
    assert len(find_all(xml, "//title")) == 4         # 含书 2 的 B2
    assert [text_of(e) for e in find_all(xml, "//book[1]/title")] == ["A", "C"]
    assert len(find_all(xml, "/catalog/*")) == 3        # 两本 book + shelf
    assert len(find_all(xml, "//*")) == 11   # 根+3book+4title+2price+shelf
    assert find_all(xml, "//book[0]") == []             # 0 视同越界

    # 属性谓词：等于 / 存在；书 2 双 title
    assert text_of(find_all(xml, "//book[@id='3']/title")[0]) == "C"
    assert len(find_all(xml, "//book[@lang='en']")) == 1
    assert len(find_all(xml, "/catalog/book[@id]")) == 2
    got = [text_of(e) for e in find_all(xml, "//book[@id='2']/title")]
    assert got == ["B", "B2"], got

    # 叠加谓词：下标 + 属性；多级后代轴
    assert text_of(find_all(xml, "//book[@id='2']/title[2]")[0]) == "B2"
    assert len(find_all(xml, "//shelf//book")) == 1

    # 未知标签 / 下标越界 → 空列表；相对路径（无前导 /）等价绝对
    assert find_all(xml, "//magazine") == []
    assert find_all(xml, "/catalog/book[9]") == []
    assert [e.get("id") for e in find_all(xml, "catalog/book")] == ["1", "2"]

    # CJK 标签名
    xml_cn = "<库存><书 id='1'><价格>30</价格></书></库存>"
    assert text_of(find_all(xml_cn, "//书[@id='1']/价格")[0]) == "30"

    # 报错：空路径 / 裸斜杠 / 连续空段 / 坏步 / 坏谓词
    for bad in ("", "/", "///a", "a//", "a/[2]", "//b[@]", "//b[@x='y]"):
        try:
            find_all(xml, bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad!r} 应报错")

    print("selftest ok: 逐层/后代轴含根/按父下标/通配/属性谓词/叠加/文档序/CJK/报错 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="XPath 最小子集")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--xml", default=None, help="XML 文件路径")
    ap.add_argument("--path", default=None, help="子集路径")
    args = ap.parse_args()
    if args.selftest or (args.xml is None and args.path is None):
        _selftest()
        if args.xml is None and args.path is None:
            return
    with open(args.xml, encoding="utf-8") as f:
        xml = f.read()
    for el in find_all(xml, args.path or ""):
        print(ET.tostring(el, encoding="unicode"))


if __name__ == "__main__":
    main()
