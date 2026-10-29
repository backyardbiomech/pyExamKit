'''
The Results tab opens an outputs folder and shows each view without a Tk
callback failing. A label that set its wrap from its own size once resized
itself, and the chart beside it, without end. That loop runs inside Tk
where Python cannot interrupt it, so the views are shown in a child process
with a time limit.

    python -m unittest tests.test_results_tab -v
'''
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from test_edits import make_outputs  # noqa: E402

# Showing every view takes about a second; a layout loop never finishes
TIME_LIMIT = 60


def _tk_root():
    try:
        import customtkinter as ctk
        return ctk.CTk()
    except Exception:
        return None


def show_every_view(outdir) -> dict:
    """Open outdir in the app's Results tab, show each view with a question and a student
    selected, and report what went wrong and what was shown."""
    import gui
    from results_tab import VIEWS
    root = _tk_root()
    errors = []
    root.report_callback_exception = lambda *exc: errors.append(repr(exc[1]))
    # In the whole app, where the loop showed: the bare tab sized differently
    app = gui.pyScanUI(root)
    ui = app.results
    opened = ui.open(outdir)
    app._tabs.set('Results')
    for view in VIEWS:
        ui._show(view)
        ui.q_tree.selection_set(ui.q_tree.get_children()[0])
        ui.s_tree.selection_set(ui.s_tree.get_children()[0])
        for _ in range(5):
            root.update()
    shown = {'opened': opened, 'errors': errors,
             'students': len(ui.s_tree.get_children()), 'answers': len(ui.a_tree.get_children())}
    root.destroy()
    return shown


class ResultsTabTest(unittest.TestCase):
    def setUp(self):
        root = _tk_root()
        if root is None:
            self.skipTest('no display for Tk')
        root.destroy()
        self.out, _ = make_outputs(Path(tempfile.mkdtemp()))

    def tearDown(self):
        shutil.rmtree(self.out.parent)

    def test_every_view_shows(self):
        try:
            run = subprocess.run([sys.executable, __file__, str(self.out)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=TIME_LIMIT)
        except subprocess.TimeoutExpired:
            self.fail(f'showing the views took over {TIME_LIMIT} s: a layout loop')
        self.assertEqual(run.returncode, 0, run.stderr)
        shown = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual(shown, {'opened': True, 'errors': [], 'students': 5, 'answers': 3})

    def test_a_folder_without_results(self):
        from results_tab import ResultsUI
        root = _tk_root()
        said = []
        try:
            self.assertFalse(ResultsUI(root, log_fn=said.append).open(self.out.parent))
        finally:
            root.destroy()
        self.assertTrue(said)


if __name__ == '__main__' and len(sys.argv) == 2 and not sys.argv[1].startswith('-'):
    print(json.dumps(show_every_view(sys.argv[1])))
elif __name__ == '__main__':
    unittest.main()
