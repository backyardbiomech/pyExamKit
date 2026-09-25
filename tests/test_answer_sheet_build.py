'''
A build writes an answer sheet whose writing boxes match the key's crop
regions, so the scanner needs no boxes drawn by hand.

    python -m unittest tests.test_answer_sheet_build -v
'''
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import keyformat  # noqa: E402
from build_tab import write_answer_sheets  # noqa: E402
from exam_builder import BuildConfig, ExamBuilder  # noqa: E402
from exam_key_writer import answer_rows, save_key  # noqa: E402

BANK = ROOT / 'tests' / 'fixtures' / 'build_migration' / 'input' / 'bank1.txt'


def build(num_versions, shuffle):
    config = BuildConfig(title='Sheet Test', course='TEST101', num_versions=num_versions,
                         shuffle_questions=shuffle, shuffle_answers=False, exact_file=BANK,
                         pools=[], version_question=False, version_question_position='last',
                         default_points=1.0, same_questions=False)
    random.seed(3)
    versions, _ = ExamBuilder().build(config)
    return versions


class TestBuildWritesSheet(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix='sheet_build_'))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def test_one_version_sheet_and_key_agree(self):
        versions = build(1, False)
        n, written = answer_rows(versions[0])
        self.assertTrue(written, 'fixture bank should hold a short-answer question')
        crops, log = write_answer_sheets(versions, self.out, 'TEST101 Sheet Test')
        self.assertTrue((self.out / 'Sheet_Test_answer_sheet.pdf').exists(), log)
        key = self.out / 'key.csv'
        save_key(versions[0], key, open_coords=crops['A'])
        data = keyformat.load_key_file(str(key))
        for q in written:
            self.assertEqual(tuple(data['open_questions'][f'openQ_{q}']['coords']),
                             crops['A'][q])

    def test_shared_sheet_when_rows_match(self):
        versions = build(2, False)
        crops, _ = write_answer_sheets(versions, self.out, 'Sheet Test')
        self.assertEqual(crops['A'], crops['B'])
        self.assertEqual(len(list(self.out.glob('*_answer_sheet.pdf'))), 1)



PINNED_BANK = """MC
1. First?
*A. yes
B. no

SA
2. Blank one ________.
A. one

OR
3. Order these from small to large.
1: small
2: medium
3: large

MC
4. Fourth?
*A. yes
B. no

MT
5. Match each term.
[catA]term1: alpha
[catB]term2: beta
catA: first
catB: second

SA
6. Blank two ________.
A. two

MC
7. Seventh?
*A. yes
B. no

MC
8. Eighth?
*A. yes
B. no

SA
9. Blank three ________.
A. three
"""


class TestWrittenRowsMatchAcrossVersions(unittest.TestCase):
    """With shared questions, every version puts its written questions on the
    same rows, so one answer sheet serves all versions."""

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix='sheet_pinned_'))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)
        self.bank = self.out / 'bank.txt'
        self.bank.write_text(PINNED_BANK, encoding='utf-8')

    def build(self, seed, same_questions=True):
        config = BuildConfig(title='Pinned', course='', num_versions=4,
                             shuffle_questions=True, shuffle_answers=True,
                             exact_file=self.bank, pools=[], version_question=False,
                             version_question_position='last', default_points=1.0,
                             same_questions=same_questions)
        random.seed(seed)
        versions, _ = ExamBuilder().build(config)
        return versions

    def test_written_rows_identical_in_every_version(self):
        for seed in range(25):
            versions = self.build(seed)
            rows = [answer_rows(v) for v in versions]
            self.assertEqual(len(rows[0][1]), 3)
            self.assertTrue(all(r == rows[0] for r in rows), f'seed {seed}: {rows}')

    def test_versions_still_differ_in_order(self):
        differ = 0
        for seed in range(25):
            orders = [tuple(q.text for q in v.questions) for v in self.build(seed)]
            differ += len(set(orders)) > 1
        self.assertGreater(differ, 20)

    def test_one_sheet_for_all_versions(self):
        crops, log = write_answer_sheets(self.build(7), self.out, 'Pinned')
        self.assertEqual(len(list(self.out.glob('*_answer_sheet.pdf'))), 1, log)
        self.assertEqual(len({tuple(sorted(c.items())) for c in crops.values()}), 1)


if __name__ == '__main__':
    unittest.main()
