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
import sheet_layout  # noqa: E402
from exam_builder import BuildConfig, ExamBuilder, is_grouped, slot_count  # noqa: E402
from exam_key_writer import answer_rows, save_key, sheet_columns  # noqa: E402

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


def grouped_rows(version) -> list[range]:
    """The answer-sheet rows of each ordering, matching, or dropdown question."""
    out, row = [], 1
    for q in version.questions:
        n = slot_count(q)
        if is_grouped(q):
            out.append(range(row, row + n))
        row += n
    return out


class TestGroupedRows(unittest.TestCase):
    """Ordering and matching rows sit together between gaps, in the same
    place in every version, and the key says where."""

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix='sheet_grouped_'))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)
        self.bank = self.out / 'bank.txt'
        self.bank.write_text(PINNED_BANK, encoding='utf-8')

    def build(self, seed):
        config = BuildConfig(title='Grouped', course='', num_versions=4,
                             shuffle_questions=True, shuffle_answers=True,
                             exact_file=self.bank, pools=[], version_question=False,
                             version_question_position='last', default_points=1.0,
                             same_questions=True)
        random.seed(seed)
        versions, _ = ExamBuilder().build(config)
        return versions

    def test_each_grouped_question_is_one_run(self):
        for seed in range(25):
            for v in self.build(seed):
                lay = sheet_layout.keyed_layout(sheet_columns(v))
                for rows in grouped_rows(v):
                    before, first, last, after = (rows[0] - 1, rows[0], rows[-1], rows[-1] + 1)
                    ys = [lay.questions[f'Q{q:03d}'][0][2] for q in rows]
                    xs = {lay.questions[f'Q{q:03d}'][0][1] for q in rows}
                    self.assertEqual(len(xs), 1, 'a grouped question split across columns')
                    self.assertTrue(all(b - a == sheet_layout.V2_Q_ROW
                                        for a, b in zip(ys, ys[1:])), 'gap inside a question')
                    for q, edge in ((before, first), (after, last)):
                        k = f'Q{q:03d}'
                        if k in lay.questions and lay.questions[k][0][1] in xs:
                            gap = abs(lay.questions[k][0][2] - lay.questions[f'Q{edge:03d}'][0][2])
                            self.assertGreater(gap, sheet_layout.V2_Q_ROW, 'no gap beside it')

    def test_rows_identical_in_every_version(self):
        for seed in range(25):
            versions = self.build(seed)
            cols = [sheet_columns(v) for v in versions]
            self.assertIsNotNone(cols[0])
            self.assertTrue(all(c == cols[0] for c in cols), f'seed {seed}: {cols}')
            self.assertTrue(all(grouped_rows(v) == grouped_rows(versions[0]) for v in versions))

    def test_one_grouped_sheet_and_key_carries_it(self):
        versions = self.build(11)
        crops, log = write_answer_sheets(versions, self.out, 'Grouped')
        self.assertEqual(len(list(self.out.glob('*_answer_sheet.pdf'))), 1, log)
        key = self.out / 'key.csv'
        save_key(versions[1], key, open_coords=crops['B'])
        data = keyformat.load_key_file(str(key))
        self.assertEqual(sheet_layout.parse_columns(data['metadata']['sheet_rows']),
                         sheet_columns(versions[0]))

    def test_exam_without_grouped_questions_gets_standard_sheet(self):
        versions = build(1, False)
        versions[0].questions = [q for q in versions[0].questions if not is_grouped(q)]
        self.assertIsNone(sheet_columns(versions[0]))
        key = self.out / 'plain.csv'
        save_key(versions[0], key)
        self.assertNotIn('sheet_rows', keyformat.load_key_file(str(key)).get('metadata', {}))


if __name__ == '__main__':
    unittest.main()
