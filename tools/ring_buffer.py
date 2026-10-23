#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ring_buffer.py — 固定容量环形缓冲：满覆盖最旧、丢弃可观测。

流式场景的那块小内存：只关心最近 N 条（告警窗口、日志尾巴、
重放缓冲）。预分配定长数组 + 头下标环绕，push/pop 均 O(1)，
零搬运：

- 满 `push` 覆盖最旧并**返回被覆盖者**（要送上游审计就接住），
  `dropped` 累计丢弃数——静默丢数据是 bug 之源，这里可观测；
- `pop` 出最旧并腾位（覆盖式用法则从不 pop）；
- 迭代 oldest → newest，与 `to_list` 同序。

用法：
    python tools/ring_buffer.py --selftest

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
from collections.abc import Iterator


class RingBuffer:
    """定容 FIFO，满时覆盖最旧。"""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"容量须 ≥ 1: {capacity}")
        self.capacity = capacity
        self.dropped = 0
        self._buf: list = [None] * capacity
        self._head = 0          # 最老元素下标
        self._count = 0

    def push(self, item) -> object:
        """入队；满则覆盖最旧并返回它，未满返回 None。"""
        if self._count < self.capacity:
            self._buf[(self._head + self._count) % self.capacity] = item
            self._count += 1
            return None
        evicted = self._buf[self._head]
        self._buf[self._head] = item
        self._head = (self._head + 1) % self.capacity
        self.dropped += 1
        return evicted

    def pop(self):
        """出最旧；空则 IndexError。"""
        if self._count == 0:
            raise IndexError("空缓冲")
        item = self._buf[self._head]
        self._buf[self._head] = None
        self._head = (self._head + 1) % self.capacity
        self._count -= 1
        return item

    def peek(self):
        """看最旧不出队；空则 IndexError。"""
        if self._count == 0:
            raise IndexError("空缓冲")
        return self._buf[self._head]

    def __len__(self) -> int:
        return self._count

    def __iter__(self) -> Iterator:
        for i in range(self._count):
            yield self._buf[(self._head + i) % self.capacity]

    def to_list(self) -> list:
        """oldest → newest 快照。"""
        return list(self)


def _selftest() -> None:
    # 基本：进满、覆盖最旧并返回被覆盖者、丢弃计数
    rb = RingBuffer(3)
    assert rb.push(1) is None and rb.push(2) is None and rb.push(3) is None
    assert rb.to_list() == [1, 2, 3] and len(rb) == 3 and rb.dropped == 0
    assert rb.push(4) == 1                      # 覆盖 1，返回被覆盖者
    assert rb.to_list() == [2, 3, 4] and rb.dropped == 1

    # 混合 pop 腾位后不再丢；再满继续覆盖
    assert rb.pop() == 2
    assert rb.to_list() == [3, 4]
    assert rb.push(5) is None                   # 腾过位，未满
    assert rb.to_list() == [3, 4, 5]
    assert rb.push(6) == 3                      # 又满，覆盖 3
    assert rb.to_list() == [4, 5, 6] and rb.dropped == 2

    # peek 不出队
    rb2 = RingBuffer(2)
    rb2.push("a")
    rb2.push("b")
    assert rb2.peek() == "a" and len(rb2) == 2

    # 容量 1 的极端环绕
    rb3 = RingBuffer(1)
    rb3.push("a")
    assert rb3.push("b") == "a"
    assert rb3.to_list() == ["b"] and rb3.dropped == 1

    # 空：迭代 / to_list / pop / peek
    rb4 = RingBuffer(2)
    assert rb4.to_list() == [] and list(rb4) == []
    for call in (rb4.pop, rb4.peek):
        try:
            call()
        except IndexError:
            pass
        else:
            raise AssertionError("空缓冲应 IndexError")
    try:
        RingBuffer(0)
    except ValueError:
        pass
    else:
        raise AssertionError("容量 0 应报错")

    # 大环绕链：容量 5 进 12 个，丢 7 个，存活 8..12
    rb5 = RingBuffer(5)
    dropped = [rb5.push(i) for i in range(12)]
    assert rb5.dropped == 7
    assert [d for d in dropped if d is not None] == list(range(7))
    assert rb5.to_list() == [7, 8, 9, 10, 11]

    print("selftest ok: 覆盖返回/丢弃计数/pop腾位/容量1/空态/大环绕 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="固定容量环形缓冲")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
