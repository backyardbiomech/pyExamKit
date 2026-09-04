"""
Tests for keyformat.py, the shared exam-key CSV reader/writer.

Run with:
    python -m unittest tests.test_keyformat -v

Covers the two behaviors phase 1 of the merge plan exists to guarantee:
  1. Both the nine-column (scanner-written, BOM'd) and ten-column
     (pyExamPaper-written, plain UTF-8) key CSV layouts load correctly.
  2. A key loaded and re-saved keeps every bubble answer, open question,
     and per-question point value it started with — no silent data loss
     on the load -> edit -> save round trip the GUI dialogs perform.
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import keyformat

FIXTURES = Path(__file__).resolve().parent
NINE_COL_FIXTURE = FIXTURES / 'testkey.csv'
NINE_COL_OPEN_ONLY_FIXTURE = FIXTURES / 'practicaltest' / 'Practical_3_key_AB.csv'
TEN_COL_FIXTURE = FIXTURES / 'ten_column_key.csv'


class LoadNineColumnFixture(unittest.TestCase):
    """The legacy scanner-written format: nine columns, BOM, no points."""

    def test_loads_without_error(self):
        data = keyformat.load_key_csv(str(NINE_COL_FIXTURE))
        self.assertIsNotNone(data)

    def test_bubble_and_open_answers(self):
        data = keyformat.load_key_csv(str(NINE_COL_FIXTURE))
        self.assertEqual(data['bubble_answers']['Q001'], 'B')
        self.assertEqual(data['bubble_answers']['Q002'], 'AC')
        self.assertEqual(data['bubble_answers']['Q004'], 'ABCDEF')
        self.assertEqual(data['bubble_answers']['Q005'], 'ignore')
        self.assertEqual(len(data['bubble_answers']), 10)
        self.assertEqual(data['open_questions']['openQ_5']['full'], ['peristalsis'])
        self.assertEqual(data['open_questions']['openQ_5']['partial'], ['paristalsis'])
        # Pipe-separated multi-answer full-credit list
        self.assertEqual(
            data['open_questions']['openQ_10']['full'],
            ['plasma oxygen partial pressure (mmHg)', 'pO2 (mmHg)'],
        )

    def test_metadata(self):
        data = keyformat.load_key_csv(str(NINE_COL_FIXTURE))
        self.assertEqual(data['metadata']['num_questions'], 10)
        self.assertEqual(data['metadata']['questions_to_skip'], '5,10,11')

    def test_no_points_column_means_no_point_values(self):
        data = keyformat.load_key_csv(str(NINE_COL_FIXTURE))
        self.assertNotIn('point_values', data)


class LoadNineColumnOpenOnlyFixture(unittest.TestCase):
    """A second real nine-column key: all-open (lab practical), BOM present."""

    def test_loads_all_fifty_open_questions(self):
        data = keyformat.load_key_csv(str(NINE_COL_OPEN_ONLY_FIXTURE))
        self.assertIsNotNone(data)
        self.assertEqual(len(data['bubble_answers']), 0)
        self.assertEqual(len(data['open_questions']), 50)
        self.assertEqual(data['open_questions']['openQ_1']['full'], ['renal pelvis'])
        self.assertEqual(data['open_questions']['openQ_1']['coords'], [130, 616, 624, 690])


class LoadTenColumnFixture(unittest.TestCase):
    """The pyExamPaper-written format: ten columns, plain UTF-8, points present."""

    def test_loads_without_error(self):
        data = keyformat.load_key_csv(str(TEN_COL_FIXTURE))
        self.assertIsNotNone(data)

    def test_point_values_present(self):
        data = keyformat.load_key_csv(str(TEN_COL_FIXTURE))
        self.assertIn('point_values', data)
        self.assertEqual(data['point_values']['Q001'], 2.0)
        self.assertEqual(data['point_values']['Q003'], 1.5)
        self.assertEqual(data['point_values']['openQ_6'], 3.0)
        # The 'ignore' bubble row (Q006, the SA placeholder) has a blank
        # points cell and must not appear in point_values at all.
        self.assertNotIn('Q006', data['point_values'])

    def test_bubble_and_open_answers(self):
        data = keyformat.load_key_csv(str(TEN_COL_FIXTURE))
        self.assertEqual(data['bubble_answers']['Q001'], 'A')
        self.assertEqual(data['bubble_answers']['Q002'], 'BD')
        self.assertEqual(data['bubble_answers']['Q006'], 'ignore')
        self.assertEqual(
            data['open_questions']['openQ_6']['full'],
            ['sample answer', 'alt answer'],
        )
        self.assertEqual(data['open_questions']['openQ_6']['partial'], ['close variant'])


class RoundTrip(unittest.TestCase):
    """load -> save -> reload must reproduce the same data, for every fixture.

    This is the regression test for the bug phase 1 exists to fix: opening a
    key in the scanner's editor and saving it used to silently drop every
    per-question point value, because the old save_key_csv never wrote a
    points column at all. It should now come back exactly.
    """

    def _round_trip(self, fixture_path: Path) -> tuple[dict, dict, Path]:
        original = keyformat.load_key_csv(str(fixture_path))
        self.assertIsNotNone(original, f'{fixture_path} failed to load')
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / 'roundtrip.csv'
            keyformat.save_key_csv(str(out_path), original)
            reloaded = keyformat.load_key_csv(str(out_path))
            # Read header + encoding before the tempdir is cleaned up.
            with open(out_path, 'rb') as fh:
                raw = fh.read()
        return original, reloaded, raw

    def test_nine_column_fixture_round_trips(self):
        original, reloaded, raw = self._round_trip(NINE_COL_FIXTURE)
        self.assertEqual(original['bubble_answers'], reloaded['bubble_answers'])
        self.assertEqual(original['open_questions'], reloaded['open_questions'])
        self.assertEqual(original.get('metadata'), reloaded.get('metadata'))
        # Source had no points column, so there is nothing to preserve —
        # confirm the round trip doesn't fabricate any.
        self.assertNotIn('point_values', reloaded)

    def test_open_only_fixture_round_trips(self):
        original, reloaded, raw = self._round_trip(NINE_COL_OPEN_ONLY_FIXTURE)
        self.assertEqual(original['open_questions'], reloaded['open_questions'])
        self.assertEqual(original.get('metadata'), reloaded.get('metadata'))

    def test_ten_column_fixture_round_trips_with_points(self):
        original, reloaded, raw = self._round_trip(TEN_COL_FIXTURE)
        self.assertEqual(original['bubble_answers'], reloaded['bubble_answers'])
        self.assertEqual(original['open_questions'], reloaded['open_questions'])
        self.assertEqual(original.get('metadata'), reloaded.get('metadata'))
        # The actual bug: points must survive the round trip.
        self.assertEqual(original['point_values'], reloaded['point_values'])

    def test_written_file_is_always_ten_columns(self):
        for fixture in (NINE_COL_FIXTURE, NINE_COL_OPEN_ONLY_FIXTURE, TEN_COL_FIXTURE):
            _, _, raw = self._round_trip(fixture)
            header = raw.decode('utf-8').splitlines()[0]
            self.assertEqual(header.split(','), keyformat.KEY_CSV_HEADER,
                             f'{fixture.name} did not round-trip to the canonical header')

    def test_written_file_has_no_bom(self):
        for fixture in (NINE_COL_FIXTURE, NINE_COL_OPEN_ONLY_FIXTURE, TEN_COL_FIXTURE):
            _, _, raw = self._round_trip(fixture)
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'),
                             f'{fixture.name} round-tripped to a file with a BOM')


class DialogRoundTripSimulation(unittest.TestCase):
    """Simulate the exact bug scenario from HANDOFF.md: build an exam with
    per-pool points (a pyExamPaper-style ten-column key), open it in the
    scanner's open-question editor, save, and confirm points survive.

    This exercises the KeyFileEditorDialog / KeyBuilderDialog fix directly,
    without needing a Tk display: both dialogs now capture
    data.get('point_values', {}) into self._point_values on load and put it
    back in the dict handed to save_key_file — this reproduces that shape by
    hand rather than instantiating the Tk dialog.
    """

    def test_editor_dialog_shape_preserves_points(self):
        original = keyformat.load_key_csv(str(TEN_COL_FIXTURE))
        # What KeyFileEditorDialog.__init__ now captures into self._point_values.
        point_values = dict(original.get('point_values', {}))
        # What KeyFileEditorDialog._to_data() now returns (bubble/open editable,
        # point_values carried through unedited since there is no points UI).
        rebuilt = {
            'bubble_answers': dict(original['bubble_answers']),
            'open_questions': dict(original['open_questions']),
            'metadata': dict(original.get('metadata', {})),
            'point_values': point_values,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / 'edited.csv'
            keyformat.save_key_csv(str(out_path), rebuilt)
            reloaded = keyformat.load_key_csv(str(out_path))
        self.assertEqual(reloaded['point_values'], original['point_values'])


if __name__ == '__main__':
    unittest.main()
