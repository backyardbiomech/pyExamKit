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

    def test_a_folder_with_nothing_graded(self):
        with self.assertRaises(ValueError):
            rm.open_folder(self.out.parent)


if __name__ == '__main__':
    unittest.main()
