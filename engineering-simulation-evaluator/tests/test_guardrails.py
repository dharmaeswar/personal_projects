"""Tests for provenance.py and guardrails.py."""

import pytest

from eng_sim_evaluator.beam import Beam
from eng_sim_evaluator.golden import GOLDEN_VERSION, generate_golden
from eng_sim_evaluator.guardrails import apply_change, gate_change, static_check
from eng_sim_evaluator.provenance import record_provenance

STEEL = Beam(length=2.0, width=0.1, height=0.10, youngs_modulus=200e9)
GOLDEN = generate_golden([("steel-100mm", STEEL, 1000.0)])


def _provenance():
    return record_provenance(
        "land_change", "agent-1", {"change": {}}, {"change": {}}, GOLDEN_VERSION
    )


def test_provenance_hashes_are_stable_and_distinct():
    a = record_provenance("run_simulation", "agent-1", {"case": "x"}, {"v": 1})
    b = record_provenance("run_simulation", "agent-1", {"case": "x"}, {"v": 1})
    assert a.inputs_hash == b.inputs_hash
    assert a.result_hash == b.result_hash
    c = record_provenance("run_simulation", "agent-1", {"case": "y"}, {"v": 1})
    assert c.inputs_hash != a.inputs_hash


def test_provenance_requires_tool_and_agent():
    with pytest.raises(ValueError):
        record_provenance("", "agent-1", {}, {})
    with pytest.raises(ValueError):
        record_provenance("run_simulation", "", {}, {})


def test_static_check_accepts_valid_change():
    assert static_check({"height_m": 0.12, "load_n": 900.0}) == []


def test_static_check_flags_unknown_and_bad_values():
    violations = static_check({"height_m": -0.05, "surprise": 1, "load_n": "fast"})
    assert len(violations) == 3


def test_apply_change_overrides_only_given_fields():
    beam, load = apply_change(STEEL, 1000.0, {"height_m": 0.12})
    assert beam.height == 0.12
    assert beam.length == STEEL.length
    assert load == 1000.0


def test_gate_allows_no_op_change_with_provenance():
    gate = gate_change({}, GOLDEN["steel-100mm"], _provenance())
    assert gate.allowed
    assert gate.reasons == []


def test_gate_blocks_change_that_moves_outputs():
    gate = gate_change({"height_m": 0.12}, GOLDEN["steel-100mm"], _provenance())
    assert not gate.allowed
    assert any("golden comparison" in r for r in gate.reasons)


def test_gate_blocks_change_without_provenance():
    gate = gate_change({}, GOLDEN["steel-100mm"], None)
    assert not gate.allowed
    assert any("provenance" in r for r in gate.reasons)


def test_gate_blocks_stale_golden_version():
    stale = record_provenance(
        "land_change", "agent-1", {"change": {}}, {"change": {}}, "golden-v0"
    )
    gate = gate_change({}, GOLDEN["steel-100mm"], stale)
    assert not gate.allowed
    assert any("golden version" in r for r in gate.reasons)


def test_gate_blocks_malformed_change_before_other_checks():
    gate = gate_change({"height_m": -0.05}, GOLDEN["steel-100mm"], _provenance())
    assert not gate.allowed
    assert any("static analysis" in r for r in gate.reasons)
