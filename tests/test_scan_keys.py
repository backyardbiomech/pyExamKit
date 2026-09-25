'''
Choosing one key on Scan Exams finds the other versions' keys beside it.

    python -m unittest tests.test_scan_keys -v
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
import scan_keys  # noqa: E402
from exam_builder import BuildConfig, ExamBuilder  # noqa: E402
from exam_key_writer import save_key  # noqa: E402

BANK = ROOT / 'tests' / 'fixtures' / 'build_migration' / 'input' / 'bank1.txt'


class TestLoadKeys(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix='scan_keys_'))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def write_build(self, versions=3, stem='Exam_2'):
        config = BuildConfig(title='Exam 2', course='', num_versions=versions,
                             shuffle_questions=True, shuffle_answers=True, exact_file=BANK,
                             same_questions=True)
        random.seed(5)
        built, _ = ExamBuilder().build(config)
        paths = []
        for v in built:
            path = self.out / f'{stem}_v{v.version_letter}_key.csv'
            save_key(v, path)
            paths.append(path)
        return paths

    def test_one_key_finds_its_versions(self):
        paths = self.write_build()
        self.write_build(2, stem='Other_Exam')      # a different build in the same folder
        ks = scan_keys.load_keys([str(paths[1])])
        self.assertEqual(sorted(ks.paths), ['A', 'B', 'C'])
        self.assertTrue(ks.multi)
        self.assertTrue(ks.has_points)
        self.assertEqual(ks.num_questions, 12)
        # The written question is pinned, so every key skips the same row
        skips = {keyformat.load_key_file(str(p))['metadata']['questions_to_skip'] for p in paths}
        self.assertEqual(len(skips), 1)
        self.assertEqual(ks.skip, [int(skips.pop())])
        self.assertTrue(ks.grouped)
        self.assertEqual(ks.notes, [])

    def test_single_version(self):
        paths = self.write_build(1)
        ks = scan_keys.load_keys([str(paths[0])])
        self.assertFalse(ks.multi)
        self.assertEqual(ks.written, 1)
        self.assertEqual(ks.notes, [])

    def test_older_key_takes_its_letter_from_the_name(self):
        paths = self.write_build(2)
        for p in paths:
            data = keyformat.load_key_file(str(p))
            del data['metadata']['version']
            keyformat.save_key_file(str(p), data)
        ks = scan_keys.load_keys([str(paths[0])])
        self.assertEqual(sorted(ks.paths), ['A', 'B'])

    def test_unlettered_key_alone(self):
        key = self.out / 'my key.csv'
        keyformat.save_key_file(str(key), {'bubble_answers': {'Q001': 'A', 'Q002': 'B'},
                                           'open_questions': {}, 'metadata': {}})
        ks = scan_keys.load_keys([str(key)])
        self.assertEqual(list(ks.paths), [''])
        self.assertEqual(ks.num_questions, 2)
        self.assertFalse(ks.has_points)

    def test_two_keys_for_one_version_refused(self):
        paths = self.write_build(1)
        copy = self.out / 'copy.csv'
        shutil.copy(paths[0], copy)
        with self.assertRaises(scan_keys.KeySetError):
            scan_keys.load_keys([str(paths[0]), str(copy)])


if __name__ == '__main__':
    unittest.main()
