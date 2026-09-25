'''
Roster loading and ID matching. Every name and ID here is invented.

    python -m unittest tests.test_roster -v
'''
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import roster  # noqa: E402


def write(text: str) -> Path:
    f = tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8')
    f.write(text)
    f.close()
    return Path(f.name)


class TestLoad(unittest.TestCase):
    def test_plain_three_columns(self):
        r, desc = roster.load_roster(write(
            'LastName,FirstName,ID\nDoe,Jon,L10123456\nRoe,Ann,00987654\n'))
        self.assertEqual(r['10123456'].last, 'Doe')
        self.assertEqual(r['00987654'].first, 'Ann')
        self.assertIn('2 students', desc)
        self.assertNotIn('Doe', desc)          # safe to log

    def test_leading_zeros_dropped_by_a_spreadsheet(self):
        r, _ = roster.load_roster(write('Last Name,First Name,Student ID\nDoe,Jon,123456\n'))
        self.assertIn('00123456', r)

    def test_canvas_gradebook_export(self):
        r, desc = roster.load_roster(write(
            'Student,ID,SIS User ID,SIS Login ID,Section,Exam 1 (1234)\n'
            '    Points Possible,,,,,100\n'
            '"Doe, Jon",55501,L10123456,jdoe,BIOL 206-01,88\n'
            '"Student, Test",55599,,,BIOL 206-01,\n'))
        self.assertEqual(list(r), ['10123456'])
        self.assertEqual((r['10123456'].last, r['10123456'].first), ('Doe', 'Jon'))
        self.assertIn('SIS User ID', desc)

    def test_id_column_found_by_content(self):
        r, _ = roster.load_roster(write('Last,First,Number\nDoe,Jon,L10123456\n'))
        self.assertIn('10123456', r)

    def test_no_names_is_an_error(self):
        with self.assertRaises(roster.RosterError):
            roster.load_roster(write('ID,Score\nL10123456,5\n'))


class TestMatch(unittest.TestCase):
    R = {s.id: s for s in [roster.Student('Doe', 'Jon', '00123456'),
                           roster.Student('Roe', 'Ann', '00987654')]}

    def test_exact(self):
        s, note = roster.match_id('00123456', self.R)
        self.assertEqual((s.last, note), ('Doe', ''))

    def test_one_digit_off(self):
        s, note = roster.match_id('00123457', self.R)
        self.assertEqual(s.last, 'Doe')
        self.assertIn('one digit off', note)

    def test_one_blank_column(self):
        s, _ = roster.match_id('0012-456', self.R)
        self.assertEqual(s.last, 'Doe')

    def test_unmatched(self):
        s, note = roster.match_id('11111111', self.R)
        self.assertIsNone(s)
        self.assertEqual(note, 'not on the roster')


if __name__ == '__main__':
    unittest.main()
