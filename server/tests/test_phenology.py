from datetime import date

import pytest

from sentinel_server import phenology as ph


def test_be_degree_days_cases():
    assert ph.be_degree_days(80, 60, 50) == pytest.approx(20.0)       # whole day above base
    assert ph.be_degree_days(45, 30, 50) == 0.0                       # whole day below base
    assert ph.be_degree_days(60, 40, 50) == pytest.approx(10 / 3.141592653589793, rel=1e-6)  # mean == base
    # partial day: the sine method exceeds the simple average (mean - base = 5) because it
    # doesn't subtract the cold night hours, but stays below (tmax - base) / 2 = 10.
    dd = ph.be_degree_days(70, 40, 50)
    assert dd == pytest.approx(7.5424, abs=1e-3) and 5.0 < dd < 10.0
    assert ph.be_degree_days(40, 70, 50) == pytest.approx(dd)         # swapped max/min tolerated


def test_cumulative_dd_counts_missing_days():
    days = {date(2026, 6, 1): (80, 60), date(2026, 6, 3): (80, 60)}
    total, missing = ph.cumulative_dd(days, date(2026, 6, 1), date(2026, 6, 3), 50)
    assert total == pytest.approx(40) and missing == 1


def test_sustained_biofix_needs_two_weeks_in_a_row():
    # week of May 4: 1 moth (not enough); weeks of May 11 and May 18: 2 each -> biofix May 12
    catches = [date(2026, 5, 6), date(2026, 5, 12), date(2026, 5, 14), date(2026, 5, 19), date(2026, 5, 20)]
    assert ph.sustained_biofix(catches) == date(2026, 5, 12)
    # a gap week breaks the run
    assert ph.sustained_biofix([date(2026, 5, 12), date(2026, 5, 13), date(2026, 5, 26), date(2026, 5, 27)]) is None
    assert ph.sustained_biofix([]) is None


def test_ofm_milestones_are_since_biofix():
    ofm = ph.MODELS["OFM"]
    assert ph.next_milestone(ofm, 0).dd == 50
    assert ph.next_milestone(ofm, 150).dd == 200
    assert ph.next_milestone(ofm, 500).dd == 965


def test_next_milestone_cm():
    cm = ph.MODELS["CM"]
    assert ph.next_milestone(cm, 0).dd == 50
    assert ph.next_milestone(cm, 230).dd == 250
    assert ph.next_milestone(cm, 300) is None


def test_daily_extremes_requires_enough_readings():
    d = date(2026, 10, 5)
    out = ph.daily_extremes_f([(d, 10.0), (d, 20.0), (d, 15.0), (d, 12.0), (date(2026, 10, 6), 5.0)])
    assert out == {d: (68.0, 50.0)}
