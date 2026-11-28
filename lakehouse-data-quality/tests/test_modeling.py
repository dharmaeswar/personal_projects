"""Tests for erwin-style logical/physical data modeling."""

from __future__ import annotations

import pytest

from lakehouse.modeling import (
    Attribute,
    Entity,
    LogicalModel,
    Relationship,
    orders_model,
)


def test_orders_model_is_valid():
    model = orders_model()
    assert model.validate() == []


def test_model_flags_entity_without_primary_key():
    model = LogicalModel(
        "Bad",
        entities=[Entity("t", [Attribute("a", "string")])],
    )
    issues = model.validate()
    assert any("no primary key" in i for i in issues)


def test_model_flags_unknown_fk_target():
    model = LogicalModel(
        "Bad",
        entities=[
            Entity("orders", [Attribute("order_id", "string", is_primary_key=True),
                              Attribute("customer_id", "string")]),
        ],
        relationships=[
            Relationship("r", "orders", "customer_id", "customers", "customer_id")
        ],
    )
    issues = model.validate()
    assert any("unknown entity customers" in i for i in issues)


def test_model_flags_fk_type_mismatch():
    model = LogicalModel(
        "Bad",
        entities=[
            Entity("customers", [Attribute("customer_id", "int64", is_primary_key=True)]),
            Entity(
                "orders",
                [
                    Attribute("order_id", "string", is_primary_key=True),
                    Attribute("customer_id", "string"),
                ],
            ),
        ],
        relationships=[
            Relationship("r", "orders", "customer_id", "customers", "customer_id")
        ],
    )
    issues = model.validate()
    assert any("type mismatch" in i for i in issues)


def test_model_flags_duplicate_attribute():
    model = LogicalModel(
        "Bad",
        entities=[
            Entity(
                "t",
                [
                    Attribute("id", "string", is_primary_key=True),
                    Attribute("id", "string"),
                ],
            )
        ],
    )
    assert any("duplicate attribute" in i for i in model.validate())


def test_invalid_model_cannot_forward_engineer():
    model = LogicalModel(
        "Bad", entities=[Entity("t", [Attribute("a", "string")])]
    )
    with pytest.raises(ValueError, match="not valid"):
        model.to_postgres_ddl()


def test_postgres_ddl_has_all_tables_and_fks():
    ddl = orders_model().to_postgres_ddl()
    assert ddl.count("CREATE TABLE") == 3
    assert "CREATE TABLE customers" in ddl
    assert "CREATE TABLE orders" in ddl
    assert "FOREIGN KEY (customer_id) REFERENCES customers (customer_id)" in ddl
    assert "FOREIGN KEY (product_id) REFERENCES products (product_id)" in ddl


def test_mysql_ddl_has_all_tables():
    ddl = orders_model().to_mysql_ddl()
    assert ddl.count("CREATE TABLE") == 3
    assert ddl.count("ENGINE=InnoDB") == 3


def test_er_text_names_entities_and_relationships():
    text = orders_model().render_er_text()
    assert "[orders]" in text
    assert "[customers]" in text
    assert "order_customer" in text
    assert "order_product" in text
