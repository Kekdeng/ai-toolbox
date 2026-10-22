#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""csv_json_convert.py — CSV ↔ JSON/JSONL 互转：类型推断 + LLM 喂数据落表。

把表格数据喂给模型、或把模型产出的记录落成表格，是 AI 应用最常见的
两条数据通道。本工具做三件事：
- CSV → 记录列表：单元格做类型推断（int/float/bool/null/字符串）；
- 记录列表 → CSV：嵌套值（dict/list）JSON 序列化进单元格，None/布尔归一；
- JSONL 互转：LLM 训练/评测数据的事实标准，逐行解析、坏行报行号。

用法：
    python tools/csv_json_convert.py --selftest
    python tools/csv_json_convert.py --csv2json data.csv
    python tools/csv_json_convert.py --json2csv records.json

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re

_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?(?:\d+\.\d+|\.\d+|\d+(?:\.\d+)?[eE][+-]?\d+)$")


def infer(cell: str | None) -> object:
    """单元格类型推断：空→None，true/false→bool，整数/浮点→数值。

    规整只用剥过空白的纯数字/布尔；普通字符串保留原样（含空白）。
    """
    if cell is None or cell == "":
        return None
    s = cell.strip()
    if s == "":
        return None
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if _INT_RE.match(s):
        return int(s)
    if _FLOAT_RE.match(s):
        return float(s)
    return cell


def csv_to_records(text: str, typed: bool = True) -> list[dict]:
    """CSV 文本 → 记录列表（首行为表头；typed=False 全部保留字符串）。"""
    rows = [dict(r) for r in csv.DictReader(io.StringIO(text))]
    if typed:
        rows = [{k: infer(v) for k, v in r.items()} for r in rows]
    return rows


def _cell(v: object) -> str:
    """值 → 单元格：None→空串，bool→true/false，dict/list→JSON。"""
    if v is None:
        return ""
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def records_to_csv(records: list[dict]) -> str:
    """记录列表 → CSV 文本；表头 = 各记录键的首次出现顺序。

    含逗号/引号/换行的单元格由 csv 模块按 RFC 4180 转义，往返无损。
    """
    header: list[str] = []
    for r in records:
        for k in r:
            if k not in header:
                header.append(k)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for r in records:
        writer.writerow([_cell(r.get(k)) for k in header])
    return buf.getvalue()


def to_jsonl(records: list[dict]) -> str:
    """记录列表 → JSONL 文本（一行一条，ensure_ascii=False）。"""
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def from_jsonl(text: str) -> list[dict]:
    """JSONL → 记录列表；坏行报 ValueError 带行号，空行跳过。"""
    out: list[dict] = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"第 {i} 行不是合法 JSON: {e}") from e
    return out


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _selftest() -> None:
    csv1 = "id,active,score\n1,true,3.5\n2,false,\n"
    recs = csv_to_records(csv1)
    assert recs == [
        {"id": 1, "active": True, "score": 3.5},
        {"id": 2, "active": False, "score": None},
    ], recs
    assert csv_to_records(csv1, typed=False)[0] == {
        "id": "1", "active": "true", "score": "3.5"}

    # 往返：CSV → 记录 → CSV → 记录，等值
    assert csv_to_records(records_to_csv(recs)) == recs

    # 键并集 + 缺失键补空串
    assert records_to_csv([{"a": 1}, {"b": 2}]) == "a,b\n1,\n,2\n"

    # 逗号/嵌套：csv 转义 + 嵌套值走 JSON 单元格
    recs2 = [{"name": "张三, Jr", "tags": ["a", "b"], "meta": {"k": 1}}]
    csv2 = records_to_csv(recs2)
    back = csv_to_records(csv2, typed=False)[0]
    assert back["name"] == "张三, Jr", back
    assert json.loads(back["tags"]) == ["a", "b"]
    assert json.loads(back["meta"]) == {"k": 1}

    # 短行：缺失单元格 → None
    assert csv_to_records("a,b\n1\n") == [{"a": 1, "b": None}]

    # 空输入
    assert csv_to_records("") == []

    # JSONL 往返 + 坏行报行号 + 空行跳过
    jl = to_jsonl([{"id": 1, "t": "中文"}, {"id": 2}])
    assert from_jsonl(jl) == [{"id": 1, "t": "中文"}, {"id": 2}]
    assert from_jsonl('{"ok": 1}\n\n') == [{"ok": 1}]
    try:
        from_jsonl('{"ok": 1}\nnot json\n')
    except ValueError as e:
        assert "第 2 行" in str(e)
    else:
        raise AssertionError("坏行应报错")

    print("selftest ok: 类型推断/往返/键并集/嵌套 JSON 单元格/JSONL 行号 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="CSV ↔ JSON/JSONL 互转")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--csv2json", default=None, help="CSV 文件 → JSON 数组")
    ap.add_argument("--json2csv", default=None, help="JSON 数组文件 → CSV")
    ap.add_argument("--csv2jsonl", default=None, help="CSV 文件 → JSONL")
    ap.add_argument("--jsonl2csv", default=None, help="JSONL 文件 → CSV")
    ap.add_argument("--no-infer", action="store_true", help="不做类型推断")
    args = ap.parse_args()
    given = [v for v in (args.csv2json, args.json2csv, args.csv2jsonl,
                         args.jsonl2csv) if v is not None]
    if args.selftest or not given:
        _selftest()
        if not given:
            return
    typed = not args.no_infer
    if args.csv2json is not None:
        print(json.dumps(csv_to_records(_read(args.csv2json), typed),
                         ensure_ascii=False, indent=2))
    if args.csv2jsonl is not None:
        print(to_jsonl(csv_to_records(_read(args.csv2jsonl), typed)), end="")
    if args.json2csv is not None:
        print(records_to_csv(json.loads(_read(args.json2csv))), end="")
    if args.jsonl2csv is not None:
        print(records_to_csv(from_jsonl(_read(args.jsonl2csv))), end="")


if __name__ == "__main__":
    main()
