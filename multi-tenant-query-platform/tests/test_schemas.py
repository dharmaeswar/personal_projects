import pytest

from query_platform.schemas import FieldDef, SchemaRegistry


def test_register_versions_schemas():
    reg = SchemaRegistry()
    v1 = reg.register("acme", "contracts", [FieldDef("title", "string", required=True)])
    v2 = reg.register("acme", "contracts", [
        FieldDef("title", "string", required=True), FieldDef("amount", "number")])
    assert v1.version == 1 and v2.version == 2
    assert reg.latest("acme", "contracts") is v2
    assert reg.get("acme", "contracts", 1) is v1
    assert reg.get("acme", "contracts", 9) is None
    assert reg.collections("acme") == ["contracts"]


def test_bad_field_type_rejected():
    with pytest.raises(ValueError):
        FieldDef("x", "date")


def test_validation_catches_missing_required_unknown_and_wrong_type():
    reg = SchemaRegistry()
    schema = reg.register("t", "c", [
        FieldDef("title", "string", required=True),
        FieldDef("amount", "number"),
        FieldDef("tags", "string_list"),
    ])
    assert schema.validate({"title": "ok", "amount": 5}) == []
    errs = schema.validate({"amount": "five", "nope": 1})
    assert any("missing required" in e for e in errs)
    assert any("unknown field" in e for e in errs)
    assert any("must be a number" in e for e in errs)
    assert schema.validate({"title": "ok", "tags": ["a", 1]}) != []


def test_validation_accepts_all_types():
    reg = SchemaRegistry()
    schema = reg.register("t", "c", [
        FieldDef("a", "string"), FieldDef("b", "number"), FieldDef("c", "boolean"),
        FieldDef("d", "string_list"), FieldDef("e", "timestamp")])
    assert schema.validate({"a": "x", "b": 1.5, "c": True, "d": ["y"], "e": 1700000000}) == []
