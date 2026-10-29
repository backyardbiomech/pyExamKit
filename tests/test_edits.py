'''
The edit layer: key changes, credit, overrides and adjustments, kept in
app_data/edits.json and applied to the results whenever the gradebook and
Canvas file are written. The raw results are never changed.

    python -m unittest tests.test_edits -v
'''
import contextlib
import csv
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import edits  # noqa: E402
import grade_functions  # noqa: E402
import outputs  # noqa: E402

# Two versions of a three-question exam, the same bank questions shuffled.
# Each student row: last name, ID, answers to Q001..Q003.
VERSIONS = {
    'A': {'key': ['A', 'B', 'C'], 'sources': ['bank.md#1', 'bank.md#2', 'bank.md#3'],
          'students': [('AMES', '1', ['A', 'B', 'C']), ('BELL', '2', ['A', 'C', 'C']),
                       ('COLE', '3', ['B', 'C', 'D'])]},
    'B': {'key': ['C', 'A', 'B'], 'sources': ['bank.md#3', 'bank.md#1', 'bank.md#2'],
          'students': [('DART', '4', ['C', 'A', 'B']), ('EGAN', '5', ['C', 'A', 'C'])]},
}
QS = ['Q001', 'Q002', 'Q003']


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def make_outputs(root: Path) -> tuple[Path, list[Path]]:
    """An outputs folder holding VERSIONS graded, as a scan leaves it."""
    out = root / 'ExamScanner_outputs'
    (out / 'marked').mkdir(parents=True)
    csvs = []
    for v, spec in VERSIONS.items():
        rows = [['0', 'KEY', '', ''] + spec['key']]
        rows += [[str(i), last, 'X', sid] + ans
                 for i, (last, sid, ans) in enumerate(spec['students'], 1)]
        path = Path(outputs.results_csv(out, v))
        pd.DataFrame(rows, columns=['index', 'LastName', 'FirstName', 'studentID'] + QS
                     ).to_csv(path, index=False)
        quiet(grade_functions.gradeResults, str(path), False, False, 1, 2,
              out / 'marked', key_data={
                  'metadata': {'title': 'Quiz'},
                  'sources': dict(zip(QS, spec['sources'])),
                  'texts': {q: f'Question from {src}: a stem long enough to wrap onto '
                               'several lines of the Results tab' for q, src in zip(QS, spec['sources'])}})
        csvs.append(path)
    quiet(outputs.record, out, csvs)
    return out, csvs


