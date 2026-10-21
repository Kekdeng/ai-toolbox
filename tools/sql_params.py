#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sql_params.py — SQL 参数化 vs 字符串拼接的对照演示（纯标准库，不连库）。

LLM Agent 替用户拼 SQL 是注入事故的高发场景：模型把用户输入直接 f-string
进语句，一个 `'; DROP TABLE --` 就是灾难。本工具不连任何数据库，只并排
展示两种写法产出的东西，并给出一个「用户输入是否泄漏进语句」的检测器——
**底线：值永远走参数位（?），语句里永远不出现用户原文**。

用法：
    python tools/sql_params.py --selftest
    python tools/sql_params.py --term "50%_off"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse


def like_escape(term: str, esc: str = "\\") -> str:
    """转义 LIKE 通配符（% _）与转义符本身，配合 ESCAPE 子句使用。"""
    out = term.replace(esc, esc + esc)
    out = out.replace("%", esc + "%").replace("_", esc + "_")
    return out


def build_concat_sql(table: str, column: str, term: str) -> str:
    """❌ 反面教材：用户输入直接 f-string 进语句。"""
    return f"SELECT * FROM {table} WHERE {column} LIKE '%{term}%'"


def build_param_sql(table: str, column: str,
                    term: str) -> tuple[str, list[str]]:
    """✅ 正确姿势：语句只有占位符，值（含转义后的 LIKE 通配）走参数。"""
    sql = f"SELECT * FROM {table} WHERE {column} LIKE ? ESCAPE '\\'"
    return sql, [f"%{like_escape(term)}%"]


def leaks_user_input(sql: str, user_input: str) -> bool:
    """检测用户原文是否出现在语句里（拼接写法的特征）。"""
    return bool(user_input) and user_input in sql


def _selftest() -> None:
    payload = "'; DROP TABLE users; --"

    # 拼接版：payload 原文进语句 = 注入成立
    bad = build_concat_sql("users", "name", payload)
    assert "DROP TABLE" in bad
    assert leaks_user_input(bad, payload)

    # 参数化版：语句里没有 payload，值在参数里
    good_sql, params = build_param_sql("users", "name", payload)
    assert "DROP" not in good_sql and "';" not in good_sql
    assert params == ["%" + payload + "%"]
    assert not leaks_user_input(good_sql, payload)

    # LIKE 通配符：拼接版被用户输入注入通配（模板两个 % + 用户一个 %）
    assert build_concat_sql("t", "c", "%") == "SELECT * FROM t WHERE c LIKE '%%%'"
    sql2, params2 = build_param_sql("t", "c", "50%_off")
    assert params2 == ["%50\\%\\_off%"], params2
    assert "ESCAPE" in sql2
    assert like_escape("a\\b") == "a\\\\b"          # 转义符自身先转义

    # 空输入不算泄漏
    assert not leaks_user_input(good_sql, "")

    print("selftest ok: 拼接注入成立 / 参数化隔离 / LIKE 转义 / 检测器 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="SQL 参数化 vs 拼接对照")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--term", default=None, help="模拟的用户搜索词")
    ap.add_argument("--table", default="users")
    ap.add_argument("--column", default="name")
    args = ap.parse_args()
    if args.selftest or args.term is None:
        _selftest()
        if args.term is None:
            return
    bad = build_concat_sql(args.table, args.column, args.term)
    good, params = build_param_sql(args.table, args.column, args.term)
    print(f"❌ 拼接（注入风险: {leaks_user_input(bad, args.term)}）:\n  {bad}")
    print("✅ 参数化（语句/参数分离）:")
    print(f"  {good}\n  params = {params}")


if __name__ == "__main__":
    main()
