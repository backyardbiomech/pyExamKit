'''
Exam statistics against the gradebook's Excel formulas. Every expected value
is worked by hand in the comments.

    python -m unittest tests.test_analysis -v
'''
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analysis


class SummaryTests(unittest.TestCase):
    def test_hand_worked(self):
        # [3,7,8,9,10]: mean 37/5 = 7.4; deviations squared sum to 29.2,
        # so sample variance 29.2/4 = 7.3
        s = analysis.summary([3, 7, 8, 9, 10])
        self.assertEqual(s['n'], 5)
        self.assertAlmostEqual(s['mean'], 7.4)
        self.assertEqual(s['median'], 8)
        self.assertAlmostEqual(s['sd'], math.sqrt(7.3))
        self.assertEqual((s['highest'], s['lowest']), (10, 3))

    def test_even_count_median(self):
        self.assertEqual(analysis.summary([1, 2, 3, 10])['median'], 2.5)

    def test_single_score_has_no_sd(self):
        s = analysis.summary([4])
        self.assertIsNone(s['sd'])
        self.assertEqual(s['mean'], 4)

    def test_empty(self):
        s = analysis.summary([])
        self.assertEqual(s['n'], 0)
        self.assertTrue(all(s[k] is None for k in
                            ('mean', 'median', 'sd', 'highest', 'lowest')))


class AlphaTests(unittest.TestCase):
    def test_perfectly_consistent_items(self):
        # items identical, totals [2,2,0,0]: VARP totals 1, each item .25,
        # alpha = 2/1 x (1 - .5/1) = 1
        item = [1, 1, 0, 0]
        self.assertAlmostEqual(
            analysis.cronbach_alpha([item, item], [2, 2, 0, 0]), 1.0)

    def test_independent_items(self):
        # [1,0,1,0] and [1,1,0,0]: totals [2,1,1,0] VARP .5; items .25 each
        # alpha = 2 x (1 - .5/.5) = 0
        self.assertAlmostEqual(analysis.cronbach_alpha(
            [[1, 0, 1, 0], [1, 1, 0, 0]], [2, 1, 1, 0]), 0.0)

    def test_blank_cells_skipped_in_item_variance(self):
        # item 2 has values [1,1] only: VARP 0, so sum of item variances is
        # .25 and alpha = 2 x (1 - .25/1) = 1.5
        self.assertAlmostEqual(analysis.cronbach_alpha(
            [[1, 1, 0, 0], [1, 1, None, None]], [2, 2, 0, 0]), 1.5)

    def test_undefined_cases(self):
        self.assertIsNone(analysis.cronbach_alpha([[1, 0]], [1, 0]))   # k < 2
        self.assertIsNone(analysis.cronbach_alpha([[1, 1], [0, 0]], [1, 1]))  # VARP 0
        self.assertIsNone(analysis.cronbach_alpha([[1, 0], [None, None]], [1, 0]))
        self.assertIsNone(analysis.cronbach_alpha([], []))


class DiscriminationTests(unittest.TestCase):
    def test_hand_worked(self):
        # totals [3,7,8,9,10]: P73 at rank 2.92 = 8 + .92 = 8.92, P27 at rank
        # 1.08 = 7 + .08 = 7.08. Upper group: totals 9 and 10. Lower: 3 and 7.
        # item [1,1,2,3,4]: upper mean 3.5, lower mean 1, (3.5-1)/4 = .625
        self.assertAlmostEqual(analysis.discrimination_index(
            [1, 1, 2, 3, 4], [3, 7, 8, 9, 10], 4), 0.625)

    def test_ties_at_cutoff_join_the_group(self):
        # totals [2,4,4,4,6]: both percentiles are 4, so the three 4s are in
        # both groups. Item [0,1,1,0,3]: upper (4,4,4,6) mean 5/4 = 1.25,
        # lower (2,4,4,4) mean 2/4 = .5; (1.25-.5)/3 = .25
        self.assertAlmostEqual(analysis.discrimination_index(
            [0, 1, 1, 0, 3], [2, 4, 4, 4, 6], 3), 0.25)

    def test_none_items_skipped(self):
        # as above, but the first student was not given the question: lower
        # group is (1,1,0) mean 2/3; (1.25 - 2/3)/3
        self.assertAlmostEqual(analysis.discrimination_index(
            [None, 1, 1, 0, 3], [2, 4, 4, 4, 6], 3), (1.25 - 2 / 3) / 3)

    def test_all_equal_class(self):
        # every student is in both groups: no difference
        self.assertEqual(analysis.discrimination_index(
            [1, 2, 3], [5, 5, 5], 3), 0)

    def test_empty_group_is_blank(self):
        # totals [1..5]: P73 = 3.92, P27 = 2.08; upper group is students 4
        # and 5, who were not given the question
        self.assertIsNone(analysis.discrimination_index(
            [1, 1, None, None, None], [1, 2, 3, 4, 5], 1))

    def test_zero_possible_or_no_students(self):
        self.assertIsNone(analysis.discrimination_index([1, 2], [1, 2], 0))
        self.assertIsNone(analysis.discrimination_index([], [], 1))

    def test_single_student(self):
        # both percentiles are that student's total
        self.assertEqual(analysis.discrimination_index([2], [5], 2), 0)


class BandTests(unittest.TestCase):
    def test_bands_unchanged_in_shape(self):
        self.assertEqual(len(analysis.BANDS), 13)
        self.assertEqual(analysis.BANDS[0][:3], ('Low F', None, 50))
        self.assertEqual(analysis.BANDS[-1][:3], ('A', 93, None))

    def test_boundaries_out_of_100(self):
        for total, grade in [(0, 'Low F'), (49.9, 'Low F'), (50, 'Close F'),
                             (59.9, 'Close F'), (60, 'D−'), (82.9, 'B−'),
                             (83, 'B'), (86.9, 'B'), (87, 'B+'),
                             (92.9, 'A−'), (93, 'A'), (100, 'A')]:
            self.assertEqual(analysis.band_of(total, 100), grade, total)

    def test_score_above_possible_is_an_A(self):
        self.assertEqual(analysis.band_of(120, 100), 'A')

    def test_scales_with_own_possible(self):
        # 50 possible: 83% is 41.5, so 41 is a B− and 41.5 a B
        self.assertEqual(analysis.band_of(41, 50), 'B−')
        self.assertEqual(analysis.band_of(41.5, 50), 'B')

    def test_counts_include_every_band(self):
        counts = analysis.band_counts([(93, 100), (95, 100), (82.9, 100),
                                       (41, 50), (10, 100)])
        self.assertEqual(list(counts), [b[0] for b in analysis.BANDS])
        self.assertEqual(counts['A'], 2)
        self.assertEqual(counts['B−'], 2)
        self.assertEqual(counts['Low F'], 1)
        self.assertEqual(sum(counts.values()), 5)
        self.assertEqual(sum(analysis.band_counts([]).values()), 0)

    def test_cutoff_rounded_as_excel_writes_it(self):
        # 0.93 * 30 is 27.900000000000002 in a double; the gradebook's
        # criterion is the text "27.9", so 27.9 out of 30 is an A
        self.assertEqual(analysis.band_of(27.9, 30), 'A')


if __name__ == '__main__':
    unittest.main()