class EditsTest(unittest.TestCase):
    def setUp(self):
        self.out, self.csvs = make_outputs(Path(tempfile.mkdtemp()))

    def tearDown(self):
        shutil.rmtree(self.out.parent)

    def graded(self):
        return {g.version: g for g in (outputs.load(p) for p in self.csvs)}

    def applied(self, *made):
        out, problems = edits.apply(list(self.graded().values()), list(made))
        return {g.version: g for g in out}, problems

    def canvas(self, *made):
        edits.save(self.out, list(made))
        quiet(outputs.write, self.out, prefix='L')
        rows = list(csv.reader((self.out / outputs.CANVAS).open()))
        return {r[1]: float(r[2]) for r in rows[2:]}, rows[1][2]

    # ── apply ──────────────────────────────────────────────────────────────

    def test_settings_recorded_for_rescoring(self):
        self.assertEqual(self.graded()['A'].settings,
                         {'partial': False, 'strictness': 0.5, 'bubble_points': 1,
                          'written_points': 2})

    def test_key_change_rescores_the_question(self):
        g, problems = self.applied(edits.make('key', version='A', question='Q002', keys=['C']))
        self.assertEqual(problems, [])
        self.assertEqual([g['A'].earned(r, 'Q002') for r in g['A'].students], [0, 1, 1])
        self.assertEqual(g['A'].key_label('Q002'), 'C')

    def test_also_accept_keeps_the_original_key(self):
        g, _ = self.applied(edits.make('key', version='A', question='Q002', keys=['C'],
                                       also=True))
        self.assertEqual([g['A'].earned(r, 'Q002') for r in g['A'].students], [1, 1, 1])
        self.assertEqual(g['A'].key_label('Q002'), 'B or C')

    def test_key_by_bank_question_in_each_sheets_letters(self):
        graded = self.graded()
        # Version B printed bank.md#2 as its Q003 with the choices shuffled:
        # its A, B, C are the bank's C, A, B, so the bank's B is its C
        graded['B'].choices['Q003'] = 'CAB'
        out, problems = edits.apply(list(graded.values()),
                                    [edits.make('key', source='bank.md#2', keys=['B'])])
        g = {g.version: g for g in out}
        self.assertEqual(problems, [])
        self.assertEqual(g['A'].key_label('Q002'), 'B')
        self.assertEqual(g['B'].key_label('Q003'), 'C')
        self.assertEqual([g['B'].earned(r, 'Q003') for r in g['B'].students], [0, 1])

    def test_full_credit_by_bank_question_reaches_every_version(self):
        g, _ = self.applied(edits.make('credit', source='bank.md#3', action='full'))
        self.assertEqual([g['A'].earned(r, 'Q003') for r in g['A'].students], [1, 1, 1])
        self.assertEqual([g['B'].earned(r, 'Q001') for r in g['B'].students], [1, 1])
        self.assertEqual(g['A'].points_possible(), 3)

    def test_drop_takes_it_out_of_the_points_possible(self):
        g, _ = self.applied(edits.make('credit', version='A', question='Q001', action='drop'))
        self.assertEqual(g['A'].points_possible(), 2)
        self.assertEqual(g['A'].total('1'), 2)
        self.assertIn('Q001', g['A'].dropped)
        self.assertEqual(g['B'].points_possible(), 3)

    def test_new_point_value_scales_what_was_earned(self):
        g, _ = self.applied(edits.make('credit', version='B', question='Q003', action='points',
                                       points=4))
        self.assertEqual([g['B'].earned(r, 'Q003') for r in g['B'].students], [4, 0])
        self.assertEqual(g['B'].points_possible(), 6)

    def test_override_checks_the_student(self):
        good = edits.make('override', version='A', row='2', student_id='2', question='Q002',
                          points=0.5)
        wrong = edits.make('override', version='A', row='3', student_id='99', question='Q002',
                           points=1)
        g, problems = self.applied(good, wrong)
        self.assertEqual(g['A'].earned('2', 'Q002'), 0.5)
        self.assertEqual(g['A'].earned('3', 'Q002'), 0)
        self.assertEqual(len(problems), 1)
        self.assertIn(wrong['id'], problems[0])

    def test_override_wins_over_a_key_change(self):
        g, _ = self.applied(
            edits.make('override', version='A', row='1', student_id='1', question='Q002',
                       points=0.25),
            edits.make('key', version='A', question='Q002', keys=['C']))
        self.assertEqual(g['A'].earned('1', 'Q002'), 0.25)

    def test_the_results_are_left_alone(self):
        before = {v: (p.read_text(), outputs.points_csv(p).read_text())
                  for v, p in zip('AB', self.csvs)}
        graded = list(self.graded().values())
        edits.apply(graded, [edits.make('key', version='A', question='Q001', keys=['D'])])
        self.assertEqual(graded[0].earned('1', 'Q001'), 1)
        self.canvas(edits.make('key', version='A', question='Q001', keys=['D']))
        self.assertEqual({v: (p.read_text(), outputs.points_csv(p).read_text())
                          for v, p in zip('AB', self.csvs)}, before)

    def test_results_from_before_settings_were_recorded(self):
        rec_path = outputs.grading_json(self.csvs[0])
        rec = json.loads(rec_path.read_text())
        del rec['settings']
        rec_path.write_text(json.dumps(rec))
        g, _ = self.applied(edits.make('key', version='A', question='Q002', keys=['C']))
        self.assertEqual([g['A'].earned(r, 'Q002') for r in g['A'].students], [0, 1, 1])

    # ── the files written ─────────────────────────────────────────────────

    def test_canvas_file_carries_every_edit(self):
        scores, possible = self.canvas()
        self.assertEqual(scores, {'L1': 3, 'L2': 2, 'L3': 0, 'L4': 3, 'L5': 2})
        scores, possible = self.canvas(
            edits.make('key', version='A', question='Q002', keys=['C'], also=True),
            edits.make('adjust', version='', points=1),
            edits.make('adjust', version='B', points=5),
            edits.make('adjust', version='B', points=0.5))
        self.assertEqual(scores, {'L1': 4, 'L2': 4, 'L3': 2, 'L4': 4.5, 'L5': 3.5})
        self.assertEqual(possible, '3')

    def test_gradebook_starts_from_the_adjustments(self):
        import openpyxl
        self.canvas(edits.make('adjust', version='', points=1),
                    edits.make('adjust', version='B', points=2),
                    edits.make('credit', version='A', question='Q001', action='drop'))
        wb = openpyxl.load_workbook(self.out / outputs.GRADEBOOK)
        row = [c.value for c in wb['Exam stats'][outputs.ADJUST_ROW]][:4]
        self.assertEqual(row, ['Points added', 1, 0, 2])
        self.assertEqual(wb['Version A'].cell(row=1, column=4).value, 'Q001\n(dropped)')

    def test_export_recorded(self):
        self.assertFalse(edits.unexported(self.out))
        made = [edits.make('adjust', version='', points=1)]
        edits.save(self.out, made)
        self.assertTrue(edits.unexported(self.out))
        self.assertTrue(quiet(outputs.write, self.out, prefix='L'))
        self.assertFalse(edits.unexported(self.out))
        # A note is not something to export; a change is
        edits.save(self.out, [{**made[0], 'note': 'curve'}])
        self.assertFalse(edits.unexported(self.out))
        edits.save(self.out, [])
        self.assertTrue(edits.unexported(self.out))

    def test_a_file_that_cannot_be_saved_is_not_exported(self):
        edits.save(self.out, [edits.make('adjust', version='', points=1)])
        (self.out / outputs.GRADEBOOK).mkdir()      # as if open in Excel
        self.assertFalse(quiet(outputs.write, self.out, prefix='L'))
        self.assertTrue(edits.unexported(self.out))
        self.assertTrue((self.out / outputs.CANVAS).exists())

    def test_a_new_scan_sets_old_edits_aside(self):
        edits.save(self.out, [edits.make('adjust', version='', points=1)])
        quiet(outputs.record, self.out, self.csvs)
        self.assertEqual(edits.load(self.out), [])
        self.assertEqual(len(list(outputs.app_data(self.out).glob('edits_replaced_*.json'))), 1)


if __name__ == '__main__':
    unittest.main()
