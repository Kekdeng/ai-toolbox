#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""state_machine.py — 简单状态机引擎：转移表 + 确定性 trace。

协议解析、订单流转、审批流这些「状态少、事件明确」的模型，一张
转移表就是全部逻辑：transitions[state][event] = next_state。

- 构造期全量校验：初始状态必须在表内、每个转移目标也必须是已声明
  状态（含空 dict 的死端状态）——表写错当场炸，不留到运行时；
- fire 单步：非法事件报错并**列出当前状态的合法事件**（调试友好）；
- run 跑事件序列，返回每步后的状态 trace（含初始态）——回放、
  断言、画图都从 trace 出发；
- can/events 查询给守卫逻辑用。

用法：
    python tools/state_machine.py --selftest

依赖：无（Python 3.10+）。
"""
from __future__ import annotations

import argparse


class StateMachine:
    """确定性有限状态机：转移表驱动，单线程使用。"""

    def __init__(self, transitions: dict[str, dict[str, str]],
                 initial: str) -> None:
        if not transitions:
            raise ValueError("转移表不能为空")
        if initial not in transitions:
            raise ValueError(f"初始状态 {initial!r} 不在转移表内: "
                             f"{sorted(transitions)}")
        for state, edges in transitions.items():
            for event, nxt in edges.items():
                if nxt not in transitions:
                    raise ValueError(f"转移目标 {nxt!r}（{state!r} + "
                                     f"{event!r}）未在表中声明")
        self._table = transitions
        self._state = initial

    @property
    def state(self) -> str:
        return self._state

    def can(self, event: str) -> bool:
        """当前状态能否响应事件。"""
        return event in self._table[self._state]

    def events(self) -> list[str]:
        """当前状态的合法事件（排序，确定性）。"""
        return sorted(self._table[self._state])

    def fire(self, event: str) -> str:
        """单步转移，返回新状态；非法事件报错并列出合法事件。"""
        edges = self._table[self._state]
        if event not in edges:
            raise ValueError(f"状态 {self._state!r} 不响应事件 {event!r}，"
                             f"合法事件: {sorted(edges)}")
        self._state = edges[event]
        return self._state

    def run(self, events: list[str]) -> list[str]:
        """跑事件序列 → 状态 trace（含初始态）。"""
        trace = [self._state]
        for e in events:
            trace.append(self.fire(e))
        return trace


def _selftest() -> None:
    # 旋转门（FSM 教科书例）：locked/unlocked × coin/push
    ts = StateMachine({"locked": {"coin": "unlocked", "push": "locked"},
                       "unlocked": {"push": "locked", "coin": "unlocked"}},
                      "locked")

    # 单步与 trace 手算
    assert ts.state == "locked"
    assert ts.fire("coin") == "unlocked"
    assert ts.fire("push") == "locked"
    assert StateMachine({"locked": {"coin": "unlocked", "push": "locked"},
                         "unlocked": {"push": "locked",
                                      "coin": "unlocked"}},
                        "locked").run(["coin", "push", "coin"]) == \
        ["locked", "unlocked", "locked", "unlocked"]
    assert ts.state == "locked"          # run 后回到初始

    # 查询：合法事件排序、can 布尔
    assert ts.events() == ["coin", "push"]
    assert ts.can("coin") and not ts.can("eject")

    # 死端状态：目标必须声明（即使无出边）
    de = StateMachine({"on": {"off": "off"}, "off": {}}, "on")
    assert de.run(["off"]) == ["on", "off"]
    assert de.events() == [] and not de.can("off")

    # 构造期报错：空表 / 初始不在表 / 目标未声明
    for bad in (lambda: StateMachine({}, "s"),
                lambda: StateMachine({"a": {}}, "b"),
                lambda: StateMachine({"a": {"go": "ghost"}}, "a")):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("应报错")

    # 运行期报错：非法事件带合法事件列表
    try:
        ts.fire("eject")
    except ValueError as e:
        assert "coin" in str(e) and "push" in str(e)
    else:
        raise AssertionError("应报错")

    # 上下班审批流：三个状态循环走一遍
    flow = StateMachine({"draft": {"submit": "review"},
                         "review": {"approve": "done", "reject": "draft"},
                         "done": {}}, "draft")
    assert flow.run(["submit", "reject", "submit", "approve"]) == \
        ["draft", "review", "draft", "review", "done"]

    print("selftest ok: 旋转门/trace/死端/构造期与运行期报错/审批流 全部通过")


def main() -> None:
    ap = argparse.ArgumentParser(description="简单状态机引擎")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args()
    _selftest()


if __name__ == "__main__":
    main()
