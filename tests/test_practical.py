'''
Lab practical source files: parsing, validation, and writing answers back.

    python -m unittest tests.test_practical -v
'''
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import keyformat  # noqa: E402
import practical  # noqa: E402

SOURCE = '''---
title: Practical 3
forms: AB, CD, AC, BD
points: 1
---

Anything up here is the author's own and is ignored.

# Station 1: kidney model
setup: Kidney model, frontal section.
setup: Pins A to D.
image: images/kidney.png

A. Name the structure at pin A.
= renal pelvis
~ pelvis

B. Name the structure
at pin B.
= renal pyramid | medullary pyramid

C) Name the structure at pin C.
=renal cortex|cortex
<!-- medulla was accepted in 2025; not any more -->

D. What passes through pin D?
image: images/ureter.png
(2 pts)
= urine

## Station 2
A. Name the vessel.
= afferent arteriole
B. Name the tissue.
= simple squamous epithelium
C. Name the organ.
= bladder | urinary bladder
D. Name the duct.
= ureter
'''


def write(text: str, suffix='.md') -> Path:
    f = tempfile.NamedTemporaryFile('w', suffix=suffix, delete=False, encoding='utf-8',
                                    newline='')
    f.write(text)
    f.close()
    return Path(f.name)


class TestParse(unittest.TestCase):
    def setUp(self):
        self.p = practical.parse(SOURCE)

    def test_front_matter(self):
        self.assertEqual(self.p.title, 'Practical 3')
        self.assertEqual(self.p.forms, ['AB', 'CD', 'AC', 'BD'])
        self.assertEqual(self.p.letters, 'ABCD')

    def test_stations(self):
        s1, s2 = self.p.stations
        self.assertEqual(s1.name, 'kidney model')
        self.assertEqual(s1.setup, ['Kidney model, frontal section.', 'Pins A to D.'])
        self.assertEqual(s1.images, ['images/kidney.png'])
        self.assertEqual(s2.number, 2)

    def test_questions(self):
        q = self.p.question('1B')
        self.assertEqual(q.text, 'Name the structure at pin B.')
        self.assertEqual(q.full, ['renal pyramid', 'medullary pyramid'])
        self.assertEqual(self.p.question('openQ_1A').partial, ['pelvis'])
        self.assertEqual(self.p.question('1C').full, ['renal cortex', 'cortex'])
        d = self.p.question('1D')
        self.assertEqual((d.points, d.images), (2.0, ['images/ureter.png']))

    def test_grading_order_is_station_then_letter(self):
        keys = [q.key for q in self.p.questions()]
        self.assertEqual(keys[:5], ['1A', '1B', '1C', '1D', '2A'])

    def test_form_questions_and_points(self):
        self.assertEqual(self.p.keys_for_form('AC'), ['1A', '1C', '2A', '2C'])
        self.assertEqual(self.p.total_points('BD'), 5)     # 1D is worth 2

    def test_comment_before_front_matter(self):
        p = practical.parse('<!-- a note\nabout the file -->\n\n' + SOURCE)
        self.assertEqual((p.title, p.forms), ('Practical 3', ['AB', 'CD', 'AC', 'BD']))

    def test_default_forms(self):
        p = practical.parse(SOURCE.replace('forms: AB, CD, AC, BD\n', ''))
        self.assertEqual(p.forms, practical.DEFAULT_FORMS)

    def test_ten_sorts_after_nine(self):
        text = '\n'.join(f'# Station {n}\nA. q\n= a\nB. q\n= b' for n in range(1, 11))
        p = practical.parse('---\nforms: AB\n---\n' + text)
        self.assertEqual([q.key for q in p.questions()][-3:], ['9B', '10A', '10B'])


class TestErrors(unittest.TestCase):
    def assertProblem(self, text, fragment):
        with self.assertRaises(practical.PracticalError) as cm:
            practical.parse(text)
        self.assertIn(fragment, str(cm.exception))

    def test_no_stations(self):
        self.assertProblem('A. a question\n= answer\n', 'No stations')

    def test_numbering(self):
        self.assertProblem('# Station 1\nA. q\n# Station 3\nA. q\n', 'numbered 1 to 2')

    def test_missing_letter_a_form_uses(self):
        self.assertProblem('---\nforms: AC\n---\n# Station 1\nA. q\n= a\n', 'no question C')

    def test_bad_form(self):
        self.assertProblem('---\nforms: AE\n---\n# Station 1\nA. q\n', '"AE"')

    def test_stray_text_before_question_a(self):
        self.assertProblem('---\nforms: AB\n---\n# Station 1\nKidney model\nA. q\nB. q\n',
                           'setup:')

    def test_unclosed_front_matter(self):
        self.assertProblem('---\ntitle: x\n# Station 1\n', 'never closes')

    def test_missing_answer_is_a_warning(self):
        p = practical.parse('---\nforms: AB\n---\n# Station 1\nA. q\nB. q\n= b\n')
        self.assertEqual(p.warnings, ['1A has no full-credit answer.'])


