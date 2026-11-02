"""
browser_pdf.py

Prints a built exam's HTML to PDF with a headless Chrome or Edge, so there
is a PDF to send without opening each version in a browser. A browser is
used because the exam's equations need MathJax (see renderer.py); the PDF
matches what the browser's own print dialog gives, footer included.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Long enough for MathJax to load from its CDN and typeset; virtual time
# runs fast when the page is idle, so a page without math does not wait it out.
_BUDGET_MS = 15000
_TIMEOUT_S = 90


def _candidates() -> list[str]:
    if sys.platform == 'darwin':
        return [f'/Applications/{app}.app/Contents/MacOS/{app}'
                for app in ('Google Chrome', 'Microsoft Edge', 'Chromium')]
    if sys.platform == 'win32':
        roots = [os.environ.get(k, '') for k in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')]
        return [str(Path(r) / sub) for r in roots if r
                for sub in (r'Google\Chrome\Application\chrome.exe',
                            r'Microsoft\Edge\Application\msedge.exe')]
    return [p for name in ('google-chrome', 'chromium', 'chromium-browser', 'microsoft-edge')
            if (p := shutil.which(name))]


def find_browser() -> str | None:
    """Path to an installed Chrome, Edge, or Chromium, or None."""
    return next((c for c in _candidates() if Path(c).is_file()), None)


def print_one(browser: str, html_path: Path) -> Path:
    """Print html_path to a PDF of the same name beside it."""
    pdf_path = html_path.with_suffix('.pdf')
    # Its own profile, so a browser the user already has open does not take
    # the job and leave headless printing nothing.
    with tempfile.TemporaryDirectory(prefix='pyexamkit_pdf_') as profile:
        subprocess.run(
            [browser, '--headless', '--disable-gpu', '--no-pdf-header-footer',
             f'--virtual-time-budget={_BUDGET_MS}', f'--user-data-dir={profile}',
             f'--print-to-pdf={pdf_path}', html_path.resolve().as_uri()],
            capture_output=True, timeout=_TIMEOUT_S, check=False)
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f'the browser wrote no PDF for {html_path.name}')
    return pdf_path


def print_all(html_paths: list[Path]) -> tuple[list[Path], list[str]]:
    """Print each HTML file to PDF, all at once. Returns (PDFs, warnings)."""
    browser = find_browser()
    if browser is None:
        return [], ['No PDF written: Chrome or Edge is needed to print the exam to PDF. '
                    'Print the HTML from a browser instead.']
    pdfs, warnings = [], []
    stale = [p.with_suffix('.pdf') for p in html_paths]
    for p in stale:
        p.unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=len(html_paths) or 1) as pool:
        futures = [pool.submit(print_one, browser, p) for p in html_paths]
        for p, f in zip(html_paths, futures):
            try:
                pdfs.append(f.result())
            except Exception as exc:
                warnings.append(f'No PDF for {p.name}: {exc}')
    return pdfs, warnings
