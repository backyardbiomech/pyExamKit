'''
A stack scanned against several versions' keys grades the written answers
too, each version against its own key, and Re-grade scores them with the
key's points.

The on-screen grader is interactive, so it is replaced by a stand-in that
marks every written answer correct; what is tested is everything around it.

    python -m unittest tests.test_multi_version_written -v
'''
import json
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz
import numpy as np
import pandas as pd
from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

import keyformat  # noqa: E402
import outputs  # noqa: E402
import scanner  # noqa: E402
import sheet_layout  # noqa: E402
from build_tab import write_answer_sheets  # noqa: E402
from exam_builder import BuildConfig, ExamBuilder  # noqa: E402
from exam_key_writer import save_key  # noqa: E402
from test_bubbles import paint, paint_version  # noqa: E402

BANK = ROOT / 'tests' / 'fixtures' / 'build_migration' / 'input' / 'bank1.txt'


class AllCorrect:
    '''Stands in for openQ.OpenQs: every student's written answers are right.'''
    calls = []

    def __init__(self, image_list, key_file_data=None, pages_per_student=1,
                 output_csv_path='', **_):
        AllCorrect.calls.append((output_csv_path, len(image_list) - 1))
        oq = key_file_data['open_questions']
        self.openQcoords = {k: tuple(v['coords']) for k, v in oq.items()}
        n = (len(image_list) - 1) // pages_per_student
        # Row 0 is the key row, which the real grader fills with 'CC'
        self.openQres = pd.DataFrame({k: ['CC'] * (n + 1) for k in oq}, index=range(n + 1))
        self.acceptable_answers = {k: list(v['full']) for k, v in oq.items()}
        self.partial_credit_answers = {k: [] for k in oq}
        self._transcriptions = {k: {i: ('ok', 1.0) for i in range(1, n + 1)} for k in oq}
        self._q_pages = {k: 1 for k in oq}

    def save_artifacts(self, csv_path, grade_config=None):
        app = outputs.artifact_dir(csv_path)
        app.mkdir(exist_ok=True)
        stem = str(app / Path(csv_path).stem)
        Path(stem + '_openq_answers.json').write_text(json.dumps(self.acceptable_answers))
        Path(stem + '_openq_transcriptions.json').write_text('{}')
        Path(stem + '_openq_gradeconfig.json').write_text(json.dumps(grade_config))


