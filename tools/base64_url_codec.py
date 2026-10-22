#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""base64_url_codec.py — Base64 / percent-encoding 编解码（严格校验）。

对接 LLM/HTTP API 的高频编解码：JWT 的三段是 base64url，多模态消息里的
图片音频走 data URL，回调与 query 参数要 percent-encoding。本工具收拢
Base64 的标准/URL-safe/无填充变体，并做**严格校验解码**——字母表外字符、
错误填充、非规范编码（末尾填充位非零）一律拒绝，而不是悄悄解出错字节。

用法：
    python tools/base64_url_codec.py --selftest
    python tools/base64_url_codec.py --encode "hello"
    python tools/base64_url_codec.py --decode "aGVsbG8=" --urlsafe

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
import base64
import string
from urllib.parse import quote, unquote, unquote_plus

_STD_ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits + "+/"
_URL_ALPHABET = _STD_ALPHABET[:-2] + "-_"


def b64_encode(data: bytes, urlsafe: bool = False, pad: bool = True) -> str:
    """编码；urlsafe 用 -_ 替代 +/（JWT 就是它），pad=False 去掉尾部 =。"""
    enc = base64.urlsafe_b64encode if urlsafe else base64.b64encode
    out = enc(data).decode("ascii")
    return out if pad else out.rstrip("=")


def b64_decode(s: str, urlsafe: bool | None = None) -> bytes:
    """严格校验解码；urlsafe=None 时按是否含 -_ 自动判断。

    拒绝：字母表外字符、长度不是 4 的倍数（补齐后）、内嵌 =、
    非规范编码（如 "Zh=="——标准解码器会悄悄返回错字节 b'f'）。
    """
    if urlsafe is None:
        urlsafe = ("-" in s) or ("_" in s)
    allowed = _URL_ALPHABET if urlsafe else _STD_ALPHABET
    s = s.strip()
    if not all(c in allowed or c == "=" for c in s):
        raise ValueError(f"非法 base64 字符: {s!r}")
    core = s.rstrip("=")
    pad = len(s) - len(core)
    # 1 字符组只有 6 bit < 1 字节，不可能合法；带了 = 就必须补齐整组
    if "=" in core or pad > 2 or len(core) % 4 == 1:
        raise ValueError(f"填充错误: {s!r}")
    if pad and (len(core) + pad) % 4:
        raise ValueError(f"填充错误: {s!r}")
    normalized = core + "=" * ((-len(core)) % 4)
    wire = normalized.replace("-", "+").replace("_", "/") if urlsafe else normalized
    out = base64.b64decode(wire, validate=True)
    if b64_encode(out, urlsafe=urlsafe) != normalized:
        raise ValueError(f"非规范编码（填充位非零）: {s!r}")
    return out


def percent_encode(s: str, safe: str = "") -> str:
    """percent-encoding；safe 中的字符不转义（如路径分隔符 /）。"""
    return quote(s, safe=safe)


def percent_decode(s: str, plus_as_space: bool = False) -> str:
    """解码；query 串里的 + 要当空格请开 plus_as_space（表单编码惯例）。"""
    return unquote_plus(s) if plus_as_space else unquote(s)


def _selftest() -> None:
    # RFC 4648 测试向量
    vectors = [("", ""), ("f", "Zg=="), ("fo", "Zm8="), ("foo", "Zm9v"),
               ("foob", "Zm9vYg=="), ("fooba", "Zm9vYmE="), ("foobar", "Zm9vYmFy")]
    for raw, enc in vectors:
        assert b64_encode(raw.encode()) == enc, (raw, enc)
        assert b64_decode(enc) == raw.encode(), enc

    # urlsafe 变体与无填充
    assert b64_encode(b"\xfb\xff") == "+/8="
    assert b64_encode(b"\xfb\xff", urlsafe=True) == "-_8="
    assert b64_decode("-_8=") == b"\xfb\xff"
    assert b64_encode(b"hello", pad=False) == "aGVsbG8"
    assert b64_decode("aGVsbG8") == b"hello"            # 缺填充自动补齐
    assert b64_decode("aGVsbG8=", urlsafe=False) == b"hello"

    # 严格校验：非法字符 / len%4==1 的不可能长度 / 内嵌 = / 非规范填充位
    for bad in ("a!bc", "a", "abcde", "Zg=", "Zh==", "Zm9=", "a=b"):
        try:
            b64_decode(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝 {bad!r}")

    # percent-encoding
    assert percent_encode("a b/c") == "a%20b%2Fc"
    assert percent_encode("a b/c", safe="/") == "a%20b/c"
    assert percent_decode("a%20b%2Fc") == "a b/c"
    assert percent_decode("q=%E4%B8%AD") == "q=中"
    assert percent_decode("a+b", plus_as_space=True) == "a b"
    assert percent_decode("a+b") == "a+b"               # 默认不动 +

    print("selftest ok: RFC4648 向量/urlsafe/无填充/严格校验/percent 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="Base64 / percent-encoding 编解码")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    ap.add_argument("--encode", default=None, help="编码该字符串（utf-8）")
    ap.add_argument("--decode", default=None, help="解码该 base64 串")
    ap.add_argument("--quote", default=None, help="percent-encode 该字符串")
    ap.add_argument("--unquote", default=None, help="percent-decode 该字符串")
    ap.add_argument("--urlsafe", action="store_true", help="URL-safe 变体（-_）")
    ap.add_argument("--no-pad", action="store_true", help="编码时去掉尾部 =")
    args = ap.parse_args()
    given = [v for v in (args.encode, args.decode, args.quote, args.unquote)
             if v is not None]
    if args.selftest or not given:
        _selftest()
        if not given:
            return
    if args.encode is not None:
        print(b64_encode(args.encode.encode(), args.urlsafe, not args.no_pad))
    if args.decode is not None:
        print(b64_decode(args.decode, urlsafe=True if args.urlsafe else None))
    if args.quote is not None:
        print(percent_encode(args.quote))
    if args.unquote is not None:
        print(percent_decode(args.unquote, plus_as_space=args.urlsafe))


if __name__ == "__main__":
    main()
