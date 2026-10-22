#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""url_ops.py — URL 工具箱：解析 / 查询参数增删改 / 相对链接合并。

拼 URL、改 query、剥域名是 Agent 和爬虫脚本的高频动作，散着写
容易踩坑（编码、重复键、fragment 丢失）。这里给一套保序保重复键
的完整口径：

- parse：六段拆解 + params 保序保重复（parse_qsl，%XX 与 + 解码）；
- set_params：同名键 dict 语义整体替换、新键追加、remove 全删，
  空白值（a=）保持，fragment 不丢，重组时统一 percent 编码；
- join：相对链接按 RFC 3986 合并（urljoin，绝对 URL 直通）；
- domain：主机名小写去端口；build：从部件拼回完整 URL。

用法：
    python tools/url_ops.py --selftest
    python tools/url_ops.py --url "https://h/p?x=1" --set page=2 --show

依赖：无（Python 3.10+，仅标准库 urllib.parse）。
"""
from __future__ import annotations

import argparse
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


def parse(url: str) -> dict:
    """URL → 六段 dict；params 保序保重复键，值已解码。"""
    s = urlsplit(url)
    return {"scheme": s.scheme, "netloc": s.netloc, "path": s.path,
            "query": s.query, "fragment": s.fragment,
            "params": parse_qsl(s.query, keep_blank_values=True)}


def set_params(url: str, updates: dict | None = None,
               remove: list[str] | None = None) -> str:
    """改 query 参数：updates 同名键整体替换并追加到尾部，remove 全删。"""
    s = urlsplit(url)
    params = parse_qsl(s.query, keep_blank_values=True)
    drop = set(remove or [])
    params = [(k, v) for k, v in params if k not in drop]
    for k, v in (updates or {}).items():
        params = [(kk, vv) for kk, vv in params if kk != k]
        params.append((k, str(v)))
    return urlunsplit((s.scheme, s.netloc, s.path, urlencode(params),
                       s.fragment))


def join(base: str, rel: str) -> str:
    """相对链接按 RFC 3986 合并到 base；rel 为绝对 URL 时直通。"""
    return urljoin(base, rel)


def domain(url: str) -> str:
    """主机名：小写、去端口；无 netloc（如 mailto:）→ 空串。"""
    return urlsplit(url).hostname or ""


def build(scheme: str, netloc: str, path: str = "", params=None,
          fragment: str = "") -> str:
    """部件 → 完整 URL；params 为键值对列表（保序保重复）或 dict。"""
    if params is None:
        params = []
    if hasattr(params, "items"):
        params = list(params.items())
    query = urlencode(params)
    return urlunsplit((scheme, netloc, path, query, fragment))


def _selftest() -> None:
    u = "https://Example.com:8443/a/b?x=1&y=2&x=3#frag"

    # parse：六段拆解，重复键保序
    p = parse(u)
    assert p["scheme"] == "https" and p["netloc"] == "Example.com:8443"
    assert p["path"] == "/a/b" and p["fragment"] == "frag"
    assert p["params"] == [("x", "1"), ("y", "2"), ("x", "3")], p["params"]

    # domain：小写去端口；无 netloc → 空串
    assert domain(u) == "example.com"
    assert domain("http://LOCALHOST/") == "localhost"
    assert domain("mailto:a@b.c") == ""

    # set_params：同名键 dict 语义替换、remove 全删、fragment 不丢
    assert set_params(u, {"x": "9"}) == \
        "https://Example.com:8443/a/b?y=2&x=9#frag"
    assert set_params(u, remove=["x"]) == \
        "https://Example.com:8443/a/b?y=2#frag"
    assert set_params(u, remove=["x"], updates={"z": 1}) == \
        "https://Example.com:8443/a/b?y=2&z=1#frag"

    # 空白值保持；值统一 percent 编码，roundtrip 回原值
    assert set_params("https://h/p?a=", {"b": "2"}) == "https://h/p?a=&b=2"
    zh = set_params(u, {"z": "中文 x"})
    assert "z=%E4%B8%AD%E6%96%87+x" in zh, zh
    assert parse(zh)["params"][-1] == ("z", "中文 x")

    # join：相对合并按 RFC，绝对 URL 直通
    assert join("https://h/base/a", "../c") == "https://h/c"
    assert join("https://h/a", "https://o/x") == "https://o/x"
    assert join("https://h/a", "b") == "https://h/b"

    # build：部件拼回，parse 往返一致
    u2 = build("https", "h", "/p", [("a", "1"), ("b", "")], "f")
    assert u2 == "https://h/p?a=1&b=#f", u2
    p2 = parse(u2)
    assert p2["params"] == [("a", "1"), ("b", "")] and p2["fragment"] == "f"

    print("selftest ok: 六段拆解/重复键保序/增删改/domain/join/build 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="URL 解析/参数增删改/合并")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--url", default=None, help="目标 URL")
    ap.add_argument("--set", action="append", default=[], metavar="K=V",
                    help="追加/替换查询参数（可多次）")
    ap.add_argument("--remove", action="append", default=[], metavar="K",
                    help="删除查询参数（可多次）")
    ap.add_argument("--join", default=None, metavar="REL",
                    help="把相对链接合并到 --url")
    ap.add_argument("--show", action="store_true", help="打印解析结果")
    args = ap.parse_args()
    if args.selftest or args.url is None:
        _selftest()
        if args.url is None:
            return
    url = args.url
    if args.join:
        url = join(url, args.join)
    if args.set or args.remove:
        updates = dict(kv.split("=", 1) for kv in args.set)
        url = set_params(url, updates, args.remove)
    print(url)
    if args.show:
        for k, v in parse(url)["params"]:
            print(f"  {k} = {v}")


if __name__ == "__main__":
    main()
