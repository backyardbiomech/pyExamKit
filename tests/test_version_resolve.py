'''
A student's version comes from the header's version bubbles or the version
question Build Exam adds, whichever was filled in. Only when neither can be
read, or the two disagree, is the person scanning asked.

    python -m unittest tests.test_version_resolve -v
'''
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import keyformat  # noqa: E402
import scanner  # noqa: E402
from exam_builder import BuildConfig, ExamBuilder  # noqa: E402
from exam_key_writer import save_key  # noqa: E402

BANK = ROOT / 'tests' / 'fixtures' / 'build_migration' / 'input' / 'bank1.txt'


def key(letter, vq='Q010'):
    return {'bubble_answers': {'Q001': 'B', vq: letter},
            'texts': {'Q001': 'A question.',
                      vq: f'EXAM VERSION — Fill in the bubble for version {letter}.'}}


def make_scanner(keys, version_question=0):
    s = object.__new__(scanner.Scanner)
    s.version_keys = keys
    s.version_question = version_question
    s.version_qks = s._find_version_questions()
    s.reads = {}
    s.resdf = pd.DataFrame(index=range(10), dtype=object)
    return s


def student(s, row, header, answers):
    s.reads[row] = SimpleNamespace(version=header)
    for qk, ans in answers.items():
        s.resdf.loc[row, qk] = ans


class TestFindVersionQuestions(unittest.TestCase):
    def test_found_from_the_keys(self):
        s = make_scanner({'A': key('A'), 'B': key('B')})
        self.assertEqual(s.version_qks, {'A': 'Q010', 'B': 'Q010'})

    def test_typed_number_wins(self):
        s = make_scanner({'A': key('A'), 'B': key('B')}, version_question=7)
        self.assertEqual(s.version_qks, {'A': 'Q007', 'B': 'Q007'})

    def test_key_without_one(self):
        s = make_scanner({'A': {'bubble_answers': {'Q001': 'A'}}})
        self.assertEqual(s.version_qks, {})

    def test_found_in_keys_written_by_build_exam(self):
        out = Path(tempfile.mkdtemp(prefix='vq_keys_'))
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        config = BuildConfig(title='VQ', course='', num_versions=3, shuffle_questions=True,
                             shuffle_answers=True, exact_file=BANK,
                             version_question=True, default_points=2.0)
        random.seed(3)
        versions, _ = ExamBuilder().build(config)
        keys = {}
        for v in versions:
            path = out / f'VQ_v{v.version_letter}_key.csv'
            save_key(v, path, 2.0)
            keys[v.version_letter] = keyformat.load_key_file(str(path))
        s = make_scanner(keys)
        n = keys['A']['metadata']['num_questions']
        self.assertEqual(s.version_qks, {v: f'Q{n:03d}' for v in 'ABC'})


class TestResolveVersion(unittest.TestCase):
    def setUp(self):
        self.s = make_scanner({v: key(v) for v in 'ABCDEF'})

    def test_both_agree(self):
        student(self.s, 1, 'C', {'Q010': 'C'})
        self.assertEqual(self.s._resolve_version(1), ('C', ''))

    def test_header_alone(self):
        student(self.s, 1, 'D', {'Q010': '-'})
        self.assertEqual(self.s._resolve_version(1), ('D', ''))

    def test_question_alone(self):
        student(self.s, 1, '-', {'Q010': 'E'})
        ver, note = self.s._resolve_version(1)
        self.assertEqual(ver, 'E')
        self.assertIn('question 10 reads version E', note)

    def test_disagreement_asks(self):
        student(self.s, 1, 'B', {'Q010': 'A'})
        ver, note = self.s._resolve_version(1)
        self.assertIsNone(ver)
        self.assertIn('bubble reads B', note)
        self.assertIn('question 10 reads version A', note)

    def test_neither_asks(self):
        student(self.s, 1, '-', {'Q010': 'AC'})
        ver, note = self.s._resolve_version(1)
        self.assertIsNone(ver)
        self.assertIn('question 10: "AC"', note)

    def test_classic_sheet_without_a_header_read(self):
        self.s.resdf = pd.DataFrame({'Q010': ['-', 'F']}, dtype=object)
        self.assertEqual(self.s._resolve_version(1)[0], 'F')

    def test_questions_at_different_numbers(self):
        # Versions of different lengths put a last-position question at
        # different numbers; a content answer matching another version's
        # letter there leaves the question unreadable rather than wrong
        s = make_scanner({'A': key('A', 'Q010'), 'B': key('B', 'Q009')})
        student(s, 1, '-', {'Q010': 'A', 'Q009': 'C'})
        self.assertEqual(s._resolve_version(1)[0], 'A')
        student(s, 2, '-', {'Q010': 'A', 'Q009': 'B'})
        self.assertIsNone(s._resolve_version(2)[0])
        student(s, 3, 'B', {'Q010': 'A', 'Q009': 'B'})
        self.assertEqual(s._resolve_version(3), ('B', ''))


if __name__ == '__main__':
    unittest.main()
