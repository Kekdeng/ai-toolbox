#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""json_schema_mini.py — JSON Schema 最小子集校验：递归 + 错误路径。

LLM 结构化输出的「格式验收」用不上完整 JSON Schema（那是个大规范），
日常九成校验就这几个关键字：type / required / properties / items /
enum / minimum·maximum（数值）/ minLength·maxLength（字符串）。
本工具递归校验并给出 JSONPath 风格错误路径（$.user.tags[1]），
**返回全部问题而不是首错即停**——喂给模型重试时一次说清所有毛病。

未实现的 schema 关键字（如 pattern、oneOf）忽略不报——校验器只对
自己认识的部分负责，这是最小实现的诚实边界。

用法：
    python tools/json_schema_mini.py --selftest
    python tools/json_schema_mini.py --schema s.json --doc d.json

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import json

_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict, "array": list, "string": str,
    "number": (int, float), "integer": int, "boolean": bool,
    "null": type(None),
}


def type_name(value: object) -> str:
    """JSON 视角的类型名（bool 在 JSON 里不是数字，优先于 int 判断）。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _type_ok(value: object, t: str) -> bool:
    py = _TYPES.get(t)
    if py is None:
        raise ValueError(f"不支持的 schema 类型 {t!r}")
    if t in ("number", "integer") and isinstance(value, bool):
        return False        # Python 的 bool 是 int 子类，JSON 语义里不是
    return isinstance(value, py)


def validate(value: object, schema: dict, path: str = "$") -> list[str]:
    """按 schema 校验，返回问题列表（空列表 = 通过）。"""
    errs: list[str] = []
    t = schema.get("type")
    if t is not None and not _type_ok(value, t):
        return [f"{path}: 期望 {t}，实为 {type_name(value)}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} 不在枚举 {schema['enum']!r}")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}: 缺少必填字段 {k!r}")
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                errs += validate(value[k], sub, f"{path}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errs += validate(item, schema["items"], f"{path}[{i}]")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(f"{path}: 长度 {len(value)} 小于下限 {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{path}: 长度 {len(value)} 大于上限 {schema['maxLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: {value} 小于下限 {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: {value} 大于上限 {schema['maximum']}")
    return errs


SCHEMA_EXAMPLE = {
    "type": "object",
    "required": ["id", "tags"],
    "properties": {
        "id": {"type": "integer", "minimum": 1},
        "name": {"type": "string", "minLength": 2, "maxLength": 8},
        "role": {"type": "string", "enum": ["user", "admin"]},
        "tags": {"type": "array", "items": {"type": "string", "minLength": 2}},
    },
}


def _selftest() -> None:
    # 合法文档：零问题
    assert validate({"id": 1, "tags": ["a1", "ok"]}, SCHEMA_EXAMPLE) == []

    # 多错齐报 + 路径精确到元素
    errs = validate({"id": 0, "tags": ["x", 3, "good"]}, SCHEMA_EXAMPLE)
    joined = "\n".join(errs)
    assert len(errs) == 3, errs
    assert "$.id: 0 小于下限 1" in errs
    assert "$.tags[0]: 长度 1 小于下限 2" in errs
    assert "$.tags[1]: 期望 string，实为 integer" in errs
    assert "$.tags[2]" not in joined                       # 第 3 个没问题

    # 缺必填字段
    assert validate({"id": 1}, SCHEMA_EXAMPLE) == ["$: 缺少必填字段 'tags'"]

    # bool 不是 integer（Python 子类陷阱）；1.5 不是 integer；2.0 是 number
    assert validate(True, {"type": "integer"}) == ["$: 期望 integer，实为 boolean"]
    assert validate(True, {"type": "boolean"}) == []
    assert validate(1.5, {"type": "integer"}) == ["$: 期望 integer，实为 number"]
    assert validate(2.0, {"type": "number"}) == []

    # enum / maxLength / 未知类型关键字报错
    assert validate("guest", {"enum": ["user", "admin"]}) == [
        "$: 'guest' 不在枚举 ['user', 'admin']"]
    assert validate("abcdefghi", {"type": "string", "maxLength": 8}) == [
        "$: 长度 9 大于上限 8"]
    try:
        validate(1, {"type": "float"})
    except ValueError as e:
        assert "float" in str(e)
    else:
        raise AssertionError("未知类型应报错")

    print("selftest ok: 合法文档/多错齐报/必填/bool 陷阱/enum/长度/未知类型 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="JSON Schema 最小子集校验")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--schema", default=None, help="schema JSON 文件")
    ap.add_argument("--doc", default=None, help="待校验 JSON 文件")
    args = ap.parse_args()
    if args.selftest or not (args.schema and args.doc):
        _selftest()
        if not (args.schema and args.doc):
            return
    with open(args.schema, encoding="utf-8") as f:
        schema = json.load(f)
    with open(args.doc, encoding="utf-8") as f:
        doc = json.load(f)
    errs = validate(doc, schema)
    if errs:
        print(f"❌ {len(errs)} 个问题:")
        for e in errs:
            print(f"  {e}")
    else:
        print("✅ 校验通过")


if __name__ == "__main__":
    main()
