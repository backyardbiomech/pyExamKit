'''
The Results tab opens an outputs folder, shows each view without a Tk
callback failing and with every control inside the window, and makes and
exports edits. A label that set its wrap from its own size once resized
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


def _squeezed(root, widget) -> bool:
    """True when a widget is hidden, shown smaller than it asks to be, or runs
    past the window's edges. Tables and charts may shrink; controls may not."""
    # A dropdown's menu is a popup, not part of the layout, so where it sits
    # says nothing about whether the view fits
    if widget.winfo_class() in ('Treeview', 'Menu') or any(
            name in str(widget) for name in ('gradechart', 'choicebars')):
        return False
    if not widget.winfo_ismapped():
        return True
    x = widget.winfo_rootx() - root.winfo_rootx()
    y = widget.winfo_rooty() - root.winfo_rooty()
    return (widget.winfo_width() < widget.winfo_reqwidth() - 2
            or widget.winfo_height() < widget.winfo_reqheight() - 2
            or x < 0 or y < 0 or x + widget.winfo_width() > root.winfo_width() + 1
            or y + widget.winfo_height() > root.winfo_height() + 1)


def _leaves(widget):
    kids = widget.winfo_children()
    if not kids:
        yield widget
    for k in kids:
        yield from _leaves(k)


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
    outside = []
    smallest = '%dx%d' % tuple(root.tk.call('wm', 'minsize', root._w))
    for view in VIEWS:
        ui._show(view)
        ui.q_tree.selection_set(ui.q_tree.get_children()[0])
        ui.s_tree.selection_set(ui.s_tree.get_children()[0])
        # At the window's first size and its smallest, every control shows
        for size in ('840x860', smallest):
            root.geometry(size)
            for _ in range(5):
                root.update()
            outside += [f'{view} at {size}: {w.winfo_class()} {w}'
                        for w in _leaves(ui.frames[view]) if _squeezed(root, w)]
    shown = {'opened': opened, 'errors': errors, 'outside': outside,
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
        self.assertEqual(shown, {'opened': True, 'errors': [], 'outside': [], 'students': 5,
                                 'answers': 3})

    def test_edits_made_and_exported(self):
        run = subprocess.run([sys.executable, __file__, 'edit', str(self.out)], cwd=ROOT,
                             capture_output=True, text=True, timeout=TIME_LIMIT)
        self.assertEqual(run.returncode, 0, run.stderr)
        done = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual(done['errors'], [])
        self.assertEqual(done['edits'], [
            'Everyone: +1 point',
            'bank.md#2: also accept C',
            'bank.md#3: dropped',
            'COLE, X, Version A Q001: 0.5 points'])
        self.assertEqual(done['notes'], ['curve', '', 'bad stem', 'partly right'])
        self.assertTrue(done['unexported_before'])
        self.assertFalse(done['unexported_after'])
        # Each out of 2 with bank.md#3 dropped, then +1: COLE has 0.5 on Q001
        # and Q002 right by the also-accepted C
        self.assertEqual(done['canvas'], {'L1': 3, 'L2': 3, 'L3': 2.5, 'L4': 3, 'L5': 3})
        self.assertIn('marked', done['notice'])
        self.assertEqual(done['after_delete'], 3)

    def test_a_students_version_changed_through_the_tab(self):
        run = subprocess.run([sys.executable, __file__, 'version', str(self.out)], cwd=ROOT,
                             capture_output=True, text=True, timeout=TIME_LIMIT)
        self.assertEqual(run.returncode, 0, run.stderr)
        done = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual(done['errors'], [])
        self.assertEqual(done['edits'], ['COLE, X: version A scored as version B'])
        # Scored against B's key, COLE is in B's students and says where they came from
        self.assertEqual(done['version'], 'B')
        self.assertEqual(done['read_as'], 'A')
        self.assertIn('bubbled as A', done['label'])
        self.assertIn('rescan', done['notice'])

    def test_a_folder_without_results(self):
        from results_tab import ResultsUI
        root = _tk_root()
        said = []
        empty = self.out.parent / 'empty'
        empty.mkdir()
        try:
            self.assertFalse(ResultsUI(root, log_fn=said.append).open(empty))
        finally:
            root.destroy()
        self.assertIn('no app_data folder', said[0])


def edit_through_the_tab(outdir) -> dict:
    """Make one edit of each kind with the tab's own controls, export, and
    report the edits, the Canvas file, and what the tab said."""
    import csv
    import results_model as rm
    from results_tab import ResultsUI
    root = _tk_root()
    errors = []
    root.report_callback_exception = lambda *exc: errors.append(repr(exc[1]))
    ui = ResultsUI(root, log_fn=lambda msg: None)
    ui.pack(fill='both', expand=True)
    ui.open(outdir)
    root.update()

    def put(entry, text):
        entry.delete(0, 'end')
        entry.insert(0, text)

    def pick(tree, table, match):
        iid = next(i for i, row in getattr(ui, table).items() if match(row))
        tree.selection_set(iid)
        root.update()

    put(ui.adjust_entries[''], '1')
    put(ui.adjust_note_entry, 'curve')
    ui.adjust_button.invoke()
    pick(ui.q_tree, '_questions', lambda q: q.label == 'bank.md#2')
    put(ui.key_entry, 'C')
    ui.also_button.invoke()
    pick(ui.q_tree, '_questions', lambda q: q.label == 'bank.md#3')
    put(ui.q_note_entry, 'bad stem')
    ui.drop_button.invoke()
    pick(ui.s_tree, '_students', lambda s: s.name.startswith('COLE'))
    pick(ui.a_tree, '_answers', lambda a: a.question == 'Q001')
    put(ui.o_points_entry, '0.5')
    put(ui.o_note_entry, 'partly right')
    ui.override_button.invoke()
    unexported_before = ui.res.unexported
    ui.export_button.invoke()
    root.update()
    with open(f'{outdir}/canvas_upload.csv', encoding='utf-8') as f:
        canvas = {r[1]: float(r[2]) for r in list(csv.reader(f))[2:]}
    done = {'errors': errors, 'edits': [rm.describe(ui.res, e) for e in ui.res.edits],
            'notes': [e['note'] for e in ui.res.edits], 'canvas': canvas,
            'unexported_before': unexported_before, 'unexported_after': ui.res.unexported,
            'notice': ui.notice.cget('text')}
    # And the override undone from the Edits view
    pick(ui.e_tree, '_edits', lambda e: e['type'] == 'override')
    ui.delete_button.invoke()
    done['after_delete'] = len(ui.res.edits)
    root.destroy()
    return done


def change_version_through_the_tab(outdir) -> dict:
    """Move a student to the version their sheet really was with the tab's
    own control, and report what the tab then shows for them."""
    import results_model as rm
    from results_tab import ResultsUI
    root = _tk_root()
    errors = []
    root.report_callback_exception = lambda *exc: errors.append(repr(exc[1]))
    ui = ResultsUI(root, log_fn=lambda msg: None)
    ui.pack(fill='both', expand=True)
    ui.open(outdir)
    root.update()
    iid = next(i for i, s in ui._students.items() if s.name.startswith('COLE'))
    ui.s_tree.selection_set(iid)
    root.update()
    ui.version_menu.set('B')
    ui.version_button.invoke()
    root.update()
    moved = next(s for s in ui._students.values() if s.name.startswith('COLE'))
    done = {'errors': errors, 'edits': [rm.describe(ui.res, e) for e in ui.res.edits],
            'version': moved.version, 'read_as': moved.read_as,
            'label': ui.student_label.cget('text'), 'notice': ui.notice.cget('text')}
    root.destroy()
    return done


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == 'version':
    print(json.dumps(change_version_through_the_tab(sys.argv[2])))
elif __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == 'edit':
    print(json.dumps(edit_through_the_tab(sys.argv[2])))
elif __name__ == '__main__' and len(sys.argv) == 2 and not sys.argv[1].startswith('-'):
    print(json.dumps(show_every_view(sys.argv[1])))
elif __name__ == '__main__':
    unittest.main()
