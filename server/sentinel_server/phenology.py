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


@dataclass(frozen=True)
class PestModel:
    code: str
    name: str
    base_f: float
    start: str  # what the degree-day clock starts from
    milestones: tuple[Milestone, ...]


MODELS = {
    "CM": PestModel("CM", "Codling moth", 50, "biofix (first sustained catch)", (
        Milestone(50, "Egg laying begins: apply materials that must be present before egg laying (50–75 DD)"),
        Milestone(100, "Early egg laying: window for materials targeting early egg laying (100–200 DD)"),
        Milestone(220, "First eggs hatch"),
        Milestone(250, "First spray for overwintering generation; second spray 10–14 days later"),
    )),
    "OFM": PestModel("OFM", "Oriental fruit moth", 45, "biofix (first sustained catch)", (
        # First-generation timing is tied to petal fall; the second flight is predicted from Jan 1.
        Milestone(1000, "2nd flight expected (1000–1400 DD base 45 °F from Jan 1)"),
    )),
    "OBLR": PestModel("OBLR", "Obliquebanded leafroller", 43, "biofix (first catch; traps out by June 1)", (
        Milestone(350, "Egg hatch: spray targeting larvae (history of OBLR); second spray 10–14 days later"),
        Milestone(600, "Scout growing terminals for larvae (600–700 DD)"),
    )),
    "PC": PestModel("PC", "Plum curculio", 50, "petal fall (entered manually)", (
        Milestone(308, "Protection can stop: oviposition period over (308 DD after petal fall)"),
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
