import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from dbre.health import check_snapshot, overall_status, SAMPLE_HEALTHY, SAMPLE_DEGRADED
def test_healthy_all_pass():
    r=check_snapshot(SAMPLE_HEALTHY); assert overall_status(r)=="pass"; assert len(r)==5
def test_degraded_fails():
    r=check_snapshot(SAMPLE_DEGRADED); assert overall_status(r)=="fail"
def test_warn_band():
    s=dict(SAMPLE_HEALTHY, replication_lag_seconds=30)
    r=check_snapshot(s); assert [x for x in r if x.name=="replication_lag"][0].status=="warn"
def test_zero_max_connections_no_crash():
    s=dict(SAMPLE_HEALTHY, max_connections=0); assert len(check_snapshot(s))==5
