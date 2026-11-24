import pytest

from capplanner import capacity


def test_plan_small_table_one_partition():
    plan = capacity.plan(100, 50, avg_item_kb=2.0, storage_gb=5.0)
    assert plan["partitions"] == 1
    assert plan["provisioned_rcu"] == 3000
    assert plan["provisioned_wcu"] == 1000
    assert plan["headroom_fraction"] > 0.9


def test_plan_reads_drive_partitions():
    # 9,000 rps at 4 KB items = 9,000 RCU; with 25% headroom -> 12,000 RCU -> 4 partitions.
    plan = capacity.plan(9000, 10, avg_item_kb=4.0, storage_gb=5.0)
    assert plan["partitions"] == 4
    assert plan["limiting_factor"] == "reads"


def test_plan_storage_drives_partitions():
    plan = capacity.plan(10, 10, avg_item_kb=1.0, storage_gb=55.0)
    assert plan["partitions"] == 6  # ceil(55 / 10)
    assert plan["limiting_factor"] == "storage"


def test_plan_writes_drive_partitions():
    # 2,500 wps at 2 KB items = 5,000 WCU; with headroom -> 6,667 WCU -> 7 partitions.
    plan = capacity.plan(10, 2500, avg_item_kb=2.0, storage_gb=5.0)
    assert plan["partitions"] == 7
    assert plan["limiting_factor"] == "writes"


def test_plan_cost_grows_with_partitions():
    small = capacity.plan(100, 50, avg_item_kb=2.0, storage_gb=5.0)
    big = capacity.plan(9000, 2500, avg_item_kb=2.0, storage_gb=5.0)
    assert big["monthly_cost_usd"] > small["monthly_cost_usd"]
    assert big["partitions"] > small["partitions"]


def test_plan_rejects_bad_inputs():
    with pytest.raises(ValueError):
        capacity.plan(-1, 10, 2.0, 5.0)
    with pytest.raises(ValueError):
        capacity.plan(10, 10, 0.0, 5.0)
    with pytest.raises(ValueError):
        capacity.plan(10, 10, 2.0, -1.0)
    with pytest.raises(ValueError):
        capacity.plan(10, 10, 2.0, 5.0, headroom=1.0)


def test_check_headroom():
    plan = capacity.plan(100, 50, avg_item_kb=2.0, storage_gb=5.0)
    assert capacity.check_headroom(plan, 100, 2.0)
    assert not capacity.check_headroom(plan, 100_000, 2.0)
