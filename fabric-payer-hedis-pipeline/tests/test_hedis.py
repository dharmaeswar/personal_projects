"""Tests for the monthly HEDIS computation, on fixtures and on seed data."""

from fabric_hedis import hedis, medallion, seed
from fabric_hedis.sftp_exchange import receive_files

MEMBERS = [
    # (member_id, sex, age, diabetes, hypertension)
    ("M0001", "F", 50, "N", "N"),  # BCS eligible, mammogram -> met
    ("M0002", "F", 50, "N", "N"),  # BCS eligible, no mammogram -> not met
    ("M0003", "M", 60, "N", "N"),  # not BCS eligible; COL eligible, no screen
    ("M0004", "M", 60, "Y", "N"),  # COL + CDC eligible; HbA1c 7.5 -> CDC met
    ("M0005", "F", 70, "Y", "Y"),  # COL + CDC + CBP; HbA1c 8.5, BP 150/95
    ("M0006", "M", 30, "N", "Y"),  # CBP eligible; BP 135/85 -> met
    ("M0007", "F", 80, "N", "Y"),  # CBP eligible (<=85); no BP reading
]
LABS = [
    ("M0004", "HbA1c", "7.5", "2026-09-15"),
    ("M0005", "HbA1c", "8.5", "2026-09-15"),
    ("M0005", "BP", "150/95", "2026-09-20"),
    ("M0006", "BP", "135/85", "2026-09-20"),
]
SCREENS = [
    ("M0001", "mammogram", "2026-03-10"),
    ("M0005", "colonoscopy", "2021-06-01"),
]


def _fixture_conn(tmp_path):
    conn = medallion.connect(tmp_path / "db.sqlite")
    conn.executemany(
        "INSERT INTO silver_members"
        " (member_id, sex, age, diabetes, hypertension)"
        " VALUES (?,?,?,?,?)", MEMBERS)
    conn.executemany(
        "INSERT INTO silver_labs (member_id, test, result, result_date)"
        " VALUES (?,?,?,?)", LABS)
    conn.executemany(
        "INSERT INTO silver_screenings"
        " (member_id, screening_type, screening_date) VALUES (?,?,?)",
        SCREENS)
    conn.commit()
    return conn


def test_hedis_on_hand_built_fixture(tmp_path):
    conn = _fixture_conn(tmp_path)
    results = {r["measure"]: r for r in hedis.compute_hedis(conn, "2026-10")}
    # BCS: M0001, M0002, M0005 eligible (F 40-74); only M0001 screened.
    assert (results["BCS"]["denominator"], results["BCS"]["numerator"]) == (3, 1)
    # COL: M0001..M0005 eligible (45-75); only M0005 screened.
    assert (results["COL"]["denominator"], results["COL"]["numerator"]) == (5, 1)
    # CDC: M0004, M0005 eligible (diabetic 18-75); only M0004 controlled.
    assert (results["CDC"]["denominator"], results["CDC"]["numerator"]) == (2, 1)
    # CBP: M0005, M0006, M0007 eligible; only M0006 controlled.
    assert (results["CBP"]["denominator"], results["CBP"]["numerator"]) == (3, 1)
    for r in results.values():
        assert 0.0 <= r["rate"] <= 1.0
        assert r["rate"] == round(r["numerator"] / r["denominator"], 4)


def test_hedis_is_idempotent(tmp_path):
    conn = _fixture_conn(tmp_path)
    first = hedis.compute_hedis(conn, "2026-10")
    second = hedis.compute_hedis(conn, "2026-10")
    assert first == second
    count = conn.execute(
        "SELECT COUNT(*) FROM gold_hedis_monthly").fetchone()[0]
    assert count == 4


def test_hedis_on_seeded_data(tmp_path):
    seed.write_inbound_files(tmp_path / "inbound")
    received = receive_files(tmp_path / "inbound")
    conn = medallion.connect(tmp_path / "db.sqlite")
    table_for = {
        "members_2026-10.csv": ("bronze_members", seed.MEMBER_COLUMNS),
        "claims_2026-10.csv": ("bronze_claims", seed.CLAIM_COLUMNS),
        "labs_2026-10.csv": ("bronze_labs", seed.LAB_COLUMNS),
        "screenings_2026-10.csv": ("bronze_screenings",
                                   seed.SCREENING_COLUMNS),
    }
    for filename, rows in received.items():
        table, columns = table_for[filename]
        medallion.load_bronze(conn, table, rows, columns)
    medallion.promote_to_silver(conn)
    results = hedis.compute_hedis(conn, "2026-10")
    assert {r["measure"] for r in results} == {"BCS", "COL", "CDC", "CBP"}
    for r in results:
        assert r["denominator"] > 0
        assert 0 <= r["numerator"] <= r["denominator"]
