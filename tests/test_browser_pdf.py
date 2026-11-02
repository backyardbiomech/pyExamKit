'''
A build prints each exam's HTML to a PDF of the same name with a headless
Chrome or Edge, and says so when there is no browser to do it.

    python -m unittest tests.test_browser_pdf -v
'''
import random
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import browser_pdf  # noqa: E402
from exam_builder import BuildConfig, ExamBuilder  # noqa: E402
from renderer import ExamRenderer  # noqa: E402

BANK = ROOT / 'tests' / 'fixtures' / 'build_migration' / 'input' / 'bank1.txt'


class TestNoBrowser(unittest.TestCase):

    def test_warns_and_writes_nothing(self):
        with mock.patch.object(browser_pdf, 'find_browser', return_value=None):
            pdfs, warnings = browser_pdf.print_all([Path('Exam_vA.html')])
        self.assertEqual(pdfs, [])
        self.assertIn('Chrome or Edge', warnings[0])


@unittest.skipIf(browser_pdf.find_browser() is None, 'no Chrome or Edge installed')
class TestPrint(unittest.TestCase):

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix='browser_pdf_'))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def test_each_version_gets_a_pdf_named_like_its_html(self):
        config = BuildConfig(title='Print Test', course='', num_versions=2,
                             shuffle_questions=True, shuffle_answers=False, exact_file=BANK,
                             pools=[], version_question=False, version_question_position='last',
                             default_points=1.0)
        random.seed(1)
        versions, _ = ExamBuilder().build(config)
        renderer = ExamRenderer()
        htmls = [renderer.to_html(v, self.out, 2, 1.0, 'large')[0] for v in versions]
        pdfs, warnings = browser_pdf.print_all(htmls)
        self.assertEqual(warnings, [])
        self.assertEqual([p.name for p in pdfs], ['Print_Test_vA_large.pdf', 'Print_Test_vB_large.pdf'])
        doc = fitz.open(pdfs[0])
        self.assertEqual((doc[0].rect.width, doc[0].rect.height), (612, 792))
        text = ''.join(page.get_text() for page in doc)
        self.assertIn(f'Page 1 of {doc.page_count}', text)
        self.assertIn(versions[0].questions[0].text.split('<')[0][:30], text)


if __name__ == '__main__':
    unittest.main()
