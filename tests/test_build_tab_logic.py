"""
Phase 3 verification: build_tab.py's widget-free logic. This session's Tk
install can't create a live root (same broken Tcl/Tk phase 1 hit), so the
widget class itself can't be driven here -- these tests cover the pure
functions that hold every actual rule (validation order and wording, pool
totals arithmetic, BuildConfig field mapping), which is everything that
can go subtly wrong in a transcription like this one. Clicking through the
real tab is still Brandon's job.
"""
import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path

from exam_builder import BuildConfig, ExamBuilder
from exam_config import load_config, load_versions, save_config
from exam_key_writer import build_key_data
from build_tab import (
    compute_pool_totals,
    config_file,
    previous_build_files,
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

    def test_reprint_needs_no_source_files(self):
        msg = validate_build_fields(title='Exam 1', output_folder='/tmp', mode='exact',
                                     exact_path=MISSING_FILE, pool_rows=[], reprint=True)
        self.assertIsNone(msg)

    def test_previous_build_files_are_only_what_a_build_writes(self):
        out = tempfile.mkdtemp(prefix='existing_exam_')
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        folder = Path(out) / 'Exam_1'
        (folder / 'images').mkdir(parents=True)
        written = ['Exam_1_vA.html', 'Exam_1_vA_large.html', 'Exam_1_vA.md',
                   'Exam_1_vA_key.csv', 'Exam_1_vC_key.csv', 'Exam_1.exam.json']
        kept = ['bank.txt', 'Exam_1_notes.md', 'images/cell.png']
        for name in written + kept:
            (folder / name).write_text('x', encoding='utf-8')
        found = previous_build_files(out, ' Exam 1 ')
        self.assertEqual(sorted(p.name for p in found), sorted(written))
        self.assertEqual(config_file(out, 'Exam 1'), folder / 'Exam_1.exam.json')

    def test_reprint_still_needs_title_and_output_folder(self):
        msg = validate_build_fields(title=' ', output_folder='/tmp', mode='pools',
                                     exact_path='', pool_rows=[], reprint=True)
        self.assertEqual(msg, "Please enter an exam title.")
        msg = validate_build_fields(title='Exam 1', output_folder='', mode='pools',
                                     exact_path='', pool_rows=[], reprint=True)
        self.assertEqual(msg, "Please select an output folder.")

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

    def test_font_size_passes_through(self):
        config = build_config_from_fields(**self._base_kwargs(font_size='larger'))
        self.assertEqual(config.font_size, 'larger')

    def test_font_size_defaults_to_medium(self):
        self.assertEqual(build_config_from_fields(**self._base_kwargs()).font_size, 'medium')


class FontSizeInSavedConfig(unittest.TestCase):
    """A saved .exam.json carries the font size. One saved before the
    setting existed, or naming a size this version does not know, loads as
    medium rather than failing."""

    def setUp(self):
        tmpdir = Path(tempfile.mkdtemp(prefix='exam_config_test_'))
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        self.path = tmpdir / 'Exam_1.exam.json'
        self.folder = tmpdir

    def _save(self, **fields):
        config = BuildConfig(title='Exam 1', course='BIOL 101', num_versions=1,
                             shuffle_questions=False, shuffle_answers=False,
                             exact_file=Path(FIXTURE_BANK), **fields)
        save_config(config, self.folder, self.path)

    def test_round_trip(self):
        self._save(font_size='small')
        config, _ = load_config(self.path)
        self.assertEqual(config.font_size, 'small')

    def test_missing_or_unknown_size_loads_as_medium(self):
        self._save(font_size='large')
        data = json.loads(self.path.read_text(encoding='utf-8'))
        for value in (None, 'huge'):
            with self.subTest(font_size=value):
                if value is None:
                    data.pop('font_size', None)
                else:
                    data['font_size'] = value
                self.path.write_text(json.dumps(data), encoding='utf-8')
                config, _ = load_config(self.path)
                self.assertEqual(config.font_size, 'medium')


class SavedExamInConfig(unittest.TestCase):
    """Generate records the built exam in the config it saves, so the exam
    can be reprinted later, at another font size, with the same answer keys."""

    @classmethod
    def setUpClass(cls):
        random.seed(7)
        # Every question type the fixture has, shuffled, plus the synthetic
        # version question, so nothing the snapshot must carry is left out.
        cls.config = BuildConfig(title='Exam 1', course='BIOL 101', num_versions=2,
                                 shuffle_questions=True, shuffle_answers=True,
                                 exact_file=Path(FIXTURE_BANK), version_question=True)
        cls.versions, _ = ExamBuilder().build(cls.config)

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='saved_exam_test_'))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.path = self.folder / 'Exam_1.exam.json'

    def test_versions_round_trip_exactly(self):
        save_config(self.config, self.folder, self.path, self.versions)
        self.assertEqual(load_versions(self.path), self.versions)

    def test_reloaded_exam_writes_the_same_keys(self):
        save_config(self.config, self.folder, self.path, self.versions)
        for original, reloaded in zip(self.versions, load_versions(self.path)):
            self.assertEqual(build_key_data(reloaded, 1.0), build_key_data(original, 1.0))

    def test_settings_only_config_has_no_saved_exam(self):
        save_config(self.config, self.folder, self.path)
        self.assertEqual(load_versions(self.path), [])


class VersionPositionMapping(unittest.TestCase):
    def test_labels_and_values_are_inverse(self):
        self.assertEqual(VERSION_POSITION_LABELS['at end of exam'], 'last')
        self.assertEqual(VERSION_POSITION_LABELS['at start of exam'], 'first')
        self.assertEqual(VERSION_POSITION_VALUES['last'], 'at end of exam')
        self.assertEqual(VERSION_POSITION_VALUES['first'], 'at start of exam')


if __name__ == '__main__':
    unittest.main()
