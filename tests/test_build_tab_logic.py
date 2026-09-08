"""
Phase 3 verification: build_tab.py's widget-free logic. This session's Tk
install can't create a live root (same broken Tcl/Tk phase 1 hit), so the
widget class itself can't be driven here -- these tests cover the pure
functions that hold every actual rule (validation order and wording, pool
totals arithmetic, BuildConfig field mapping), which is everything that
can go subtly wrong in a transcription like this one. Clicking through the
real tab is still Brandon's job.
"""
import unittest
from pathlib import Path

from build_tab import (
    compute_pool_totals,
    validate_build_fields,
    build_config_from_fields,
    VERSION_POSITION_LABELS,
    VERSION_POSITION_VALUES,
)

FIXTURE_BANK = str(Path(__file__).parent / 'fixtures' / 'build_migration' / 'input' / 'bank1.txt')
MISSING_FILE = str(Path(__file__).parent / 'fixtures' / 'build_migration' / 'input' / 'nope.txt')


class ComputePoolTotals(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(compute_pool_totals([], 1.0), (0, 0.0))

    def test_uses_default_points_when_blank(self):
        rows = [{'count_text': '10', 'points_text': ''}]
        self.assertEqual(compute_pool_totals(rows, 2.0), (10, 20.0))

    def test_row_points_override_default(self):
        rows = [{'count_text': '10', 'points_text': '3.0'}]
        self.assertEqual(compute_pool_totals(rows, 1.0), (10, 30.0))

    def test_bad_count_falls_back_to_ten(self):
        rows = [{'count_text': 'abc', 'points_text': ''}]
        self.assertEqual(compute_pool_totals(rows, 1.0), (10, 10.0))

    def test_bad_points_falls_back_to_default(self):
        rows = [{'count_text': '5', 'points_text': 'abc'}]
        self.assertEqual(compute_pool_totals(rows, 2.0), (5, 10.0))

    def test_multiple_rows_sum(self):
        rows = [{'count_text': '5', 'points_text': '1.0'},
                {'count_text': '5', 'points_text': '2.0'}]
        self.assertEqual(compute_pool_totals(rows, 1.0), (10, 15.0))


class ValidateBuildFields(unittest.TestCase):
    def test_blank_title(self):
        msg = validate_build_fields(title='  ', output_folder='/tmp', mode='exact',
                                     exact_path=FIXTURE_BANK, pool_rows=[])
        self.assertEqual(msg, "Please enter an exam title.")

    def test_blank_output_folder(self):
        msg = validate_build_fields(title='Exam 1', output_folder=' ', mode='exact',
                                     exact_path=FIXTURE_BANK, pool_rows=[])
        self.assertEqual(msg, "Please select an output folder.")

    def test_exact_mode_blank_path(self):
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='exact',
                                     exact_path='  ', pool_rows=[])
        self.assertEqual(msg, "Please select a question file.")

    def test_exact_mode_missing_file(self):
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='exact',
                                     exact_path=MISSING_FILE, pool_rows=[])
        self.assertEqual(msg, f"File not found:\n{MISSING_FILE}")

    def test_exact_mode_valid_passes(self):
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='exact',
                                     exact_path=FIXTURE_BANK, pool_rows=[])
        self.assertIsNone(msg)

    def test_pools_mode_invalid_points_named_by_file(self):
        rows = [{'filepath': FIXTURE_BANK, 'count_text': '10', 'points_text': 'abc'}]
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='pools',
                                     exact_path='', pool_rows=rows)
        self.assertEqual(
            msg,
            'Invalid Pts/Q value "abc" for:\nbank1.txt\n\n'
            'Enter a number or leave blank to use the global default.',
        )

    def test_pools_mode_empty_pools(self):
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='pools',
                                     exact_path='', pool_rows=[])
        self.assertEqual(msg, "Please add at least one pool file.")

    def test_pools_mode_missing_pool_file(self):
        rows = [{'filepath': MISSING_FILE, 'count_text': '10', 'points_text': ''}]
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='pools',
                                     exact_path='', pool_rows=rows)
        self.assertEqual(msg, f"Pool file not found:\n{MISSING_FILE}")

    def test_pools_mode_count_below_one(self):
        rows = [{'filepath': FIXTURE_BANK, 'count_text': '0', 'points_text': ''}]
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='pools',
                                     exact_path='', pool_rows=rows)
        self.assertEqual(msg, "Question count must be ≥ 1 for:\nbank1.txt")

    def test_pools_mode_valid_passes(self):
        rows = [{'filepath': FIXTURE_BANK, 'count_text': '10', 'points_text': '1.0'}]
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='pools',
                                     exact_path='', pool_rows=rows)
        self.assertIsNone(msg)

    def test_points_checked_before_empty_pools(self):
        """A non-empty but all-invalid-points pool list should report the
        Pts/Q error, not fall through to 'add at least one pool file' --
        matches the original's check ordering (Pts/Q pass runs over all
        rows before the empty-pools check)."""
        rows = [{'filepath': FIXTURE_BANK, 'count_text': '10', 'points_text': 'xyz'}]
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='pools',
                                     exact_path='', pool_rows=rows)
        self.assertIn('Invalid Pts/Q value', msg)


