"""Sandbox simulate must auto-pass action triggers so chains can proceed."""

from __future__ import annotations

from core.harness.ontology_engine.state_machine import EvalContext, StateMachine


class _Cls:
    def __init__(self, label: str, uri: str, states: dict, transitions: list):
        self.label = label
        self.uri = uri
        self.states = states
        self.transitions = transitions
        self.side_effects = []


class _Prop:
    def __init__(self, uri: str, label: str, ranges: list, domains: list | None = None):
        self.uri = uri
        self.label = label
        self.range = ranges
        self.domain = domains or []
        self.inverse_label = ""


class _Domain:
    def __init__(self):
        self.classes = [
            _Cls(
                "安装工单",
                "http://x/InstallOrder",
                {"default": "pending", "enum": [{"name": "pending"}, {"name": "accepted"}, {"name": "assigned"}]},
                [
                    {"from": "pending", "to": "accepted", "trigger": {"type": "action", "action_id": "a1"}},
                    {"from": "accepted", "to": "assigned", "trigger": {"type": "relation_exists", "relation": "assigned_to"}},
                ],
            ),
            _Cls("安装师傅", "http://x/Technician", {}, []),
        ]
        self.object_properties = [
            _Prop("http://x/assigned_to", "派单给", ["http://x/Technician"], ["http://x/InstallOrder"]),
        ]


def test_action_trigger_false_outside_simulate():
    sm = StateMachine(_Domain())
    inst = {"class_name": "安装工单", "properties": {"name": "o1"}, "chunk_id": "c0", "entity_text": "o1"}
    others = [
        inst,
        {"class_name": "安装师傅", "properties": {"name": "t1"}, "chunk_id": "c0", "entity_text": "t1"},
        {"class_name": "安装师傅", "properties": {"name": "t2"}, "chunk_id": "c0", "entity_text": "t2"},
    ]
    assert sm.evaluate_chain(inst, EvalContext(others, simulate=False)) == []


def test_action_trigger_auto_pass_in_simulate_then_relation():
    sm = StateMachine(_Domain())
    inst = {"class_name": "安装工单", "properties": {"name": "o1"}, "chunk_id": "c0", "entity_text": "o1"}
    others = [
        inst,
        {"class_name": "安装师傅", "properties": {"name": "t1"}, "chunk_id": "c0", "entity_text": "t1"},
    ]
    chain = sm.evaluate_chain(inst, EvalContext(others, simulate=True))
    assert [t.to_state for t in chain] == ["accepted", "assigned"]
    assert chain[0].trigger_type == "action"
    assert chain[1].trigger_type == "relation_exists"


def test_relation_exists_cross_class_needs_one():
    sm = StateMachine(_Domain())
    inst = {"class_name": "安装工单", "properties": {"name": "o1"}, "chunk_id": "c0", "entity_text": "o1"}
    with_one = [
        inst,
        {"class_name": "安装师傅", "properties": {"name": "t1"}, "chunk_id": "c0", "entity_text": "t1"},
    ]
    chain = sm.evaluate_chain(inst, EvalContext(with_one, simulate=True))
    assert [t.to_state for t in chain] == ["accepted", "assigned"]
