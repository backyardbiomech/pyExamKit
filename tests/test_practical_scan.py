'''
Scanning a lab practical: pages grouped into students by what is printed on
them, and a synthetic mixed stack graded end to end against the one key.

The grading window needs Tk, so the end-to-end test replaces it with a
stand-in that grades from the generator's record of what each student wrote,
and records what the window would have shown.

    python -m unittest tests.test_practical_scan -v
'''
import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))

import make_practical_test_stack as stack  # noqa: E402
import openQ  # noqa: E402
import practical  # noqa: E402
from keyformat import _openq_sort_key  # noqa: E402
from practical_scan import PageRead, group_pages  # noqa: E402

SOURCE = ROOT / 'tests' / 'fixtures' / 'practical' / 'practical_test.md'


def pr(scan, page, form='AB'):
    return PageRead(scan, page, form, f'aligned_{scan}.jpg')


class TestGroupPages(unittest.TestCase):
    def test_in_order(self):
        sheets, alerts = group_pages([pr(1, 1), pr(2, 2), pr(3, 1, 'CD'), pr(4, 2, 'CD')], 2)
        self.assertEqual([s.form for s in sheets], ['AB', 'CD'])
        self.assertEqual((alerts, sheets[1].pages[1].scan), ([], 4))

    def test_missing_page_two_does_not_shift_the_next_student(self):
        sheets, alerts = group_pages([pr(1, 1), pr(2, 1, 'CD'), pr(3, 2, 'CD')], 2)
        self.assertEqual([s.first_scan for s in sheets], [1, 2])
        self.assertIsNone(sheets[0].pages[1])
        self.assertIn('page 2 missing', sheets[0].notes[0])
        self.assertEqual(alerts, [])

    def test_page_from_another_form_is_skipped(self):
        sheets, alerts = group_pages([pr(1, 1), pr(2, 2, 'CD')], 2)
        self.assertIsNone(sheets[0].pages[1])
        self.assertIn('Check the page order', alerts[0])

    def test_page_two_first_and_foreign_pages(self):
        sheets, alerts = group_pages([pr(1, 2), pr(2, 0, ''), pr(3, 1), pr(4, 2), pr(5, 2)], 2)
        self.assertEqual(len(sheets), 1)
        self.assertEqual(len(alerts), 3)          # scans 1, 2, and the second page 2


# What a grader would give each kind of answer in the generator's record
GRADE_FOR = {'full': 'CC', 'misspelled': 'CC', 'partial': 'CX', 'wrong': 'XX', 'blank': 'XX',
             'crossed out': 'CC', 'runs past box': 'CC', 'note outside box': 'CC'}


