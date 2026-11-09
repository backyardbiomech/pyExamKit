'''
Accepting a written answer on the Results tab is an edit: it upgrades every
student whose saved reading is exactly that answer, on every version that
printed the question, and deleting it takes the upgrades back.

    python -m unittest tests.test_written_edits -v
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
import keyformat  # noqa: E402
import outputs  # noqa: E402
import results_model as rm  # noqa: E402

GOOD = 'stratum germinativum'
# {version: (the written column, [(student, cell, what it was read as)], answers)}
WRITTEN = {
    'A': ('openQ_3', [('ADAMS', 'XX', ' Stratum  Germinativum'), ('BAKER', 'CX', GOOD),
                      ('COLE', 'CC: stratum basale', 'stratum basale'),
                      ('DIAZ', 'XX', 'stratum germ'),
                      ('ELLIS', 'XX', 'stratum basale')],      # read as the key, graded wrong
          {'full': ['stratum basale'], 'partial': []}),
    'B': ('openQ_5', [('FOX', 'XX', GOOD), ('GRAY', 'XX', 'ulna')],
          {'full': ['stratum basale', 'basal layer'], 'partial': ['skin']}),
}


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def write_results(out: Path, version: str, col: str, students, answers, sources=None,
                  points=4.0, config=None) -> Path:
    '''One version's results as a scan with written answers leaves them.'''
    rows = [['0', 'KEY', '', '', 'A', 'CC']]
    rows += [[str(i), last, 'X', f'{i:08d}', 'A', cell]
             for i, (last, cell, _) in enumerate(students, 1)]
    path = Path(outputs.results_csv(out, version))
    pd.DataFrame(rows, columns=['index', 'LastName', 'FirstName', 'studentID', 'Q001', col]
                 ).to_csv(path, index=False)
    quiet(grade_functions.gradeResults, str(path), False, True, 1, 2, out / 'marked',
          point_values={'Q001': 1.0, col: points},
          key_data={'metadata': {'title': 'Quiz'}, 'sources': sources or {},
                    'texts': {col: 'Name the deepest layer of the epidermis, in as many words '
                                   'as it takes to wrap onto several lines of the view'}})
    app = outputs.artifact_dir(path)
    (app / f'{path.stem}_openq_answers.json').write_text(json.dumps({col: answers}))
    (app / f'{path.stem}_openq_transcriptions.json').write_text(json.dumps(
        {col: {str(i): [text, 0.9] for i, (_, _, text) in enumerate(students, 1)}}))
    if config:
        (app / f'{path.stem}_openq_gradeconfig.json').write_text(json.dumps(config))
    return path


def make_written_outputs(root: Path, one_column: bool = False) -> Path:
    '''An outputs folder of two versions sharing one written question, at a
    different place on each sheet unless one_column is set.'''
    out = root / 'ExamScanner_outputs'
    (out / 'marked').mkdir(parents=True)
    paths = [write_results(out, v, 'openQ_3' if one_column else col, students, answers,
                           {'Q001': 'bank.md#1', 'openQ_3' if one_column else col: 'bank.md#9'})
             for v, (col, students, answers) in WRITTEN.items()]
    quiet(outputs.record, out, paths)
    return out


