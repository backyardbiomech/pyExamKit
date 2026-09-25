"""
HTML exam output: font size, margins, footer, math, filenames, and images.

Page breaks are the browser's job once the exam is printed (the template
asks for break-inside: avoid on every question), so these tests read the
HTML the renderer writes rather than a printed page. docs/dev/pdf-output-plan.md
records why the exam is HTML rather than a PDF the app writes itself.
"""
import dataclasses
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from exam_builder import FONT_SIZES
from models import Answer, ExamVersion, Question
from parser import parse_file
from renderer import ExamRenderer

FIXTURE_INPUT = Path(__file__).parent / 'fixtures' / 'build_migration' / 'input'


def _mc(text: str, image_paths=(), folder: Path = FIXTURE_INPUT) -> Question:
    return Question(q_type='MC', text=text, image_paths=list(image_paths), source_folder=folder,
                    answers=[Answer('yes', True), Answer('no', False)])


def _exam(questions: list[Question]) -> ExamVersion:
    return ExamVersion(title='Edge', course='TEST101', version_num=1, questions=questions,
                       source_folder=FIXTURE_INPUT)


class HtmlOutput(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix='html_output_test_'))
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def _render(self, version: ExamVersion, **kwargs) -> tuple[str, Path, list[str]]:
        path, warnings = ExamRenderer().to_html(version, self.tmpdir, **kwargs)
        return path.read_text(encoding='utf-8'), path, warnings

    def test_font_size_sets_the_body_size(self):
        for name, pt in FONT_SIZES.items():
            with self.subTest(size=name):
                text, _, _ = self._render(_exam([_mc('one')]), font_size=name)
                self.assertRegex(text, rf'body \{{[^}}]*font-size: {pt}pt;')

    def test_sizes_other_than_medium_are_named_in_the_filename(self):
        _, medium, _ = self._render(_exam([_mc('one')]))
        _, large, _ = self._render(_exam([_mc('one')]), font_size='large')
        self.assertEqual((medium.name, large.name), ('Edge_vA.html', 'Edge_vA_large.html'))

    def test_unknown_font_size_is_rejected(self):
        with self.assertRaises(ValueError):
            ExamRenderer().to_html(_exam([_mc('x')]), self.tmpdir, font_size='huge')

    def test_page_margins_are_three_quarters_of_an_inch_top_and_bottom(self):
        text, _, _ = self._render(_exam([_mc('one')]))
        self.assertIn('margin: 0.75in 0.5in;', text)

    def test_every_question_asks_not_to_be_split_across_pages(self):
        text, _, _ = self._render(_exam([_mc('one')]))
        self.assertRegex(text, r'\.question-block \{[^}]*break-inside: avoid;')

    def test_version_appears_only_at_the_end_when_several_are_built(self):
        # Printed where a neighbor cannot read it: never in the header or footer.
        single, _, _ = self._render(_exam([_mc('one')]))
        several, _, _ = self._render(_exam([_mc('one')]), total_versions=2)
        for text in (single, several):
            self.assertIn('content: "Page " counter(page) " of " counter(pages);', text)
            self.assertNotIn('Version A', text)
        self.assertNotIn('class="version-end"', single)
        self.assertIn('This is exam version <strong>A</strong>', several)

    def test_math_reaches_mathjax_with_markup_characters_escaped(self):
        bank = self.tmpdir / 'math.txt'
        bank.write_text('MC\n1. If $a<b$ and **c**, which holds?\n*A. $x & y$\nB. neither\n',
                        encoding='utf-8')
        questions, _ = parse_file(bank)
        text, _, warnings = self._render(_exam(questions))
        self.assertIn('$a&lt;b$', text)
        self.assertIn('$x &amp; y$', text)
        self.assertIn('<strong>c</strong>', text)  # formatting outside math is untouched
        self.assertNotIn('$a<b$', text)
        self.assertIn('mathjax', text)
        self.assertEqual(warnings, [])

    def test_images_are_copied_beside_the_exam(self):
        text, _, warnings = self._render(_exam([_mc('pic', ['testImage.png'])]))
        self.assertTrue((self.tmpdir / 'images' / 'testImage.png').exists())
        self.assertIn('src="images/testImage.png"', text)
        self.assertEqual(warnings, [])

    def test_missing_image_is_named_in_a_warning(self):
        text, _, warnings = self._render(_exam([_mc('where is it', ['nope.png'])]))
        self.assertIn('where is it', text)
        self.assertEqual(len(warnings), 1)
        self.assertIn('nope.png', warnings[0])

    def _bank(self, name: str, image_bytes: bytes) -> Path:
        """A bank folder holding images/cell.png with the given content."""
        folder = self.tmpdir / name
        (folder / 'images').mkdir(parents=True)
        (folder / 'images' / 'cell.png').write_bytes(image_bytes)
        return folder

    def test_output_in_the_bank_folder_leaves_its_images_alone(self):
        bank = self._bank('bank', b'one')
        path, warnings = ExamRenderer().to_html(
            _exam([_mc('pic', ['images/cell.png'], folder=bank)]), bank)
        self.assertEqual((bank / 'images' / 'cell.png').read_bytes(), b'one')
        self.assertIn('src="images/cell.png"', path.read_text(encoding='utf-8'))
        self.assertEqual(warnings, [])

    def test_same_named_images_from_two_banks_both_survive(self):
        a, b = self._bank('a', b'one'), self._bank('b', b'two')
        out = self.tmpdir / 'out'
        path, _ = ExamRenderer().to_html(
            _exam([_mc('first', ['images/cell.png'], folder=a),
                   _mc('second', ['images/cell.png'], folder=b)]), out)
        text = path.read_text(encoding='utf-8')
        self.assertEqual((out / 'images' / 'cell.png').read_bytes(), b'one')
        self.assertEqual((out / 'images' / 'cell_2.png').read_bytes(), b'two')
        self.assertLess(text.index('images/cell.png'), text.index('images/cell_2.png'))

    def test_a_renamed_image_keeps_its_name_in_every_version(self):
        a, b = self._bank('a', b'one'), self._bank('b', b'two')
        out = self.tmpdir / 'out'
        renderer = ExamRenderer()
        renderer.to_html(_exam([_mc('first', ['images/cell.png'], folder=a),
                                _mc('second', ['images/cell.png'], folder=b)]), out)
        # A later version drawing only bank b must not claim cell.png for it.
        only_b = dataclasses.replace(_exam([_mc('second', ['images/cell.png'], folder=b)]),
                                     version_num=2)
        path, _ = renderer.to_html(only_b, out)
        self.assertIn('src="images/cell_2.png"', path.read_text(encoding='utf-8'))
        self.assertEqual((out / 'images' / 'cell.png').read_bytes(), b'one')


if __name__ == '__main__':
    unittest.main()