class TestKeyFile(unittest.TestCase):
    def test_load_key_file_reads_a_practical(self):
        data = keyformat.load_key_file(str(write(SOURCE)))
        self.assertEqual(data['open_questions']['openQ_1A']['full'], ['renal pelvis'])
        self.assertEqual(data['point_values']['openQ_1D'], 2.0)
        self.assertEqual(data['metadata']['forms'], 'AB,CD,AC,BD')

    def test_is_practical(self):
        self.assertTrue(practical.is_practical(write(SOURCE)))
        self.assertFalse(practical.is_practical(write('# Notes\nnothing here\n')))


class TestSync(unittest.TestCase):
    def sync(self, source, key, full=None, partial=None):
        path = write(source)
        data = practical.to_key_data(practical.load(path))['open_questions']
        if full is not None:
            data[f'openQ_{key}']['full'] = full
        if partial is not None:
            data[f'openQ_{key}']['partial'] = partial
        n = practical.sync_answers(path, data)
        return n, path.read_text(encoding='utf-8')

    def test_nothing_changed_leaves_file_byte_identical(self):
        n, text = self.sync(SOURCE, '1A')
        self.assertEqual((n, text), (0, SOURCE))

    def test_new_full_answer_goes_after_the_last_full_line(self):
        n, text = self.sync(SOURCE, '1A', full=['renal pelvis', 'pelvis of kidney'])
        self.assertEqual(n, 1)
        self.assertIn('= renal pelvis\n= pelvis of kidney\n~ pelvis\n', text)
        self.assertEqual(len(text.splitlines()), len(SOURCE.splitlines()) + 1)

    def test_new_partial_with_none_before_goes_after_full(self):
        n, text = self.sync(SOURCE, '2C', partial=['kidney'])
        self.assertIn('= bladder | urinary bladder\n~ kidney\nD. Name the duct.', text)

    def test_removal_rewrites_only_that_line(self):
        n, text = self.sync(SOURCE, '1B', full=['renal pyramid'])
        self.assertEqual(n, 1)
        self.assertIn('at pin B.\n= renal pyramid\n\nC)', text)
        self.assertIn('=renal cortex|cortex\n', text)       # untouched spacing elsewhere

    def test_emptied_line_is_dropped(self):
        n, text = self.sync(SOURCE, '1A', partial=[])
        self.assertNotIn('~ pelvis', text)
        self.assertIn('= renal pelvis\n\nB. Name', text)

    def test_moving_full_to_partial(self):
        n, text = self.sync(SOURCE, '1C', full=['renal cortex'], partial=['cortex'])
        self.assertEqual(n, 2)
        self.assertIn('= renal cortex\n~ cortex\n<!--', text)

    def test_answer_after_image_and_points_lines(self):
        n, text = self.sync(SOURCE, '1D', full=['urine', 'filtrate'])
        self.assertIn('= urine\n= filtrate\n', text)
        self.assertEqual(practical.parse(text).question('1D').points, 2.0)

    def test_round_trip_through_save_key_file(self):
        path = write(SOURCE.replace('\n', '\r\n'))
        data = keyformat.load_key_file(str(path))
        data['open_questions']['openQ_2A']['full'].append('afferent artery')
        keyformat.save_key_file(str(path), data)
        raw = path.read_bytes().decode('utf-8')
        self.assertIn('= afferent arteriole\r\n= afferent artery\r\n', raw)
        self.assertEqual(practical.load(path).question('2A').full,
                         ['afferent arteriole', 'afferent artery'])


class TestImportOldKeys(unittest.TestCase):
    HEADER = 'type,question,page,x1,y1,x2,y2,answer,partial_answers\n'

    def test_union_across_forms(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
        import practical_from_keys as pk
        ab = write(self.HEADER + 'open,openQ_1A,1,1,1,2,2,renal pelvis,pelvis\n'
                   'open,openQ_1B,1,3,1,4,2,renal pyramid,\n', '.csv')
        ac = write(self.HEADER + 'open,openQ_1A,1,1,1,2,2,renal pelvis|pelvis,\n'
                   'open,openQ_1C,1,3,1,4,2,cortex,\n', '.csv')
        questions, forms, notes = pk.merge([ab, ac])
        self.assertEqual(forms, {'AB', 'AC'})
        self.assertEqual(questions[(1, 'A')], {'full': ['renal pelvis', 'pelvis'], 'partial': []})
        self.assertTrue(any('1A: kept as full credit' in n for n in notes))
        text = pk.render('P', questions, forms)
        p = practical.parse(text)
        self.assertEqual(p.forms, ['AB', 'AC'])
        self.assertEqual(p.question('1C').full, ['cortex'])
        self.assertEqual(p.stations[0].setup, [])


if __name__ == '__main__':
    unittest.main()
