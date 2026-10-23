#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""priority_queue.py — 稳定优先队列：手写二叉最小堆，同优先级 FIFO。

任务调度、Dijkstra、超时管理都要「优先级高的先走」。stdlib 的
heapq 是裸堆，稳定性要自己垫 (seq)，元素还得可比较才不炸。这里
把这两件事做掉：

- 手写二叉最小堆（sift_up / sift_down），堆序只比 (priority, seq)——
  同优先级按入队顺序 FIFO，**元素本身永不参与比较**（dict 当元素
  照样用）；
- `push(item, priority)` / `pop() -> (priority, item)` / `peek()`；
  `to_sorted_list()` 非破坏快照（heapq 没有的顺手件）。

用法：
    python tools/priority_queue.py --selftest

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse
from collections.abc import Iterator


class PriorityQueue:
    """最小堆优先队列；数值越小越先出，同优先级先入先出。"""

    def __init__(self) -> None:
        self._heap: list[tuple[float, int, object]] = []  # (优先级, 序号, 元素)
        self._seq = 0

    def push(self, item: object, priority: float = 0) -> None:
        self._seq += 1
        self._sift_up((priority, self._seq, item))

    def pop(self) -> tuple[float, object]:
        """出最小者 → (优先级, 元素)；空则 IndexError。"""
        if not self._heap:
            raise IndexError("优先队列为空")
        first = self._heap[0]
        last = self._heap.pop()
        if self._heap:
            self._heap[0] = last
            self._sift_down(0)
        return (first[0], first[2])

    def peek(self) -> tuple[float, object]:
        """看最小者不出队；空则 IndexError。"""
        if not self._heap:
            raise IndexError("优先队列为空")
        first = self._heap[0]
        return (first[0], first[2])

    def __len__(self) -> int:
        return len(self._heap)

    def __iter__(self) -> Iterator[tuple[float, object]]:
        """非破坏快照，出队序（按优先级+入队序）。"""
        return iter(self.to_sorted_list())

    def to_sorted_list(self) -> list[tuple[float, object]]:
        """全量快照按出队序排列，不改队列。"""
        return [(p, item) for p, _seq, item in sorted(self._heap)]

    # -- 堆内部：比较只看 (优先级, 序号)，元素不参与 --

    def _sift_up(self, node: tuple) -> None:
        a = self._heap
        a.append(node)
        i = len(a) - 1
        while i > 0:
            p = (i - 1) // 2
            if a[i][:2] < a[p][:2]:
                a[i], a[p] = a[p], a[i]
                i = p
            else:
                break

    def _sift_down(self, i: int) -> None:
        a = self._heap
        n = len(a)
        while True:
            left, right, m = 2 * i + 1, 2 * i + 2, i
            if left < n and a[left][:2] < a[m][:2]:
                m = left
            if right < n and a[right][:2] < a[m][:2]:
                m = right
            if m == i:
                return
            a[i], a[m] = a[m], a[i]
            i = m


def _selftest() -> None:
    # 基本次序 + 同优先级 FIFO
    pq = PriorityQueue()
    pq.push("a", 5)
    pq.push("b", 1)
    pq.push("c", 3)
    pq.push("d", 1)
    assert pq.peek() == (1, "b") and len(pq) == 4
    assert [pq.pop() for _ in range(4)] == [
        (1, "b"), (1, "d"), (3, "c"), (5, "a")]

    # 元素不可比较（dict）也照常工作
    pq2 = PriorityQueue()
    pq2.push({"k": 1}, 2)
    pq2.push({"k": 2}, 1)
    assert pq2.pop() == (1, {"k": 2})
    assert pq2.pop() == (2, {"k": 1})

    # 交错 push/pop
    pq3 = PriorityQueue()
    pq3.push("x1", 2)
    assert pq3.pop() == (2, "x1")
    pq3.push("x2", 1)
    pq3.push("x3", 3)
    assert pq3.pop() == (1, "x2")
    assert pq3.pop() == (3, "x3")

    # 负数/零/浮点优先级；to_sorted_list 非破坏
    pq4 = PriorityQueue()
    prios = [5, 1, 4, 1, 3, 2, 1, 0, 2, 0]
    for i, p in enumerate(prios):
        pq4.push(f"v{i}", p)
    expect = [(0, "v7"), (0, "v9"), (1, "v1"), (1, "v3"), (1, "v6"),
              (2, "v5"), (2, "v8"), (3, "v4"), (4, "v2"), (5, "v0")]
    assert pq4.to_sorted_list() == expect
    assert len(pq4) == 10                      # 快照不出队
    assert [pq4.pop() for _ in range(10)] == expect
    pq4.push("late", -1.5)
    assert pq4.pop() == (-1.5, "late")

    # 空：pop/peek IndexError，快照 []
    pq5 = PriorityQueue()
    assert pq5.to_sorted_list() == [] and list(pq5) == []
    for call in (pq5.pop, pq5.peek):
        try:
            call()
        except IndexError:
            pass
        else:
            raise AssertionError("空队列应 IndexError")

    print("selftest ok: 堆序/同优先级FIFO/不可比较元素/交错/非破坏快照/空态 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="稳定优先队列（手写最小堆）")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
