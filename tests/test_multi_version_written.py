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
        app = Path(csv_path).parent / 'app_data'
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
        df = pd.read_csv(self.results / f'results_version{letter}.csv', dtype=object)
        return df.set_index('index')

    def test_each_version_graded_against_its_own_key(self):
        self.assertEqual(sorted(p for p, _ in AllCorrect.calls),
                         sorted(str(self.results / f'results_version{v}.csv') for v in 'AB'))
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

    def test_combined_file_lists_every_student(self):
        combined = pd.read_csv(self.results / 'results_all_versions_forCanvas.csv')
        self.assertEqual(sorted(combined['version']), ['A', 'A', 'B', 'B'])
        self.assertTrue((combined['partialscore'] > 0).all())

    def test_regrade_config_carries_the_key_points(self):
        cfg = json.loads((self.results / 'app_data' /
                          'results_versionA_openq_gradeconfig.json').read_text())
        self.assertEqual(cfg['point_values'],
                         keyformat.load_key_file(self.keys['A'])['point_values'])


if __name__ == '__main__':
    unittest.main()