class WrittenEditTest(unittest.TestCase):
    def setUp(self):
        self.out = make_written_outputs(Path(tempfile.mkdtemp()))
        self.res = rm.open_folder(self.out)

    def tearDown(self):
        shutil.rmtree(self.out.parent)

    def question(self, res=None) -> rm.Question:
        return next(q for q in rm.questions(res or self.res) if q.written)

    def accept(self, answer=GOOD, grade='full', res=None, note='') -> rm.Results:
        res = res or self.res
        return rm.add(res, rm.written_edit(res, self.question(res), answer, grade, note))

    @staticmethod
    def points(res) -> dict:
        '''{last name: points on the written question}'''
        out = {}
        for g in res.graded:
            col = next(c for c in g.possible if c.startswith('openQ_'))
            for r in g.students:
                out[g.df.loc[r, 'LastName']] = g.earned(r, col)
        return out

    def test_the_question_is_listed_once(self):
        qs = [q for q in rm.questions(self.res) if q.written]
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].where, 'A3, B5')

    def test_an_answer_upgrades_every_version_on_an_exact_reading(self):
        before = self.points(self.res)
        self.assertEqual(before, {'ADAMS': 0, 'BAKER': 2, 'COLE': 4, 'DIAZ': 0, 'ELLIS': 0,
                                  'FOX': 0, 'GRAY': 0})
        res = self.accept()
        self.assertEqual(self.points(res), {'ADAMS': 4, 'BAKER': 4, 'COLE': 4, 'DIAZ': 0,
                                            'ELLIS': 0, 'FOX': 4, 'GRAY': 0})
        self.assertEqual(rm.grades_changed(self.res, res, self.question()), 3)

    def test_a_new_partial_answer_only_raises(self):
        # BAKER was given half by eye, and a full-credit grade would stay too
        res = self.accept(grade='partial')
        self.assertEqual(self.points(res)['ADAMS'], 2)
        self.assertEqual(self.points(res)['BAKER'], 2)
        self.assertEqual(self.points(res)['FOX'], 2)

    def test_only_the_new_answer_is_judged(self):
        # ELLIS was read as a key answer and graded wrong: that was the grader's call
        self.assertEqual(self.points(self.accept())['ELLIS'], 0)

    def test_deleting_the_edit_takes_the_upgrades_back(self):
        res = self.accept()
        res = rm.delete(res, res.edits[0]['id'])
        self.assertEqual(res.edits, [])
        self.assertEqual(self.points(res), self.points(self.res))

    def test_results_files_are_left_alone(self):
        path = outputs.listed(self.out)[0]
        before = path.read_text()
        self.accept()
        self.assertEqual(path.read_text(), before)

    def test_answers_are_combined_across_versions(self):
        keys = rm.written_keys(self.res, self.question())
        self.assertEqual([(k.answer, k.grade) for k in keys],
                         [('stratum basale', 'full'), ('basal layer', 'full'), ('skin', 'partial')])
        self.assertTrue(all(not k.edit_id for k in keys))

    def test_an_added_answer_is_marked_and_listed_on_every_version(self):
        res = self.accept()
        key = next(k for k in rm.written_keys(res, self.question(res)) if k.answer == GOOD)
        self.assertEqual(key.edit_id, res.edits[0]['id'])
        self.assertTrue(all(GOOD in next(v for k, v in g.open_answers.items()) for g in res.graded))

    def test_a_second_grade_for_an_answer_replaces_the_first(self):
        res = self.accept(GOOD.upper())
        res = self.accept(GOOD, 'partial', res)
        self.assertEqual(len(res.edits), 1)
        self.assertEqual(self.points(res)['FOX'], 2)
        keys = rm.written_keys(res, self.question(res))
        self.assertEqual([k.grade for k in keys if k.answer == GOOD], ['partial'])

    def test_removing_a_scan_answer_takes_its_credit_back(self):
        q = self.question()
        key = rm.written_keys(self.res, q)[0]
        res = rm.remove_written(self.res, q, key)
        self.assertNotIn('stratum basale', [k.answer for k in rm.written_keys(res, q)])
        self.assertEqual(self.points(res)['COLE'], 0)
        self.assertEqual(rm.grades_changed(self.res, res, q), 1)
        # Deleting the edit gives it back
        self.assertEqual(self.points(rm.delete(res, res.edits[0]['id'])), self.points(self.res))

    def test_removing_leaves_a_near_miss_alone(self):
        # Graded by eye against that answer; nothing says it was only for that answer
        graded = [outputs.load(p) for p in outputs.listed(self.out)]
        graded[0].transcriptions['openQ_3']['4'] = ['stratum basle', 0.9]
        graded[0].df.loc['4', 'openQ_3'] = 'CC'
        graded[0].pts.loc['4', 'openQ_3'] = 4.0
        out, _ = edits.apply(graded, [edits.make('written', source='bank.md#9',
                                                 answer='stratum basale', grade='remove')])
        self.assertEqual(out[0].earned('4', 'openQ_3'), 4)

    def test_a_point_set_by_hand_stands_over_a_removal(self):
        res = rm.add(self.res, rm.override_edit(self.res, 'A', '3', 'openQ_3', 3.0))
        q = self.question(res)
        res = rm.remove_written(res, q, rm.written_keys(res, q)[0])
        self.assertEqual(self.points(res)['COLE'], 3)

    def test_a_full_credit_answer_moved_to_partial_gives_half(self):
        res = self.accept('stratum basale', 'partial')
        self.assertEqual(self.points(res)['COLE'], 2)

    def test_removing_an_added_answer_undoes_it(self):
        res = self.accept()
        q = self.question(res)
        key = next(k for k in rm.written_keys(res, q) if k.edit_id)
        res = rm.remove_written(res, q, key)
        self.assertEqual(res.edits, [])
        self.assertEqual(self.points(res)['FOX'], 0)

    def test_what_cannot_be_accepted(self):
        q = self.question()
        with self.assertRaisesRegex(ValueError, 'Type the answer'):
            rm.written_edit(self.res, q, '   ', 'full')
        with self.assertRaisesRegex(ValueError, 'already'):
            rm.written_edit(self.res, q, 'Stratum  Basale', 'full')
        bubble = next(q for q in rm.questions(self.res) if not q.written)
        with self.assertRaisesRegex(ValueError, 'not a written'):
            rm.written_edit(self.res, bubble, GOOD, 'full')

    def test_a_point_set_by_hand_stands_over_an_upgrade(self):
        res = rm.add(self.res, rm.override_edit(self.res, 'A', '1', 'openQ_3', 1.0))
        self.assertEqual(self.points(self.accept(res=res))['ADAMS'], 1)

    def test_a_student_moved_to_another_version_keeps_the_upgrade(self):
        # Moving a student carries a column only when both versions have it
        out = make_written_outputs(Path(tempfile.mkdtemp()), one_column=True)
        self.addCleanup(shutil.rmtree, out.parent)
        start = rm.open_folder(out)
        s = next(s for s in rm.students(start) if s.name.startswith('ADAMS'))
        res = rm.add(start, rm.version_edit(start, s, 'B'))
        res = self.accept(res=res)
        self.assertEqual(res.problems, [])
        moved = next(g for g in res.graded if g.version == 'B')
        self.assertTrue(moved.df.loc['A1', 'openQ_3'].startswith('CC'))
        rows = rm.written_rows(res, self.question(res))
        self.assertEqual([r.grade for r in rows if r.student.startswith('ADAMS')], ['Full'])

    def test_readings_sit_together(self):
        rows = rm.written_rows(self.res, self.question())
        self.assertEqual([r.student.split(',')[0] for r in rows],
                         ['COLE', 'ELLIS', 'DIAZ', 'ADAMS', 'BAKER', 'FOX', 'GRAY'])
        self.assertEqual({r.where for r in rows}, {'A3', 'B5'})

    def test_described_for_the_edits_list(self):
        res = self.accept(note='also correct')
        self.assertEqual(rm.describe(res, res.edits[0]), f'bank.md#9: also accept "{GOOD}"')
        self.assertTrue(res.unexported)

    def test_export_carries_it(self):
        res = self.accept()
        self.assertTrue(quiet(outputs.write, self.out, prefix='L'))
        rows = list(csv.reader((self.out / outputs.CANVAS).read_text().splitlines()))
        scores = {r[0].split(',')[0]: float(r[5]) for r in rows[2:]}
        # Each has Q001 (1 point) too
        self.assertEqual(scores['FOX'], 5)
        self.assertEqual(scores['GRAY'], 1)
        self.assertFalse(rm.open_folder(self.out).unexported)
        self.assertEqual(len(res.edits), 1)


