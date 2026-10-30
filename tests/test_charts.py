"""Tests for charts.py: the pure layout math, plus one Tk smoke test."""
from __future__ import annotations

import os
import tkinter as tk
import unittest

import analysis
import charts


class TestTicks(unittest.TestCase):
    def test_choices(self):
        self.assertEqual(charts.nice_ticks(0), [0, 1])
        self.assertEqual(charts.nice_ticks(1), [0, 1])
        self.assertEqual(charts.nice_ticks(5), [0, 1, 2, 3, 4, 5])
        self.assertEqual(charts.nice_ticks(7), [0, 2, 4, 6, 8])
        self.assertEqual(charts.nice_ticks(23), [0, 5, 10, 15, 20, 25])
        self.assertEqual(charts.nice_ticks(140), [0, 50, 100, 150])

    def test_covers_max_and_at_most_six(self):
        for m in range(0, 2000):
            t = charts.nice_ticks(m)
            self.assertLessEqual(len(t), 6)
            self.assertGreaterEqual(t[-1], m)


class TestGeometry(unittest.TestCase):
    def test_bars_inside_and_disjoint(self):
        n = len(analysis.BANDS)
        left, right = 30.0, 412.0
        slots = charts.bar_slots(left, right, n, 2)
        flat = [x for group in slots for x in group]
        self.assertEqual(len(flat), 26)
        for x0, x1 in flat:
            self.assertGreater(x1, x0)
            self.assertGreaterEqual(x0, left)
            self.assertLessEqual(x1, right)
        for (_a0, a1), (b0, _b1) in zip(flat, flat[1:]):
            self.assertLessEqual(a1, b0 + 1e-9)

    def test_bar_top(self):
        self.assertEqual(charts.bar_top(0, 10, 20, 120), 120)
        self.assertEqual(charts.bar_top(10, 10, 20, 120), 20)
        self.assertEqual(charts.bar_top(5, 10, 20, 120), 70)

    def test_legend(self):
        self.assertFalse(charts.show_legend(1))
        self.assertTrue(charts.show_legend(2))

    def test_hit_bar(self):
        slots = charts.bar_slots(0, 100, 2, 2)
        x0, x1 = slots[1][0]
        self.assertEqual(charts.hit_bar((x0 + x1) / 2, 50, slots, 10, 90), (1, 0))
        self.assertIsNone(charts.hit_bar((x0 + x1) / 2, 95, slots, 10, 90))

    def test_fit_font_size(self):
        measure = lambda t, s: len(t) * s
        self.assertEqual(charts.fit_font_size(measure, ['abcd'], 40), 10)
        self.assertEqual(charts.fit_font_size(measure, ['abcd'], 30), 7)
        self.assertIsNone(charts.fit_font_size(measure, ['abcd'], 20))

    def test_choice_rows_and_label(self):
        g = charts.choice_rows(400, 150, 5, 40, 50)
        self.assertGreater(g['full'], 0)
        self.assertLessEqual(g['y0'] + 5 * g['row_h'], 150)
        self.assertEqual(charts.choice_label(7, 20), '7 · 35%')
        self.assertEqual(charts.choice_label(0, 0), '0 · 0%')


def _root():
    try:
        r = tk.Tk()
        r.withdraw()
        return r
    except tk.TclError:
        return None


@unittest.skipUnless(_root() is not None, 'no Tk display')
class TestSmoke(unittest.TestCase):
    def test_widgets_draw(self):
        root = tk.Tk()
        try:
            root.geometry('600x500')
            gc = charts.GradeChart(root)
            gc.pack(fill='both', expand=True)
            cb = charts.ChoiceBars(root)
            cb.pack(fill='both', expand=True)
            cats = [b[0] for b in analysis.BANDS]
            gc.set_data(cats, [('Unadjusted', [1] * 13, charts.UNADJUSTED_COLOR),
                               ('Adjusted', [2] * 13, charts.ADJUSTED_COLOR)])
            cb.set_data([('A', 3), ('B', 7), ('Blank', 0)], {'B'})
            root.update()
            self.assertGreater(len(gc.find_all()), 26)
            self.assertGreater(len(cb.find_all()), 3)
            cb.set_data([], set())
            root.update()
            self.assertEqual(len(cb.find_all()), 1)
        finally:
            root.destroy()

    def test_named_choices_keep_the_bars_room(self):
        """A choice given its text is drawn as letter and text, cut to fit,
        and the bars still have most of the width."""
        root = tk.Tk()
        try:
            root.geometry('520x200')
            cb = charts.ChoiceBars(root)
            cb.pack(fill='both', expand=True)
            long = 'the sarcoplasmic reticulum, which stores calcium ' * 3
            cb.set_data([('A', 3, 'the T tubule'), ('B', 7, long)], {'B'})
            root.update()
            labels = [cb.itemcget(i, 'text') for i in cb.find_all()
                      if cb.type(i) == 'text']
            self.assertIn('A  the T tubule', labels)
            cut = next(t for t in labels if t.startswith('B  the sarcoplasmic'))
            self.assertTrue(cut.endswith('…'))
            self.assertLess(len(cut), len(long))
            bars = [cb.bbox(i) for i in cb.find_all() if cb.type(i) == 'rectangle']
            self.assertTrue(any(b[2] - b[0] > 80 for b in bars))
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
