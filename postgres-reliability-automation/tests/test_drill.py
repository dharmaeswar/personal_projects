import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from dbre.drill import build_drill_plan, run_drill
from dbre.health import check_snapshot, SAMPLE_HEALTHY, SAMPLE_DEGRADED
def test_plan_has_seven_steps():
    p=build_drill_plan(); assert len(p["steps"])==7; assert p["rto_minutes"]==30
def test_drill_proceeds_when_healthy():
    rep=run_drill(build_drill_plan(), check_snapshot(SAMPLE_HEALTHY)); assert rep["verdict"]=="PROCEED"
def test_drill_blocked_when_failing():
    rep=run_drill(build_drill_plan(), check_snapshot(SAMPLE_DEGRADED)); assert rep["ready_for_drill"] is False
