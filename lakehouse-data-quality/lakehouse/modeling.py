"""erwin-style logical and physical data modeling.

A logical model names the business entities, their attributes, keys
and relationships — the diagram an erwin Data Modeler user draws
before any database exists. ``to_postgres_ddl`` / ``to_mysql_ddl``
forward-engineer that logical model into physical DDL, the step erwin
performs when a model is deployed to PostgreSQL or Aurora MySQL.

Validation catches the modelling mistakes that break a deployment:
an entity with no primary key, a foreign key pointing at an entity or
column that does not exist, a foreign key whose type does not match
the key it references, and duplicate attribute names inside one
entity. A model that fails validation is never forward-engineered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .relational import (
    ColumnDef,
    ForeignKey,
    TableDef,
    aurora_mysql_ddl,
    postgres_ddl,
)


@dataclass
class Attribute:
    name: str
    dtype: str  # pandas dtype string, e.g. "string", "int64"
    nullable: bool = True
    is_primary_key: bool = False


@dataclass
class Relationship:
    name: str
    from_entity: str
    from_attribute: str
    to_entity: str
    to_attribute: str
    cardinality: str = "many-to-one"  # "many-to-one" or "one-to-one"


@dataclass
class Entity:
    name: str
    attributes: list[Attribute] = field(default_factory=list)

    def attribute(self, name: str) -> Attribute | None:
        for attr in self.attributes:
            if attr.name == name:
                return attr
        return None

    def primary_key(self) -> list[str]:
        return [a.name for a in self.attributes if a.is_primary_key]


@dataclass
class LogicalModel:
    name: str
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)

    def entity(self, name: str) -> Entity | None:
        for entity in self.entities:
            if entity.name == name:
                return entity
        return None

    def validate(self) -> list[str]:
        """Return modelling issues; an empty list means the model is sound."""
        issues: list[str] = []
        for entity in self.entities:
            names = [a.name for a in entity.attributes]
            if len(names) != len(set(names)):
                issues.append(f"entity {entity.name}: duplicate attribute names")
            if not entity.attributes:
                issues.append(f"entity {entity.name}: no attributes")
            elif not entity.primary_key():
                issues.append(f"entity {entity.name}: no primary key")
        for rel in self.relationships:
            from_entity = self.entity(rel.from_entity)
            to_entity = self.entity(rel.to_entity)
            if from_entity is None:
                issues.append(f"relationship {rel.name}: unknown entity {rel.from_entity}")
                continue
            if to_entity is None:
                issues.append(f"relationship {rel.name}: unknown entity {rel.to_entity}")
                continue
            from_attr = from_entity.attribute(rel.from_attribute)
            to_attr = to_entity.attribute(rel.to_attribute)
            if from_attr is None:
                issues.append(
                    f"relationship {rel.name}: {rel.from_entity} has no attribute {rel.from_attribute}"
                )
            if to_attr is None:
                issues.append(
                    f"relationship {rel.name}: {rel.to_entity} has no attribute {rel.to_attribute}"
                )
            if from_attr is not None and to_attr is not None:
                if not to_attr.is_primary_key:
                    issues.append(
                        f"relationship {rel.name}: {rel.to_entity}.{rel.to_attribute} is not a primary key"
                    )
                if from_attr.dtype != to_attr.dtype:
                    issues.append(
                        f"relationship {rel.name}: type mismatch "
                        f"{rel.from_entity}.{rel.from_attribute} ({from_attr.dtype}) vs "
                        f"{rel.to_entity}.{rel.to_attribute} ({to_attr.dtype})"
                    )
        return issues

    def to_table_defs(self) -> list[TableDef]:
        """Forward-engineer the logical model into physical table definitions."""
        issues = self.validate()
        if issues:
            raise ValueError("model is not valid: " + "; ".join(issues))
        tables: list[TableDef] = []
        for entity in self.entities:
            fks = [
                ForeignKey(rel.from_attribute, rel.to_entity, rel.to_attribute)
                for rel in self.relationships
                if rel.from_entity == entity.name
            ]
            tables.append(
                TableDef(
                    name=entity.name,
                    columns=[
                        ColumnDef(a.name, a.dtype, nullable=a.nullable)
                        for a in entity.attributes
                    ],
                    primary_key=entity.primary_key(),
                    foreign_keys=fks,
                )
            )
        return tables

    def to_postgres_ddl(self) -> str:
        """Forward-engineer the model as PostgreSQL DDL."""
        return "\n".join(postgres_ddl(t) for t in self.to_table_defs())

    def to_mysql_ddl(self) -> str:
        """Forward-engineer the model as Aurora MySQL DDL."""
        return "\n".join(aurora_mysql_ddl(t) for t in self.to_table_defs())

    def render_er_text(self) -> str:
        """Render the model as a plain-text entity-relationship diagram."""
        lines = [f"Logical model: {self.name}", ""]
        for entity in self.entities:
            lines.append(f"[{entity.name}]")
            for attr in entity.attributes:
                key = " PK" if attr.is_primary_key else ""
                null = "" if attr.nullable else " NOT NULL"
                lines.append(f"  {attr.name}: {attr.dtype}{key}{null}")
            lines.append("")
        for rel in self.relationships:
            lines.append(
                f"{rel.from_entity}.{rel.from_attribute} --{rel.cardinality}--> "
                f"{rel.to_entity}.{rel.to_attribute}  ({rel.name})"
            )
        return "\n".join(lines) + "\n"


def orders_model() -> LogicalModel:
    """Logical model for the lakehouse orders domain (customers/products/orders)."""
    return LogicalModel(
        name="Lakehouse Orders",
        entities=[
            Entity(
                "customers",
                [
                    Attribute("customer_id", "string", nullable=False, is_primary_key=True),
                    Attribute("customer_name", "string", nullable=False),
                    Attribute("region", "string", nullable=False),
                    Attribute("signup_date", "datetime64[ns]", nullable=False),
                ],
            ),
            Entity(
                "products",
                [
                    Attribute("product_id", "string", nullable=False, is_primary_key=True),
                    Attribute("product_name", "string", nullable=False),
                    Attribute("category", "string", nullable=False),
                    Attribute("list_price", "float64", nullable=False),
                ],
            ),
            Entity(
                "orders",
                [
                    Attribute("order_id", "string", nullable=False, is_primary_key=True),
                    Attribute("customer_id", "string", nullable=False),
                    Attribute("product_id", "string", nullable=False),
                    Attribute("order_date", "datetime64[ns]", nullable=False),
                    Attribute("quantity", "int64", nullable=False),
                    Attribute("unit_price", "float64", nullable=False),
                    Attribute("total_amount", "float64", nullable=False),
                    Attribute("region", "string", nullable=False),
                ],
            ),
        ],
        relationships=[
            Relationship(
                "order_customer", "orders", "customer_id", "customers", "customer_id"
            ),
            Relationship(
                "order_product", "orders", "product_id", "products", "product_id"
            ),
        ],
    )
