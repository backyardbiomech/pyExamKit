'''
Help links: each tab's page in the user guide, at this release's tag.

    python -m unittest tests.test_help_links -v
'''
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import help_links  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / 'docs'


class TestHelpLinks(unittest.TestCase):
    def test_every_page_exists(self):
        for tab, page in help_links.TAB_PAGES.items():
            self.assertTrue((DOCS / page.split('#')[0]).is_file(), tab)

    def test_release_links_to_its_tag(self):
        with mock.patch.object(help_links.metadata, 'version', return_value='3.3.1'):
            self.assertEqual(help_links.url_for('Build Practical'),
                             f'{help_links.REPO}/blob/v3.3.1/docs/lab-practicals.md')

    def test_development_copy_links_to_main(self):
        for v in ('3.3.1.post2.dev0', '3.3.1.dev4+gabc123'):
            with mock.patch.object(help_links.metadata, 'version', return_value=v):
                self.assertIn('/blob/main/', help_links.url_for('Scan Exams'))
        with mock.patch.object(help_links.metadata, 'version',
                               side_effect=help_links.metadata.PackageNotFoundError):
            self.assertIn('/blob/main/', help_links.url_for('Scan Exams'))

    def test_unknown_tab_opens_readme(self):
        self.assertTrue(help_links.url_for('Nope').endswith('/README.md'))


if __name__ == '__main__':
    unittest.main()
