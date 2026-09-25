"""
help_links.py

Where each tab's Help button goes: that tab's page in the user guide on
GitHub, opened in the browser. The docs are markdown, which Tk cannot render,
and GitHub shows them with their links and the README's diagram working.

A released app links to the docs as they were at its own release tag, so an
older copy opens the docs that describe it; a development copy links to main.
"""
import re
import webbrowser
from importlib import metadata

REPO = 'https://github.com/backyardbiomech/pyExamKit'

# Tab name -> page under docs/, or '' for the README
TAB_PAGES = {
    'Build Exam': 'building-exams.md',
    'Build Practical': 'lab-practicals.md',
    'Scan Exams': 'scanning-and-grading.md',
    'Re-grade': 'open-ended-questions.md#re-grading-afterward',
    'Standard Sheet': 'building-keys.md',
}


def _ref() -> str:
    '''The release tag this copy was built from, or main when it was not
    built from one (a .dev or .post version, or no package metadata).'''
    try:
        found = metadata.version('pyexamkit')
    except metadata.PackageNotFoundError:
        return 'main'
    return f'v{found}' if re.fullmatch(r'\d+(\.\d+)*', found) else 'main'


def url_for(tab: str) -> str:
    page = TAB_PAGES.get(tab, '')
    if not page:
        return f'{REPO}/blob/{_ref()}/README.md'
    return f'{REPO}/blob/{_ref()}/docs/{page}'


def open_help(tab: str) -> str:
    '''Open the tab's help page in the browser; returns the URL.'''
    url = url_for(tab)
    webbrowser.open(url)
    return url
