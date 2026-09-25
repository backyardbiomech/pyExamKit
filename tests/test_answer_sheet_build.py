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


if __name__ == '__main__':
    unittest.main()
