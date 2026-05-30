import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.scenario import load_scenario
from backend.constellation import CHINA_GROUND_STATIONS

def test_load_default_scenario_matches_constellation():
    sc = load_scenario()
    assert [g["id"] for g in sc["ground_stations"]] == [g["id"] for g in CHINA_GROUND_STATIONS]
    assert len(sc["leo_satellites"]) == 8
    assert sc["leo_satellites"][0].get_orbital_period() > 0
    assert isinstance(sc["data_types"]["TASK_CMD"]["size_range"], tuple)