class PracticalKeyFileTest(unittest.TestCase):
    '''A lab practical's source file is its key, and keeps its answers current.'''

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.key = self.root / 'practical.md'
        shutil.copy(ROOT / 'tests' / 'fixtures' / 'practical' / 'practical_test.md', self.key)
        self.col = next(iter(keyformat.load_key_file(str(self.key))['open_questions']))
        out = self.root / 'ExamScanner_outputs'
        (out / 'marked').mkdir(parents=True)
        path = write_results(out, '', self.col, [('ADAMS', 'XX', 'a new answer')],
                             {'full': ['first'], 'partial': []},
                             config={'key_file': str(self.key)})
        quiet(outputs.record, out, [path])
        self.res = rm.open_folder(out)

    def tearDown(self):
        shutil.rmtree(self.root)

    def on_file(self) -> list:
        return keyformat.load_key_file(str(self.key))['open_questions'][self.col]['full']

    def test_an_answer_goes_into_the_file_and_comes_out_with_its_edit(self):
        q = next(q for q in rm.questions(self.res) if q.written)
        res = rm.add(self.res, rm.written_edit(self.res, q, 'a new answer', 'full'))
        self.assertIn('a new answer', self.on_file())
        rm.delete(res, res.edits[0]['id'])
        self.assertNotIn('a new answer', self.on_file())


if __name__ == '__main__':
    unittest.main()
