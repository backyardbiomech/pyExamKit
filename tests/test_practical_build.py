'''
Lab practical printed materials: placards, setup guide, and instructor key.

    python -m unittest tests.test_practical_build -v
'''
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import practical  # noqa: E402
import practical_build  # noqa: E402
import practical_tab  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'practical' / 'practical_test.md'


def pages(pdf: bytes) -> list[str]:
    # Without ligatures, so "stratified" reads back as typed
    flags = fitz.TEXTFLAGS_TEXT & ~fitz.TEXT_PRESERVE_LIGATURES
    return [pg.get_text(flags=flags) for pg in fitz.open(stream=pdf, filetype='pdf')]


def one_station(body: str) -> practical.Practical:
    '''A single-station practical beside the fixture, so its images resolve.'''
    text = f'---\ntitle: T\nforms: AB, CD\n---\n# Station 1: secret name\nsetup: hidden\n{body}'
    return practical.parse(text, FIXTURE)


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = practical.load(FIXTURE)
        cls.b = practical_build.Builder(cls.p)
        cls.placards = pages(cls.b.placards())
        cls.guide_pdf = cls.b.setup_guide()
        cls.guide = '\n'.join(pages(cls.guide_pdf))
        cls.key_pdf = cls.b.instructor_key()
        cls.key = '\n'.join(pages(cls.key_pdf))

    def test_writes_every_file(self):
        with tempfile.TemporaryDirectory() as d:
            written, warnings = practical_build.build(self.p, Path(d), students=12, logo=None)
            names = {w.name for w in written}
        self.assertEqual(warnings, [])
        for part in ('placards', 'setup_guide', 'instructor_key', 'form_AB',
                     'all_forms_12_students'):
            self.assertTrue(any(part in n for n in names), part)

    def test_one_placard_per_station(self):
        self.assertEqual(len(self.placards), len(self.p.stations))
        for s, text in zip(self.p.stations, self.placards):
            self.assertIn(f'Station {s.number}', text)
            for q in s.questions.values():
                self.assertIn(q.text, ' '.join(text.split()))

    def test_placards_keep_setup_and_names_from_students(self):
        for s, text in zip(self.p.stations, self.placards):
            self.assertNotIn(s.name, text)
            for line in s.setup:
                self.assertNotIn(line, text)

    def test_placards_print_images(self):
        doc = fitz.open(stream=self.b.placards(), filetype='pdf')
        self.assertTrue(doc[0].get_images())          # station 1's image
        self.assertTrue(doc[19].get_images())         # 20D's image
        self.assertFalse(doc[1].get_images())

    def test_question_image_prints_full_width_under_its_question(self):
        page = fitz.open(stream=self.b.placards(), filetype='pdf')[19]      # 20D
        img = page.get_image_rects(page.get_images()[0][0])[0]
        d_text = page.search_for('D. Name')[0]
        self.assertGreater(img.width, 400)
        self.assertGreater(img.y0, d_text.y1)

    def test_guide_has_names_setup_and_answers(self):
        guide = ' '.join(self.guide.split())
        for s in self.p.stations:
            self.assertIn(s.name, guide)
            for line in s.setup:
                self.assertIn(line, guide)
        self.assertIn('renal pelvis', guide)
        self.assertIn('images/station20d.png', guide)

    def test_key_has_answers_and_points(self):
        key = ' '.join(self.key.split())
        for q in self.p.questions():
            for a in q.full + q.partial:
                self.assertIn(a, key)
        self.assertIn('2 pts', key)                   # 24A

    def test_columns_stay_fixed(self):
        '''A long answer must not squeeze the question column: every header
        starts at the same place on every page.'''
        for pdf in (self.guide_pdf, self.key_pdf):
            xs = {round(w[0]) for pg in fitz.open(stream=pdf, filetype='pdf')
                  for w in pg.get_text('words') if w[4] == 'Full'}
            self.assertEqual(len(xs), 1, xs)

    def test_pages_are_numbered(self):
        n = len(fitz.open(stream=self.key_pdf, filetype='pdf'))
        self.assertIn(f'page {n} of {n}', self.key)


class TestProblems(unittest.TestCase):
    def test_missing_image_is_warned_and_marked(self):
        p = one_station('image: images/nope.png\nA. Name A.\n= a\nB. Name B.\n= b\n'
                        'C. c\n= c\nD. d\n= d\n')
        b = practical_build.Builder(p)
        self.assertTrue(any('images/nope.png' in w for w in b.warnings))
        self.assertIn('Missing image', pages(b.placards())[0])
        self.assertIn('Missing', ' '.join(pages(b.setup_guide())))

    def test_question_and_station_images_share_the_page(self):
        body = ('image: images/station1.png\nA. Name A.\n= a\nB. Name B.\n'
                'image: images/station20d.png\n= b\nC. c\n= c\nD. d\n= d\n')
        b = practical_build.Builder(one_station(body))
        doc = fitz.open(stream=b.placards(), filetype='pdf')
        self.assertEqual(len(doc), 1)
        self.assertEqual(b.warnings, [])
        page = doc[0]
        rects = sorted((page.get_image_rects(x[0])[0] for x in page.get_images()),
                       key=lambda r: r.y0)
        self.assertEqual(len(rects), 2)
        self.assertGreater(rects[0].y0, page.search_for('B. Name')[0].y1)   # under B
        self.assertLess(rects[0].y1, page.search_for('C. c')[0].y0)
        self.assertGreater(min(r.height for r in rects), practical_build.MIN_IMAGE_H)

    def test_crowded_station_moves_images_to_a_second_page(self):
        long = 'Name the structure at pin A, then describe its function in detail. ' * 3
        body = 'image: images/station1.png\n' + ''.join(
            f'{c}. {long}\n= x\n' for c in 'ABCD')
        b = practical_build.Builder(one_station(body))
        texts = pages(b.placards())
        self.assertEqual(len(texts), 2)
        self.assertIn('Station 1 (continued)', texts[1])
        self.assertTrue(any('second page' in w for w in b.warnings))


class TestTabFields(unittest.TestCase):
    def test_checks(self):
        src = str(FIXTURE)
        self.assertEqual(practical_tab.check_fields(src, '/tmp/x', ''), ('', 0))
        self.assertEqual(practical_tab.check_fields(src, '/tmp/x', ' 48 '), ('', 48))
        self.assertIn('source', practical_tab.check_fields('', '/tmp/x', '')[0])
        self.assertIn('does not exist', practical_tab.check_fields('/no/such.md', '/tmp/x', '')[0])
        self.assertIn('output', practical_tab.check_fields(src, ' ', '')[0])
        self.assertIn('whole number', practical_tab.check_fields(src, '/tmp/x', 'forty')[0])
        self.assertIn('negative', practical_tab.check_fields(src, '/tmp/x', '-2')[0])

    def test_summary(self):
        self.assertEqual(practical_tab.summarize(practical.load(FIXTURE)),
                         'Test Practical: 25 stations, 4 questions each; '
                         'forms AB, CD, AC, BD, AD, BC')


if __name__ == '__main__':
    unittest.main()
