"""
HTML exam output: font size, margins, footer, math, filenames, and images.

Page breaks are the browser's job once the exam is printed (the template
asks for break-inside: avoid on every question), so these tests read the
HTML the renderer writes rather than a printed page. docs/dev/pdf-output-plan.md
records why the exam is HTML rather than a PDF the app writes itself.
"""
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

    def test_footer_names_the_version_only_when_several_are_built(self):
        single, _, _ = self._render(_exam([_mc('one')]))
        several, _, _ = self._render(_exam([_mc('one')]), total_versions=2)
        self.assertIn('content: "Page " counter(page) " of " counter(pages);', single)
        self.assertIn('content: "Version A · Page " counter(page) " of " counter(pages);', several)

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


if __name__ == '__main__':
    unittest.main()
