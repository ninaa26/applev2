"""Degree days, biofix and management timings, following the NEWA Quick Guide for apple insect pests.

Degree days use the Baskerville-Emin (BE) single-sine method with a lower
threshold only, which is what NEWA's "°F BE" degree days are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta


def be_degree_days(tmax_f: float, tmin_f: float, base_f: float) -> float:
    """Baskerville-Emin single-sine degree days for one day, lower threshold only."""
    if tmax_f < tmin_f:
        tmax_f, tmin_f = tmin_f, tmax_f
    if tmax_f <= base_f:
        return 0.0
    mean = (tmax_f + tmin_f) / 2
    if tmin_f >= base_f:
        return mean - base_f
    amp = (tmax_f - tmin_f) / 2
    theta = math.asin((base_f - mean) / amp)
    return ((mean - base_f) * (math.pi / 2 - theta) + amp * math.cos(theta)) / math.pi


@dataclass(frozen=True)
class Milestone:
    dd: float
    label: str
    short: str = ""  # a few words, for the grower's sentence ("First spray in about 2 days")


@dataclass(frozen=True)
class PestModel:
    code: str
    name: str
    base_f: float
    start: str  # what the degree-day clock starts from
    milestones: tuple[Milestone, ...]


MODELS = {
    "CM": PestModel("CM", "Codling moth", 50, "biofix (first sustained catch)", (
        Milestone(50, "Egg laying begins: apply materials that must be present before egg laying (50–75 DD)", "Egg laying begins"),
        Milestone(100, "Early egg laying: window for materials targeting early egg laying (100–200 DD)", "Early egg laying"),
        Milestone(220, "First eggs hatch", "First eggs hatch"),
        Milestone(250, "First spray for overwintering generation; second spray 10–14 days later", "First spray"),
    )),
    "OFM": PestModel("OFM", "Oriental fruit moth", 45, "biofix (first sustained catch)", (
        # UC IPM OFM phenology models (Croft et al. 1980, validated in Michigan; Rice et al. 1984),
        # both base 45 °F from biofix. They use a 90 °F horizontal upper cutoff that NEWA's BE
        # degree days don't; it rarely matters in Ithaca. The 2nd flight is also predicted from
        # Jan 1 (1000–1400 DD), shown separately on the trap page.
        Milestone(50, "Egg laying begins", "Egg laying begins"),
        Milestone(200, "Egg hatch begins: time larval sprays for the first generation", "Larval spray"),
        Milestone(965, "Next generation's moths start flying", "Next flight"),
    )),
    # Biofix: sustained flight, moths caught "over two to three successive days" (Cornell, Jentsch 2019);
    # NEWA's OBLR page doesn't define it. Checked Oct 24 2026 (L-12).
    "OBLR": PestModel("OBLR", "Obliquebanded leafroller", 43, "biofix (first sustained catch; traps out by June 1)", (
        Milestone(350, "Egg hatch: spray targeting larvae (history of OBLR); second spray 10–14 days later", "Larval spray"),
        Milestone(600, "Scout growing terminals for larvae (600–700 DD)", "Scout terminals"),
    )),
    "PC": PestModel("PC", "Plum curculio", 50, "petal fall (entered manually)", (
        Milestone(308, "Protection can stop: oviposition period over (308 DD after petal fall)", "Protection can stop"),
    )),
}


def cumulative_dd(days: dict[date, tuple[float, float]], start: date, end: date, base_f: float) -> tuple[float, int]:
    """Sum DD over [start, end]. Returns (total, missing_days)."""
    total, missing = 0.0, 0
    d = start
    while d <= end:
        if d in days:
            total += be_degree_days(days[d][0], days[d][1], base_f)
        else:
            missing += 1
        d += timedelta(days=1)
    return total, missing


def sustained_biofix(catch_dates: list[date], min_per_week: int = 2, weeks_in_a_row: int = 2) -> date | None:
    """NEWA: 'mark 1st capture when you have captured more than 1 moth two weeks in a row'.

    Weeks run Monday–Sunday. Returns the date of the first catch in the first
    week of the first qualifying run, or None.
    """
    if not catch_dates:
        return None
    by_week: dict[date, list[date]] = {}
    for d in sorted(catch_dates):
        by_week.setdefault(d - timedelta(days=d.weekday()), []).append(d)
    weeks = sorted(by_week)
    first, last = weeks[0], weeks[-1]
    run: list[date] = []
    w = first
    while w <= last:
        if len(by_week.get(w, [])) >= min_per_week:
            run.append(w)
            if len(run) >= weeks_in_a_row:
                return by_week[run[0]][0]
        else:
            run = []
        w += timedelta(days=7)
    return None


NOW_WITHIN_DD = 30  # a milestone passed this recently is still "due now"
SOON_DAYS = 7       # a milestone this close is "soon"


def recent_dd_per_day(days: dict[date, tuple[float, float]], today: date, base_f: float, n: int = 7) -> float | None:
    """Mean degree days a day over the last n days with weather data: how fast the clock is running now."""
    got = [be_degree_days(*days[d], base_f) for i in range(n) if (d := today - timedelta(days=i)) in days]
    return sum(got) / len(got) if got else None


def outlook(model: PestModel, biofix: date | None, dd: float | None, days: dict[date, tuple[float, float]],
            today: date) -> dict:
    """The grower's sentence for one trap: what is due now or next, and in about how many days at this
    week's temperatures. state: waiting (no biofix), soon (within SOON_DAYS), now (just passed), later, done."""
    if biofix is None or dd is None:
        return {"state": "waiting", "headline": "Waiting for biofix", "passed": [], "next": None,
                "dd_to_go": None, "days_to_go": None,
                "detail": "The degree-day clock starts at the first sustained catch of this lure's moth."}
    passed = [m for m in model.milestones if dd >= m.dd]
    nxt = next_milestone(model, dd)
    rate = recent_dd_per_day(days, today, model.base_f)
    to_go = round(nxt.dd - dd) if nxt else None
    days_to_go = math.ceil(to_go / rate) if to_go is not None and rate and rate >= 0.5 else None
    detail = ""
    if nxt and days_to_go is None:
        detail = "Too cool this week for degree days to build up." if rate is not None else "No recent weather data."
    elif nxt:
        detail = f"{to_go} DD to go, at about {rate:.0f} DD a day this week."
    when = f"in about {days_to_go} day{'s' if days_to_go != 1 else ''}" if days_to_go is not None else f"at {nxt.dd:.0f} DD" if nxt else ""
    if nxt and days_to_go is not None and days_to_go <= SOON_DAYS:
        state, headline = "soon", f"{nxt.short} {when}"
    elif passed and dd - passed[-1].dd <= NOW_WITHIN_DD:
        last = passed[-1]
        state, headline = "now", f"{last.short} {'due ' if 'spray' in last.short.lower() else ''}now"
        detail = f"{last.label}." + (f" Then {nxt.short[0].lower()}{nxt.short[1:]} {when}." if nxt else "")
    elif nxt:
        state, headline = "later", f"Next: {nxt.short[0].lower()}{nxt.short[1:]} {when}"
    else:
        state, headline = "done", "All milestones passed for this generation"
    return {"state": state, "headline": headline, "passed": passed, "next": nxt, "dd_to_go": to_go,
            "days_to_go": days_to_go, "detail": detail}


def next_milestone(model: PestModel, dd: float) -> Milestone | None:
    for m in model.milestones:
        if dd < m.dd:
            return m
    return None


def daily_extremes_f(readings: list[tuple[date, float]]) -> dict[date, tuple[float, float]]:
    """(local date, °C) readings -> {date: (tmax °F, tmin °F)}. Days with <4 readings are skipped:
    a trap that sleeps between photos only samples a few times a day, which under-estimates the range."""
    per_day: dict[date, list[float]] = {}
    for d, c in readings:
        per_day.setdefault(d, []).append(c * 9 / 5 + 32)
    return {d: (max(v), min(v)) for d, v in per_day.items() if len(v) >= 4}
