"""Currency conversion to USD. Money is Decimal throughout — never float."""

from decimal import Decimal

CENT = Decimal("0.01")


def to_usd(value, currency, rates):
    """Convert ``value`` in ``currency`` to USD using ``rates``.

    Raises KeyError for an unknown currency; the quality rules quarantine
    such rows before conversion, so this should never fire on valid rows.
    """
    rate = rates[currency]
    return (value * rate).quantize(CENT)


def convert_row(row, rates):
    """Return a copy of a valid manifest row with ``value_usd`` added."""
    converted = dict(row)
    converted["value_usd"] = to_usd(row["value"], row["currency"], rates)
    return converted
