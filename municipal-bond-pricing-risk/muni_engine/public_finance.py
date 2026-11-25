"""Public-finance sector screen and sales-research ideas for municipal bonds.

The relative-value screen in ``relative_value.py`` compares every bond with
one market-wide model. A public-finance sales desk also needs the sector
view: general-obligation bonds and revenue bonds backed by water/sewer
systems, toll roads, hospitals, schools or housing do not trade at the same
spread, so a bond can look fair against the whole market yet cheap against
its own sector peers — or the reverse. This module groups screened bonds by
sector, measures each bond against its sector peers, and turns the cheapest
names into short, client-facing sales ideas with a taxable-equivalent yield
for the buyer's tax bracket.

All data handled here is synthetic and seeded in the demo. No real issuer,
CUSIP, or market data appears anywhere in this project.
"""

from .curve import TaxExemptCurve

SECTORS = {
    "GO": "General Obligation",
    "WATER_SEWER": "Water / Sewer Revenue",
    "TOLL_ROAD": "Toll Road Revenue",
    "HOSPITAL": "Hospital Revenue",
    "SCHOOL": "School District",
    "HOUSING": "Housing Revenue",
}


def sector_summary(screened):
    """Mean spread and mean residual per sector over screened bonds.

    ``screened`` is the output of ``RelativeValueScreen.screen`` with a
    ``sector`` key on each row. Returns ``{sector: {...}}`` with the sector
    name, bond count, mean spread and mean model residual in bp.
    """
    groups = {}
    for row in screened:
        sector = row.get("sector", "GO")
        if sector not in SECTORS:
            raise ValueError(f"unknown sector: {sector!r}")
        groups.setdefault(sector, []).append(row)
    out = {}
    for sector, rows in sorted(groups.items()):
        out[sector] = {
            "sector_name": SECTORS[sector],
            "count": len(rows),
            "mean_spread_bp": round(
                sum(r["spread_bp"] for r in rows) / len(rows), 2),
            "mean_residual_bp": round(
                sum(r["residual_bp"] for r in rows) / len(rows), 2),
        }
    return out


def sector_relative_value(screened, threshold_bp=25.0):
    """Flag each bond against its own sector peers, not the whole market.

    A bond's sector residual is its model residual minus its sector's mean
    residual, so a bond that is merely in a wide sector is not called cheap
    for the sector alone. Flags use the same +/-threshold rule as the
    market-wide screen. Returns rows with ``sector_residual_bp`` and
    ``sector_flag`` added.
    """
    summary = sector_summary(screened)
    out = []
    for row in screened:
        sector = row.get("sector", "GO")
        sector_residual = row["residual_bp"] - summary[sector]["mean_residual_bp"]
        if sector_residual > threshold_bp:
            flag = "CHEAP"
        elif sector_residual < -threshold_bp:
            flag = "RICH"
        else:
            flag = "FAIR"
        out.append({**row, "sector_residual_bp": round(sector_residual, 2),
                    "sector_flag": flag})
    return out


def sales_ideas(screened, top_n=3, marginal_tax_rate=0.37):
    """Top client-facing relative-value ideas from the sector screen.

    Ranks bonds flagged CHEAP against their sector peers by sector
    residual, largest first, and attaches the taxable-equivalent yield at
    the given marginal tax rate plus a one-line rationale a salesperson can
    use with a client. Rows need ``yield_pct`` (tax-exempt yield in
    percent) alongside the screen fields. Returns at most ``top_n`` ideas.
    """
    if not 0.0 <= marginal_tax_rate < 1.0:
        raise ValueError("marginal tax rate must be in [0, 1)")
    flagged = sector_relative_value(screened)
    cheap = [r for r in flagged if r["sector_flag"] == "CHEAP"]
    cheap.sort(key=lambda r: r["sector_residual_bp"], reverse=True)
    ideas = []
    for row in cheap[:top_n]:
        tey = TaxExemptCurve.taxable_equivalent_yield(
            row["yield_pct"] / 100.0, marginal_tax_rate)
        rationale = (
            f"{row['id']} ({SECTORS[row.get('sector', 'GO')]}, "
            f"{row['rating']}, {row['maturity_years']}y): spread "
            f"{row['spread_bp']}bp vs {row['predicted_spread_bp']}bp model "
            f"({row['residual_bp']:+.1f}bp), {row['sector_residual_bp']:+.1f}bp "
            f"cheap vs sector peers; TEY {tey * 100:.2f}% at a "
            f"{marginal_tax_rate:.0%} tax bracket."
        )
        ideas.append({**row, "taxable_equivalent_yield_pct": round(tey * 100, 2),
                      "rationale": rationale})
    return ideas
