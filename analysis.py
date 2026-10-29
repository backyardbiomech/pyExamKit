"""Exam statistics in plain Python: the same numbers the Excel gradebook
computes with formulas (outputs.py: _summary_rows, TotalRange.alpha,
_stats_sheet), reproduced here so the Results tab can show them live. Each
function follows its Excel formula's definition and edge cases, and returns
None where Excel would show a blank. Nothing is rounded; callers round for
display. Stdlib only, no I/O."""
from __future__ import annotations

import math

# Letter-grade bands by percent of the points possible, lowest first: each
# runs from its lower bound up to, not including, the next. F is split to
# tell a near miss from a long way off.
BANDS = [('Low F', None, 50, 'below 50%'), ('Close F', 50, 60, '50–59%')]
for _letter, _base in (('D', 60), ('C', 70), ('B', 80)):
    BANDS += [(f'{_letter}−', _base, _base + 3, f'{_base}–{_base + 2}%'),
              (_letter, _base + 3, _base + 7, f'{_base + 3}–{_base + 6}%'),
              (f'{_letter}+', _base + 7, _base + 10, f'{_base + 7}–{_base + 9}%')]
BANDS += [('A−', 90, 93, '90–92%'), ('A', 93, None, '93–100%')]
del _letter, _base

# Canvas's discrimination index compares the top and bottom 27% of the class
# by total score (docs/outputs.md).
DI_GROUP = 0.27


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def _varp(xs: list[float]) -> float:
    """Population variance, Excel's VARP."""
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def _percentile(xs: list[float], p: float) -> float:
    """Excel's PERCENTILE (.INC): linear interpolation at rank p*(n-1)."""
    s = sorted(xs)
    rank = p * (len(s) - 1)
    lo = math.floor(rank)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (rank - lo) * (s[hi] - s[lo])


def summary(totals: list[float]) -> dict:
    """n, mean, median, sample standard deviation (Excel STDEV, n - 1),
    highest, and lowest. None where undefined: everything but n for an empty
    list, and sd for a single score."""
    n = len(totals)
    if not n:
        return dict(n=0, mean=None, median=None, sd=None, highest=None, lowest=None)
    mean = sum(totals) / n
    sd = (math.sqrt(sum((x - mean) ** 2 for x in totals) / (n - 1))
          if n > 1 else None)
    return dict(n=n, mean=mean, median=_median(totals), sd=sd,
                highest=max(totals), lowest=min(totals))


def cronbach_alpha(items: list[list[float | None]], totals: list[float]) -> float | None:
    """k/(k-1) x (1 - the items' summed variances over the totals' variance).
    items[i][s] is student s's points on question i, None where the student
    wasn't given it; like Excel's VARP over a range, an item's variance uses
    only its non-None values. None where Excel would show a blank: fewer than
    two items, totals with no variance, or an item with no values."""
    k = len(items)
    if k < 2 or not totals:
        return None
    var_total = _varp(totals)
    if var_total == 0:
        return None
    item_vars = []
    for col in items:
        vals = [v for v in col if v is not None]
        if not vals:
            return None
        item_vars.append(_varp(vals))
    return k / (k - 1) * (1 - sum(item_vars) / var_total)


def discrimination_index(item: list[float | None], totals: list[float],
                         possible: float) -> float | None:
    """Canvas's index: the item's mean points among students at or above the
    73rd percentile of totals, less its mean among students at or below the
    27th, over the points possible. Ties at a cutoff join the group. The
    percentiles come from every student's total; None values are skipped in
    the means, as AVERAGEIFS does. None where Excel would show a blank."""
    if not totals or not possible:
        return None
    p_hi = _percentile(totals, 1 - DI_GROUP)
    p_lo = _percentile(totals, DI_GROUP)
    upper = [v for v, t in zip(item, totals) if v is not None and t >= p_hi]
    lower = [v for v, t in zip(item, totals) if v is not None and t <= p_lo]
    if not upper or not lower:
        return None
    return (sum(upper) / len(upper) - sum(lower) / len(lower)) / possible


def _cutoff(pct: float, possible: float) -> float:
    """A band's cutoff in points as the gradebook's COUNTIFS sees it: the
    formula joins the cutoff into its criterion as text (">="&0.93*30),
    and Excel writes a number as text to 15 significant digits, so 0.93*30
    is 27.9 there, not 27.900000000000002."""
    return float(f'{pct / 100 * possible:.15g}')


def band_of(total: float, possible: float) -> str | None:
    """The grade band a score falls in, compared the way the gradebook's
    COUNTIFS does, so a score on a cutoff lands where Excel puts it. A
    score above the points possible is an A."""
    for grade, lo, hi, _label in BANDS:
        if lo is not None and not total >= _cutoff(lo, possible):
            continue
        if hi is not None and not total < _cutoff(hi, possible):
            continue
        return grade
    return None


def band_counts(scores: list[tuple[float, float]]) -> dict[str, int]:
    """Students per band from (total, that student's points possible) pairs;
    every band is present, zero if empty."""
    counts = {grade: 0 for grade, *_ in BANDS}
    for total, possible in scores:
        grade = band_of(total, possible)
        if grade is not None:
            counts[grade] += 1
    return counts