class BuildConfigFromFields(unittest.TestCase):
    def _base_kwargs(self, **overrides):
        kwargs = dict(
            title='Exam 1', course='BIOL 101', num_versions=2,
            shuffle_questions=True, shuffle_answers=False,
            mode='exact', exact_path=FIXTURE_BANK, pool_rows=[],
            version_question=True, version_question_position='last',
            default_points=1.5, same_questions=False,
        )
        kwargs.update(overrides)
        return kwargs

    def test_exact_mode_fields(self):
        config = build_config_from_fields(**self._base_kwargs())
        self.assertEqual(config.title, 'Exam 1')
        self.assertEqual(config.exact_file, Path(FIXTURE_BANK))
        self.assertEqual(config.pools, [])
        self.assertEqual(config.num_versions, 2)
        self.assertTrue(config.shuffle_questions)
        self.assertFalse(config.shuffle_answers)

    def test_blank_title_falls_back_to_untitled(self):
        config = build_config_from_fields(**self._base_kwargs(title='   '))
        self.assertEqual(config.title, 'Untitled')

    def test_pools_mode_builds_pool_configs(self):
        rows = [
            {'filepath': FIXTURE_BANK, 'count_text': '5', 'points_text': '2.0'},
            {'filepath': FIXTURE_BANK, 'count_text': 'bad', 'points_text': ''},
        ]
        config = build_config_from_fields(**self._base_kwargs(mode='pools', pool_rows=rows))
        self.assertIsNone(config.exact_file)
        self.assertEqual(len(config.pools), 2)
        self.assertEqual(config.pools[0].count, 5)
        self.assertEqual(config.pools[0].points, 2.0)
        self.assertEqual(config.pools[1].count, 10)  # bad text -> falls back to 10
        self.assertIsNone(config.pools[1].points)     # blank -> None, uses global default

    def test_blank_exact_path_becomes_none_not_dot(self):
        config = build_config_from_fields(**self._base_kwargs(exact_path='  '))
        self.assertIsNone(config.exact_file)


class VersionPositionMapping(unittest.TestCase):
    def test_labels_and_values_are_inverse(self):
        self.assertEqual(VERSION_POSITION_LABELS['at end of exam'], 'last')
        self.assertEqual(VERSION_POSITION_LABELS['at start of exam'], 'first')
        self.assertEqual(VERSION_POSITION_VALUES['last'], 'at end of exam')
        self.assertEqual(VERSION_POSITION_VALUES['first'], 'at start of exam')


if __name__ == '__main__':
    unittest.main()
