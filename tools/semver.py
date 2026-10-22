#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""semver.py — 语义化版本（SemVer 2.0.0）：解析 / 比较 / 排序 / 约束。

模型 SDK、依赖锁文件、API 兼容性判断都绕不开版本号，而「1.10.0 和
1.9.0 谁大」「1.0.0-rc.1 算不算 ≥1.0.0」这类问题字符串比较必错。
本工具按 SemVer 2.0.0 规范实现：

- `主.次.修订[-先行版本][+构建元数据]`，构建元数据不参与优先级；
- 先行版本 < 正式版（1.0.0-alpha < 1.0.0）；
- 先行版本标识符逐个比较：数字按数值、字母按 ASCII、数字 < 字母、
  标识符更多者更大（1.0.0-alpha < 1.0.0-alpha.1）；
- satisfies_range：`>=1.2.0, <2.0.0` 逗号为 AND 的约束判断。

用法：
    python tools/semver.py --selftest
    python tools/semver.py --compare 1.10.0 1.9.0
    python tools/semver.py --check 1.5.2 --range ">=1.2.0,<2.0.0"

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import functools
import re

# SemVer 2.0.0 官方正则（核心部分照搬规范，分组：主/次/修订/先行/构建）
_SEMVER_RE = re.compile(
    r"^\s*(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\s*$"
)


def parse(version: str) -> tuple[int, int, int, tuple[str, ...], str]:
    """解析为（主, 次, 修订, 先行标识符元组, 构建元数据）；不合规范抛错。"""
    m = _SEMVER_RE.match(version)
    if m is None:
        raise ValueError(f"不是合法 SemVer: {version!r}")
    major, minor, patch, pre, build = m.groups()
    return (int(major), int(minor), int(patch),
            tuple(pre.split(".")) if pre else (), build or "")


def _pre_key(pre: tuple[str, ...]) -> tuple:
    """先行版本排序键：数字标识符 (0, n) 恒小于字母标识符 (1, s)。"""
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre)


def sort_key(version: str) -> tuple:
    """排序键；构建元数据不参与（规范规定）。无先行版用 (1,) 压过 (0,)。"""
    major, minor, patch, pre, _build = parse(version)
    return (major, minor, patch, 0, _pre_key(pre)) if pre else \
        (major, minor, patch, 1, ())


def compare(a: str, b: str) -> int:
    """a<b → -1；相等（含仅构建元数据不同）→ 0；a>b → 1。"""
    ka, kb = sort_key(a), sort_key(b)
    return -1 if ka < kb else (1 if ka > kb else 0)


def satisfies_range(version: str, range_: str) -> bool:
    """约束判断：逗号分隔为 AND，每个约束支持 >= <= > < == !=。"""
    for cond in range_.split(","):
        cond = cond.strip()
        for op in (">=", "<=", "==", "!=", ">", "<"):
            if cond.startswith(op):
                target = cond[len(op):]
                c = compare(version, target)
                ok = {">=": c >= 0, "<=": c <= 0, "==": c == 0,
                      "!=": c != 0, ">": c > 0, "<": c < 0}[op]
                break
        else:
            raise ValueError(f"约束缺比较符（形如 >=1.2.0）: {cond!r}")
        if not ok:
            return False
    return True


def _selftest() -> None:
    # 规范 11 条优先级示例全序
    order = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta",
             "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1",
             "1.0.0", "1.0.1", "1.1.0", "2.0.0"]
    assert sorted(order, key=sort_key) == order
    assert sorted(order[::-1], key=sort_key) == order        # 输入序无关
    for a, b in zip(order, order[1:]):
        assert compare(a, b) == -1

    # 数字按数值比（字符串比较的经典翻车点）、构建元数据不影响优先级
    assert compare("1.10.0", "1.9.0") == 1
    assert compare("1.0.0+build.1", "1.0.0+build.999") == 0
    assert compare("1.0.0-alpha", "1.0.0-alpha.1") == -1      # 少标识符更小

    # 解析分组与宽松空白
    assert parse(" 1.2.3-beta.2+exp ") == (1, 2, 3, ("beta", "2"), "exp")

    # 约束：正式版命中；先行版本 < 同号正式版所以不命中
    assert satisfies_range("1.5.2", ">=1.2.0,<2.0.0")
    assert not satisfies_range("2.1.0", ">=1.2.0,<2.0.0")
    assert not satisfies_range("1.2.0-alpha", ">=1.2.0")
    assert satisfies_range("1.2.1", ">=1.2.0, !=1.2.3, <2.0.0")

    # 规范禁止的写法：位数不足、前导零、空标识符
    for bad in ("1.0", "01.0.0", "1.0.0-", "1.0.0+", "1.0.0-01", "v1.0.0"):
        try:
            parse(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad!r}")

    print("selftest ok: 规范全序/数值比较/构建元数据/约束/先行版<正式/坏输入 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="SemVer 2.0.0 解析/比较/约束")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"),
                    help="比较两个版本")
    ap.add_argument("--sort", nargs="+", metavar="V", help="版本升序排序")
    ap.add_argument("--check", metavar="V", help="校验该版本是否满足约束")
    ap.add_argument("--range", default=None, help='约束串，如 ">=1.2.0,<2.0.0"')
    args = ap.parse_args()
    if args.selftest or not (args.compare or args.sort
                             or (args.check and args.range)):
        _selftest()
        if not (args.compare or args.sort or (args.check and args.range)):
            return
    if args.compare:
        c = compare(*args.compare)
        rel = "<" if c < 0 else (">" if c > 0 else "==")
        print(f"{args.compare[0]} {rel} {args.compare[1]}")
    if args.sort:
        for v in sorted(args.sort, key=sort_key):
            print(v)
    if args.check and args.range:
        print("✅ 满足" if satisfies_range(args.check, args.range) else "❌ 不满足")


if __name__ == "__main__":
    main()