class TestPracticalScan(unittest.TestCase):
    @classmethod
    def write_source(cls, path: Path):
        shutil.copy(SOURCE, path)

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix='practical_scan_'))
        cls.key = cls.dir / 'practical.md'
        cls.write_source(cls.key)                    # grading writes answers back into it
        shutil.copytree(SOURCE.parent / 'images', cls.dir / 'images')
        # Printed at 85%, as the department's office printer does
        scans = stack.make_stack(cls.key, cls.dir / 'stack', n_students=5, seed=11,
                                 print_scale=0.85)
        with open(cls.dir / 'stack' / 'students.csv') as fh:
            cls.students = list(csv.DictReader(fh))
        with open(cls.dir / 'stack' / 'answers.csv') as fh:
            cls.written = {(int(r['student']), r['question']): (r['written'], r['why'])
                           for r in csv.DictReader(fh)}
        cls.shown = []

        def fake_window(self, filename, k, v, img_idx=None, force_show=False):
            label, name_crop = self._student_info(img_idx - 1)
            crop = np.array(PILImage.open(filename).convert('L'))[v[1]:v[3], v[0]:v[2]]
            q = k[len('openQ_'):]
            text, why = cls.written[(img_idx, q)]
            cls.shown.append({'q': q, 'student': img_idx, 'label': label,
                              'name_ink': name_crop is not None and name_crop.min() < 150,
                              'ink': int((crop < 200).sum()), 'text': text,
                              'blank': openQ.looks_blank(crop),
                              'title': self._q_text.get(k, ''), 'progress': self._progress})
            if (img_idx, q) == cls.add_at:
                # The grader accepts this student's spelling for everyone
                self._add_acceptable_and_regrade(k, 'renal pelvis of the kidney', img_idx)
                self._write_answers_to_key_file()
            return GRADE_FOR[why]

        # The first student to answer 1A gets an answer added to the key
        first_a = next(int(s['student']) for s in cls.students if 'A' in s['form'])
        cls.add_at = (first_a, '1A')
        import scanner
        with mock.patch.object(openQ.OpenQs, '_gradeOneAnswer', fake_window), \
                mock.patch.object(scanner, 'OpenQs', openQ.OpenQs):
            scanner.Scanner(str(scans), 0, True, True, True, '', 0.35, 1.0, 1.0,
                            parent=object(), key_file_path=str(cls.key),
                            roster_path=str(cls.dir / 'stack' / 'roster.csv'),
                            review_perfect=True)
        cls.out = cls.dir / 'stack' / 'ExamScanner_outputs'
        cls.results = pd.read_csv(cls.out / 'app_data' / 'results.csv',
                                  dtype=object).set_index('index')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_station_by_station_each_across_its_students(self):
        order = [s['q'] for s in self.shown]
        firsts = list(dict.fromkeys(order))
        self.assertEqual(firsts, sorted(firsts, key=_openq_sort_key))
        self.assertEqual(firsts[:5], ['1A', '1B', '1C', '1D', '2A'])
        for q in firsts:
            got = [s['student'] for s in self.shown if s['q'] == q]
            want = [int(s['student']) for s in self.students if q[-1] in s['form']]
            self.assertEqual(got, want, q)
            self.assertEqual([s['progress'] for s in self.shown if s['q'] == q],
                             [(i, len(want)) for i in range(1, len(want) + 1)])

    def test_each_crop_holds_that_students_writing(self):
        for s in self.shown:
            if s['text']:
                self.assertGreater(s['ink'], 40, s)
            else:
                self.assertLess(s['ink'], 10, s)

    def test_blank_boxes_are_told_from_written_ones(self):
        # Including the student who writes in very light pencil
        for s in self.shown:
            self.assertEqual(s['blank'], not s['text'], s)

    def test_window_names_the_student_and_the_question(self):
        s = self.shown[0]
        self.assertTrue(s['name_ink'])
        self.assertIn('form', s['label'])
        self.assertEqual(s['title'], 'Name the structure at pin A.')

    def test_roster_names_and_near_match(self):
        rows = self.results.drop(index=['0', 'numb_correct'])
        self.assertEqual(sorted(rows['LastName']), sorted(s['last'] for s in self.students))
        alerts = (self.out / 'ALERT.txt').read_text()
        self.assertIn('ROSTER', alerts)               # student 5's ID is one digit off
        self.assertNotIn('PRACTICAL', alerts)         # every page found its student

    def test_results_blank_off_form_and_scored_on_form(self):
        p = practical.load(self.key)
        for i, s in enumerate(self.students, 1):
            row = self.results.loc[str(i)]
            self.assertEqual(row['form'], s['form'])
            expected = 0.0
            for q in p.questions():
                cell = row[f'openQ_{q.key}']
                if q.letter not in s['form']:
                    self.assertTrue(pd.isna(cell), (i, q.key, cell))
                    continue
                grade = GRADE_FOR[self.written[(i, q.key)][1]]
                self.assertEqual(str(cell)[:2], grade, (i, q.key))
                expected += {'CC': 1, 'CX': 0.5, 'XX': 0}[grade] * p.points_for(q)
            self.assertAlmostEqual(float(row['partialscore']), expected)

    def test_added_answer_written_back_into_the_source(self):
        self.assertIn('renal pelvis of the kidney', practical.load(self.key).question('1A').full)
        self.assertIn('= renal pelvis\n= renal pelvis of the kidney\n', self.key.read_text())

    def test_outputs(self):
        for name in ('gradebook.xlsx', 'canvas_upload.csv', 'marked.pdf'):
            self.assertTrue((self.out / name).exists(), name)
        import sheet_layout
        last = sheet_layout.practical_pages(len(practical.load(self.key).stations))
        self.assertEqual(len(list((self.out / 'marked').glob(f'*_p{last}.jpg'))), 5)



class TestOnePagePracticalScan(TestPracticalScan):
    '''
    Eleven stations fit one page, so each sheet is printed double-sided with
    a blank back, and the stack alternates a student's page and a blank one.
    The blank pages are skipped without an alert; every test above still holds.
    '''

    @classmethod
    def write_source(cls, path: Path):
        text = SOURCE.read_text()
        path.write_text(text[:text.index('# Station 12')])

    def test_stack_has_the_blank_backs(self):
        import fitz
        self.assertEqual(practical.load(self.key).stations[-1].number, 11)
        self.assertEqual(len(fitz.open(self.dir / 'stack' / 'scans.pdf')), 2 * len(self.students))


if __name__ == '__main__':
    unittest.main()
