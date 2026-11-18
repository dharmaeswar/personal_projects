"""Legacy code samples used as migration benchmarks.

Each sample is a small, self-contained legacy Python module with a known
behaviour: a list of ``(function_name, args, expected_result)`` cases. The
evaluator runs those cases against both the original and the migrated code,
so a migration scores on behaviour, not on how modern it looks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Sample:
    name: str
    legacy_source: str
    cases: list[tuple[str, tuple, object]] = field(default_factory=list)


GREETING = Sample(
    name="greeting",
    legacy_source=(
        "def greet(name):\n"
        '    return "Hello, %s!" % name\n'
        "\n"
        "def shout(text):\n"
        '    return "%s!!!" % text.upper()\n'
    ),
    cases=[
        ("greet", ("Ada",), "Hello, Ada!"),
        ("greet", ("",), "Hello, !"),
        ("shout", ("hey",), "HEY!!!"),
    ],
)

COUNTERS = Sample(
    name="counters",
    legacy_source=(
        "def total_upto(n):\n"
        "    total = 0\n"
        "    for i in xrange(n + 1):\n"
        "        total += i\n"
        "    return total\n"
        "\n"
        "def squares(n):\n"
        "    return [i * i for i in xrange(n)]\n"
    ),
    cases=[
        ("total_upto", (5,), 15),
        ("total_upto", (0,), 0),
        ("squares", (4,), [0, 1, 4, 9]),
    ],
)

LOOKUP = Sample(
    name="lookup",
    legacy_source=(
        "PRICES = {'apple': 3, 'pear': 5}\n"
        "\n"
        "def price_of(item):\n"
        "    if PRICES.has_key(item):\n"
        "        return PRICES[item]\n"
        "    return -1\n"
        "\n"
        "def receipt(items):\n"
        "    lines = []\n"
        "    for item in items:\n"
        '        lines.append("{}: {}".format(item, price_of(item)))\n'
        "    return lines\n"
    ),
    cases=[
        ("price_of", ("apple",), 3),
        ("price_of", ("plum",), -1),
        ("receipt", (["apple", "pear"],), ["apple: 3", "pear: 5"]),
    ],
)

SAMPLES: dict[str, Sample] = {s.name: s for s in (GREETING, COUNTERS, LOOKUP)}