class TestMultiVersionWritten(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp(prefix='mv_written_'))
        config = BuildConfig(title='MV', course='', num_versions=2, shuffle_questions=True,
                             shuffle_answers=True, exact_file=BANK, same_questions=True,
                             default_points=2.0)
        random.seed(8)
        versions, _ = ExamBuilder().build(config)
        crops, _ = write_answer_sheets(versions, cls.out, 'MV')
        cls.keys = {}
        for v in versions:
            path = cls.out / f'MV_v{v.version_letter}_key.csv'
            save_key(v, path, 2.0, open_coords=crops[v.version_letter])
            cls.keys[v.version_letter] = str(path)
        sheet = next(cls.out.glob('*_answer_sheet.pdf'))
        pix = fitz.open(sheet)[0].get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB)
        blank = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)

        # Two students per version, every bubble answered correctly
        pages, cls.expected = [], {}
        scans = cls.out / 'scans'
        scans.mkdir()
        for letter in ('A', 'B', 'A', 'B'):
            kd = keyformat.load_key_file(cls.keys[letter])
            grid = sheet_layout.keyed_layout(
                sheet_layout.parse_columns(kd['metadata']['sheet_rows']))
            img = blank.copy()
            for qk, ans in kd['bubble_answers'].items():
                if ans != 'ignore':
                    for a in ans:
                        paint(img, grid, qk, a, 90)
            paint_version(img, grid, letter, 90)
            for c, d in enumerate(f'{12345670 + len(pages) + 1}', 1):
                paint(img, grid, f'ID{c:02d}', d, 90)
            pages.append(PILImage.fromarray(img))
            cls.expected[letter] = sum(kd['point_values'].values())
        pages[0].save(scans / 'stack.pdf', save_all=True, append_images=pages[1:],
                      resolution=144)
        n = max(keyformat.load_key_file(k)['metadata']['num_questions']
                for k in cls.keys.values())
        AllCorrect.calls = []
        with mock.patch.object(scanner, 'OpenQs', AllCorrect):
            scanner.Scanner(str(scans / 'stack.pdf'), n, True, True, True, '', 0.35, 1, 1,
                            version_key_paths=cls.keys)
        cls.results = scans / 'ExamScanner_outputs'

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def version_df(self, letter):
        df = pd.read_csv(self.results / 'app_data' / f'results_version{letter}.csv', dtype=object)
        return df.set_index('index')

    def test_each_version_graded_against_its_own_key(self):
        self.assertEqual(sorted(p for p, _ in AllCorrect.calls),
                         sorted(str(self.results / 'app_data' / f'results_version{v}.csv')
                                for v in 'AB'))
        self.assertTrue(all(n == 2 for _, n in AllCorrect.calls))

    def test_written_points_count_toward_the_score(self):
        for letter in 'AB':
            df = self.version_df(letter)
            open_cols = [c for c in df.columns if c.startswith('openQ_')]
            self.assertTrue(open_cols, 'no written grades joined')
            for row in ('1', '2'):
                self.assertTrue(all(df.loc[row, c].startswith('CC') for c in open_cols))
                self.assertAlmostEqual(float(df.loc[row, 'partialscore']),
                                       self.expected[letter], places=2)

    def test_one_set_of_outputs_for_every_version(self):
        top = sorted(p.name for p in self.results.iterdir())
        self.assertEqual(top, ['ALERT.txt', 'app_data', 'canvas_upload.csv', 'gradebook.xlsx',
                               'marked', 'marked.pdf'][0 if 'ALERT.txt' in top else 1:])
        self.assertEqual(len(list((self.results / 'marked').glob('*.jpg'))), 4)

    def test_canvas_file_uploads_as_is(self):
        rows = (self.results / 'canvas_upload.csv').read_text().splitlines()
        self.assertEqual(rows[0], 'Student,SIS User ID,MV')
        possible = rows[1].split(',')
        self.assertEqual(possible[:2], ['    Points Possible', ''])
        self.assertAlmostEqual(float(possible[2]), self.expected['A'])
        body = rows[2:]
        self.assertEqual(len(body), 4)
        for line in body:
            sid, score = line.rsplit(',', 2)[-2:]
            self.assertRegex(sid, r'^L\d{8}$')
            self.assertGreater(float(score), 0)

    def test_canvas_file_loads_back_as_a_roster(self):
        import roster
        r, _ = roster.load_roster(self.results / 'canvas_upload.csv')
        self.assertEqual(len(r), 4)

    def test_gradebook_tabs(self):
        import openpyxl
        wb = openpyxl.load_workbook(self.results / 'gradebook.xlsx')
        self.assertEqual(wb.sheetnames, ['Version A', 'Version B', 'By question',
                                         'Item analysis'])

    def test_versions_combined_by_bank_question(self):
        graded = [outputs.load(p) for p in outputs.listed(self.results)]
        t = outputs.item_table(graded)
        self.assertTrue(t.by_source)
        for it in t.items:
            # every question sat once on each version, answered by all four
            self.assertEqual(sorted(w[0] for w in it.where), ['A', 'B'], it.label)
            self.assertEqual(len(it.responses), 4, it.label)
            # and every student chose the key, in the bank's letters
            if not it.written:
                self.assertEqual({a for *_, a in it.responses}, {it.key}, it.label)

    def test_regrade_config_carries_the_key_points(self):
        cfg = json.loads((self.results / 'app_data' /
                          'results_versionA_openq_gradeconfig.json').read_text())
        self.assertEqual(cfg['point_values'],
                         keyformat.load_key_file(self.keys['A'])['point_values'])


if __name__ == '__main__':
    unittest.main()
