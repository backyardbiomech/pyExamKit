'''
What the Results tab shows, from an outputs folder with its edits applied.
The fixture is test_edits's two-version quiz:

    Version A (key A B C): AMES 3, BELL 2, COLE 0
    Version B (key C A B): DART 3, EGAN 2           each out of 3

    python -m unittest tests.test_results_model -v
'''
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

import edits  # noqa: E402
import outputs  # noqa: E402
import results_model as rm  # noqa: E402
from test_edits import make_outputs  # noqa: E402


class ResultsModelTest(unittest.TestCase):
    def setUp(self):
        self.out, self.csvs = make_outputs(Path(tempfile.mkdtemp()))

    def tearDown(self):
        shutil.rmtree(self.out.parent)

    def results(self, *made):
        edits.save(self.out, list(made))
        return rm.open_folder(self.out)

    def test_summary_columns_before_and_after(self):
        cols = rm.columns(self.results(edits.make('adjust', version='', points=1),
                                       edits.make('adjust', version='A', points=1)))
        self.assertEqual([c.label for c in cols], ['All students', 'Version A', 'Version B'])
        everyone, a, b = cols
        self.assertEqual((everyone.before['n'], everyone.before['mean']), (5, 2.0))
        # A gets 2 points, B gets 1: (5 + 4 + 2 + 4 + 3) / 5
        self.assertEqual(everyone.after['mean'], 3.6)
        self.assertEqual((a.after['highest'], b.after['highest']), (5, 4))
        self.assertEqual(everyone.possible, 3)

    def test_grade_counts(self):
        before, after = rm.grade_counts(self.results(edits.make('adjust', version='', points=1)))
        # 3/3 twice is an A, 2/3 (66.7%) twice a D, 0 a low F
        self.assertEqual({k: v for k, v in before.items() if v}, {'A': 2, 'D': 2, 'Low F': 1})
        # +1: four at or above 100%, and 1/3 still a low F
        self.assertEqual({k: v for k, v in after.items() if v}, {'A': 4, 'Low F': 1})

    def test_questions_matched_across_versions(self):
        qs = {q.label: q for q in rm.questions(self.results())}
        self.assertEqual(sorted(qs), ['bank.md#1', 'bank.md#2', 'bank.md#3'])
        q = qs['bank.md#2']
        self.assertEqual((q.where, q.key, q.n), ('A2, B3', 'B', 5))
        self.assertEqual(q.counts, {'B': 2, 'C': 3})
        self.assertAlmostEqual(q.mean, 0.4)

    def test_questions_follow_a_key_edit(self):
        res = self.results(edits.make('key', version='A', question='Q002', keys=['C'], also=True),
                           edits.make('key', version='B', question='Q003', keys=['C'], also=True))
        q = next(q for q in rm.questions(res) if q.label == 'bank.md#2')
        self.assertEqual((q.key, q.mean), ('B or C', 1.0))

    def test_students_sorted_by_name(self):
        res = self.results(edits.make('adjust', version='B', points=2))
        rows = rm.students(res)
        self.assertEqual([s.name for s in rows],
                         ['AMES, X', 'BELL, X', 'COLE, X', 'DART, X', 'EGAN, X'])
        dart = rows[3]
        self.assertEqual((dart.version, dart.total, dart.adjusted), ('B', 3, 5))

    def test_one_students_answers(self):
        res = self.results(edits.make('credit', version='A', question='Q001', action='drop'))
        cole = rm.answers(res, 'A', '3')
        self.assertEqual([(a.question, a.answer, a.key, a.earned, a.possible) for a in cole],
                         [('Q001', 'B', 'A', 0, None), ('Q002', 'C', 'B', 0, 1),
                          ('Q003', 'D', 'C', 0, 1)])

    def test_marked_pages_by_name_and_id(self):
        for name in ('AMES_X_1_001.jpg', 'AMES_X_1_002_p2.jpg', 'BELL_X_2_002.jpg'):
            (self.out / 'marked' / name).write_bytes(b'')
        res = self.results()
        self.assertEqual([p.name for p in rm.marked_pages(res, 'A', '1')],
                         ['AMES_X_1_001.jpg', 'AMES_X_1_002_p2.jpg'])

    def test_problems_and_legacy_reported(self):
        res = self.results(edits.make('key', version='C', question='Q001', keys=['A']))
        self.assertEqual(len(res.problems), 1)
        self.assertFalse(res.legacy)
        rec_path = outputs.grading_json(self.csvs[0])
        rec = json.loads(rec_path.read_text())
        del rec['settings']
        rec_path.write_text(json.dumps(rec))
        self.assertTrue(rm.open_folder(self.out).legacy)

    def test_the_folder_holding_the_outputs_opens_them(self):
        self.assertEqual(rm.open_folder(self.out.parent).outdir, self.out)

    def test_an_empty_folder_says_what_it_looked_for(self):
        empty = self.out.parent / 'empty'
        empty.mkdir()
        with self.assertRaises(ValueError) as said:
            rm.open_folder(empty)
        self.assertIn('no app_data folder', str(said.exception))
        # The scan's results gone, the gradebook still there
        (self.out / outputs.GRADEBOOK).write_bytes(b'')
        for p in self.csvs:
            p.unlink()
        with self.assertRaises(ValueError) as said:
            rm.open_folder(self.out)
        msg = str(said.exception)
        self.assertIn('names results_versionA.csv, results_versionB.csv', msg)
        self.assertIn('gradebook.xlsx is there', msg)
        (outputs.app_data(self.out) / outputs.MANIFEST).unlink()
        with self.assertRaises(ValueError) as said:
            rm.open_folder(self.out)
        self.assertIn('looked for app_data/results.csv', str(said.exception))

    # ── Making edits ──────────────────────────────────────────────────────

    def question(self, res, label):
        return next(q for q in rm.questions(res) if q.label == label)

    def test_adjustments_replace_and_clear(self):
        res = rm.set_adjustments(self.results(), {'': 1, 'A': 0, 'B': 2}, note='curve')
        self.assertEqual(res.adjust, {'': 1, 'B': 2})
        self.assertTrue(res.unexported)
        res = rm.set_adjustments(res, {'': 1, 'A': 0, 'B': 0})
        self.assertEqual(res.adjust, {'': 1})
        self.assertEqual([(e['version'], e['note']) for e in res.edits], [('', 'curve')])

    def test_key_change_by_bank_question(self):
        res = self.results()
        q = self.question(res, 'bank.md#2')
        e = rm.key_edit(res, q, rm.parse_keys('c'), also=True, note='two right answers')
        self.assertEqual((e['source'], e['keys'], e['also']), ('bank.md#2', ['C'], True))
        res = rm.add(res, e)
        self.assertEqual(self.question(res, 'bank.md#2').mean, 1.0)
        # Changing the key outright makes the also-accept moot
        res = rm.add(res, rm.key_edit(res, q, ['C'], also=False))
        self.assertEqual(len(res.edits), 1)
        self.assertEqual(self.question(res, 'bank.md#2').key, 'C')
        self.assertEqual(rm.describe(res, res.edits[0]), 'bank.md#2: key changed to C')

    def test_parse_keys(self):
        self.assertEqual(rm.parse_keys(' c, d or ca '), ['C', 'D', 'AC'])
        for bad in ('', '1', 'C;D'):
            with self.assertRaises(ValueError):
                rm.parse_keys(bad)

    def test_credit_actions(self):
        res = self.results()
        q = self.question(res, 'bank.md#3')
        res = rm.add(res, rm.credit_edit(res, q, 'points', 2))
        res = rm.add(res, rm.credit_edit(res, q, 'points', 4))
        self.assertEqual(len(res.edits), 1)
        self.assertEqual(self.question(res, 'bank.md#3').points, 4)
        self.assertEqual(rm.describe(res, res.edits[0]), 'bank.md#3: worth 4 points')
        res = rm.add(res, rm.credit_edit(res, q, 'drop'))
        self.assertNotIn('bank.md#3', [q.label for q in rm.questions(res)])
        res = rm.delete(res, [e['id'] for e in res.edits])
        self.assertEqual(res.edits, [])
        with self.assertRaises(ValueError):
            rm.credit_edit(res, q, 'points', -1)

    def test_override_one_cell(self):
        res = self.results()
        res = rm.add(res, rm.override_edit(res, 'A', '3', 'Q002', 0.5, note='argued well'))
        res = rm.add(res, rm.override_edit(res, 'A', '3', 'Q002', 1))
        self.assertEqual(len(res.edits), 1)
        self.assertEqual(res.edits[0]['student_id'], '3')
        cole = {a.question: a for a in rm.answers(res, 'A', '3')}
        self.assertEqual((cole['Q002'].earned, cole['Q002'].overridden), (1, True))
        self.assertFalse(cole['Q001'].overridden)
        self.assertEqual(rm.describe(res, res.edits[0]), 'COLE, X, Version A Q002: 1 point')
        self.assertEqual(len(rm.overrides_on(res, self.question(res, 'bank.md#2'))), 1)
        res = rm.set_note(res, res.edits[0]['id'], 'checked the sheet')
        self.assertEqual(res.edits[0]['note'], 'checked the sheet')

    def test_written_keys_are_not_changed_here(self):
        res = self.results()
        q = self.question(res, 'bank.md#1')
        q.written = True
        with self.assertRaises(ValueError):
            rm.key_edit(res, q, ['A'], also=False)


if __name__ == '__main__':
    unittest.main()
