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


def test_label_matches_the_biofix_rule_the_code_applies():
    """Every lure's clock starts at sustained_biofix(), so the page must say so (L-12: OBLR said "first catch").
    Cornell (Jentsch, 2019): OBLR caught "over two to three successive days (sustained flight)" sets the biofix."""
    for code in ("CM", "OFM", "OBLR"):
        assert "first sustained catch" in ph.MODELS[code].start, code
    assert ph.MODELS["OBLR"].base_f == 43  # NEWA's OBLR tool: base 43 °F BE degree days


def test_outlook_says_what_is_due_and_when():
    """The grower's sentence for a trap: what is due now or next, and in about how many days at this week's
    temperatures (L-25's "what to do this week")."""
    from datetime import timedelta

    cm, today = ph.MODELS["CM"], date(2026, 6, 20)
    warm = {today - timedelta(days=i): (70, 50) for i in range(10)}  # ~10 DD50 a day
    o = ph.outlook(cm, None, None, warm, today)
    assert o["state"] == "waiting" and o["headline"] == "Waiting for biofix"
    o = ph.outlook(cm, date(2026, 6, 1), 230, warm, today)
    assert o["state"] == "soon" and o["next"].short == "First spray" and o["dd_to_go"] == 20 and o["days_to_go"] == 2
    assert o["headline"] == "First spray in about 2 days"
    o = ph.outlook(cm, date(2026, 6, 1), 262, warm, today)
    assert o["state"] == "now" and o["headline"] == "First spray due now" and o["next"] is None
    assert o["detail"].startswith("First spray for overwintering generation")
    mild = {today - timedelta(days=i): (60, 46) for i in range(10)}  # ~3.6 DD50 a day
    o2 = ph.outlook(cm, date(2026, 6, 1), 60, mild, today)  # next (100) is 12 days off: "now" wins
    assert o2["headline"] == "Egg laying begins now" and "Then early egg laying in about" in o2["detail"], o2
    assert [m.short for m in o["passed"]] == ["Egg laying begins", "Early egg laying", "First eggs hatch", "First spray"]
    o = ph.outlook(cm, date(2026, 6, 1), 140, warm, today)  # early egg laying (100) is 40 DD back
    assert o["state"] == "later" and o["days_to_go"] == 8 and o["headline"] == "Next: first eggs hatch in about 8 days"
    cold = {today - timedelta(days=i): (48, 35) for i in range(10)}
    o = ph.outlook(cm, date(2026, 6, 1), 140, cold, today)
    assert o["days_to_go"] is None and "too cool" in o["detail"].lower()
    assert all(m.short for model in ph.MODELS.values() for m in model.milestones)
