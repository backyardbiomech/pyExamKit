"""
results_tab.py

The Results tab: a scan's results with their edits applied, as summary
statistics and a grade chart, a table of questions, and a table of students,
and the place to make those edits: adjustments, key changes and credit for a
question, one student's points on one question. Each edit is saved to
app_data/edits.json as it is made; Export rewrites the gradebook and Canvas
file. A scan opens the tab on its own outputs folder when it finishes;
Choose… opens any earlier one. docs/dev/results-tab.md has the design, and
results_model.py the numbers and the edits.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import customtkinter as ctk

import analysis
import charts
import outputs
import results_model as rm

VIEWS = ('Summary', 'Questions', 'Students', 'Edits')
FLAG_FILL = {'Light': '#F8CBAD', 'Dark': '#6B3A2A'}     # the gradebook's flag color, and a dark one
PENDING_COLOR = ('#B35C00', '#E8A33D')                  # edits not yet exported
ERROR_COLOR = ('#C0392B', '#FF7B6B')


def _fmt(x, digits: int = 2) -> str:
    if x is None:
        return ''
    x = round(float(x), digits)
    return f'{int(x)}' if x.is_integer() else f'{x:g}'


def _number(text: str, what: str = 'Points') -> float:
    try:
        return float(text.strip() or 0)
    except ValueError:
        raise ValueError(f'{what} must be a number.') from None


def _with_pct(x, possible) -> str:
    if x is None:
        return ''
    return f'{_fmt(x)} ({x / possible:.1%})' if possible else _fmt(x)


def open_file(path: Path) -> None:
    """Open a file in the system's own viewer."""
    if sys.platform == 'darwin':
        subprocess.run(['open', str(path)], check=False)
    elif sys.platform == 'win32':
        os.startfile(str(path))  # noqa: S606 (a marked sheet the app wrote)
    else:
        subprocess.run(['xdg-open', str(path)], check=False)


class ResultsUI(ctk.CTkFrame):
    def __init__(self, parent, log_fn):
        super().__init__(parent, fg_color='transparent')
        self.log_fn = log_fn
        self.res: rm.Results | None = None
        self._build_ui()

    # ── Layout ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        bold = ctk.CTkFont(weight='bold')
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.pack(fill='x')
        ctk.CTkLabel(header, text='Outputs folder', font=bold).pack(side='left')
        self.folder_entry = ctk.CTkEntry(header, width=420)
        self.folder_entry.pack(side='left', padx=(8, 0), fill='x', expand=True)
        self.folder_entry.bind('<Return>', lambda e: self.open(self.folder_entry.get().strip()))
        ctk.CTkButton(header, text='Choose…', width=90, command=self._choose).pack(
            side='left', padx=(6, 0))
        self.export_button = ctk.CTkButton(header, text='Export', width=90, state='disabled',
                                           command=self._export)
        self.export_button.pack(side='left', padx=(6, 0))
        self.status = ctk.CTkLabel(self, text='Scan exams, or choose the ExamScanner_outputs '
                                              'folder of an earlier scan.',
                                   anchor='w', justify='left', text_color='gray',
                                   font=ctk.CTkFont(size=12))
        self.status.pack(fill='x', pady=(4, 0))
        # Whether the gradebook and Canvas file carry the edits, and what the
        # last action did
        self.notice = ctk.CTkLabel(self, text='', anchor='w', justify='left',
                                   font=ctk.CTkFont(size=12))
        self.notice.pack(fill='x', pady=(0, 4))
        # Wrap to the tab's width, not the label's own: a label that sets its
        # wrap from its own size resizes itself, and so on without end
        def wrap(e):
            for label in (self.status, self.notice):
                label.configure(wraplength=max(e.width - 8, 200))
        self.bind('<Configure>', wrap)

        self.switch = ctk.CTkSegmentedButton(self, values=list(VIEWS), command=self._show)
        self.switch.pack(anchor='w', pady=(0, 6))
        self.switch.set(VIEWS[0])
        self.body = ctk.CTkFrame(self, fg_color='transparent')
        self.body.pack(fill='both', expand=True)
        self._style_trees()
        self.frames = {'Summary': self._summary_view(), 'Questions': self._questions_view(),
                       'Students': self._students_view(), 'Edits': self._edits_view()}
        self._show(VIEWS[0])

    def _style_trees(self):
        """ttk tables in the colors of the customtkinter theme around them."""
        mode = charts.mode()
        dark = mode == 'Dark'
        bg, fg = ('#2B2B2B', '#DCE4EE') if dark else ('#FFFFFF', '#1A1A1A')
        head = '#3A3A3A' if dark else '#E5E5E5'
        style = ttk.Style(self)
        style.theme_use('clam' if 'clam' in style.theme_names() else style.theme_use())
        style.configure('Results.Treeview', background=bg, fieldbackground=bg, foreground=fg,
                        rowheight=22, borderwidth=0)
        style.configure('Results.Treeview.Heading', background=head, foreground=fg,
                        relief='flat')
        style.map('Results.Treeview', background=[('selected', '#2A78D6')],
                  foreground=[('selected', '#FFFFFF')])
        for tree in getattr(self, '_trees', []):
            tree.tag_configure('flag', background=FLAG_FILL[mode])

    def _tree(self, parent, columns: list[tuple[str, str, int]], height: int
              ) -> tuple[ttk.Treeview, tk.Frame]:
        """A sortable table; columns are (id, heading, width), the first left-aligned."""
        frame = tk.Frame(parent)
        tree = ttk.Treeview(frame, columns=[c for c, _, _ in columns], show='headings',
                            height=height, style='Results.Treeview', selectmode='browse')
        for i, (cid, heading, width) in enumerate(columns):
            tree.heading(cid, text=heading, command=lambda c=cid: self._sort(tree, c))
            tree.column(cid, width=width, anchor='w' if i == 0 else 'center',
                        stretch=i == 0)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        # The scrollbar first, so a narrow window narrows the table instead
        scroll.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)
        self._trees = getattr(self, '_trees', []) + [tree]
        tree.tag_configure('flag', background=FLAG_FILL[charts.mode()])
        return tree, frame

    def _sort(self, tree: ttk.Treeview, col: str):
        """Sort by a column, numbers as numbers; a second click reverses."""
        rows = [(tree.set(iid, col), iid) for iid in tree.get_children('')]

        def key(v):
            try:
                return (0, float(v[0].split(' ')[0]))
            except ValueError:
                return (1, v[0].lower())
        reverse = getattr(tree, '_sorted', None) == col
        rows.sort(key=key, reverse=reverse)
        for i, (_, iid) in enumerate(rows):
            tree.move(iid, '', i)
        tree._sorted = None if reverse else col

    def _summary_view(self):
        f = ctk.CTkFrame(self.body, fg_color='transparent')
        self.stats_grid = ctk.CTkFrame(f, fg_color='transparent')
        self.stats_grid.pack(fill='x', anchor='w')
        row = ctk.CTkFrame(f, fg_color='transparent')
        row.pack(fill='x', pady=(6, 2))
        ctk.CTkLabel(row, text='Note').pack(side='left', padx=(8, 6))
        self.adjust_note_entry = ctk.CTkEntry(row, placeholder_text='why, for the edits list')
        self.adjust_note_entry.pack(side='left', fill='x', expand=True)
        self.adjust_button = ctk.CTkButton(row, text='Apply points added', width=150,
                                           state='disabled', command=self._apply_adjustments)
        self.adjust_button.pack(side='left', padx=(6, 0))
        self.adjust_note = ctk.CTkLabel(f, text='', anchor='w', text_color='gray',
                                        font=ctk.CTkFont(size=12))
        self.adjust_note.pack(fill='x', pady=(0, 2))
        self.grade_chart = charts.GradeChart(f, height=240)
        self.grade_chart.pack(fill='both', expand=True, pady=(4, 0))
        return f

    def _questions_view(self):
        f = ctk.CTkFrame(self.body, fg_color='transparent')
        self.q_tree, frame = self._tree(f, [
            ('label', 'Question', 150), ('where', 'On sheet', 90), ('key', 'Key', 70),
            ('points', 'Points', 55), ('n', 'Students', 65), ('mean', 'Mean score', 80),
            ('r', 'Discrimination', 95), ('di', 'Canvas DI', 75)], height=9)
        self.q_tree.bind('<<TreeviewSelect>>', lambda e: self._show_question())
        detail = ctk.CTkFrame(f, fg_color='transparent')
        self.q_text = ctk.CTkLabel(detail, text='Select a question to see how it was answered. '
                                                'Shaded questions have a discrimination below '
                                                '0.2: worth rereading.',
                                   anchor='nw', justify='left', width=300, wraplength=290)
        self.q_text.pack(side='left', fill='y', padx=(0, 8))
        self.choice_bars = charts.ChoiceBars(detail, height=170)
        self.choice_bars.pack(side='left', fill='both', expand=True)

        # The actions, on the selected question: on every version that
        # printed it when the versions were matched by bank question
        actions = ctk.CTkFrame(f, fg_color='transparent')
        one = ctk.CTkFrame(actions, fg_color='transparent')
        one.pack(fill='x')
        ctk.CTkLabel(one, text='Key').pack(side='left', padx=(0, 6))
        self.key_entry = ctk.CTkEntry(one, width=80)
        self.key_entry.pack(side='left')
        self.change_key_button = ctk.CTkButton(one, text='Change key', width=100,
                                               command=lambda: self._key_action(also=False))
        self.change_key_button.pack(side='left', padx=(6, 0))
        self.also_button = ctk.CTkButton(one, text='Also accept', width=100,
                                         command=lambda: self._key_action(also=True))
        self.also_button.pack(side='left', padx=(6, 0))
        ctk.CTkLabel(one, text='Points').pack(side='left', padx=(18, 6))
        self.q_points_entry = ctk.CTkEntry(one, width=60)
        self.q_points_entry.pack(side='left')
        self.set_points_button = ctk.CTkButton(one, text='Set points', width=90,
                                               command=lambda: self._credit_action('points'))
        self.set_points_button.pack(side='left', padx=(6, 0))
        two = ctk.CTkFrame(actions, fg_color='transparent')
        two.pack(fill='x', pady=(6, 0))
        self.full_button = ctk.CTkButton(two, text='Full credit to everyone', width=170,
                                         command=lambda: self._credit_action('full'))
        self.full_button.pack(side='left')
        self.drop_button = ctk.CTkButton(two, text='Drop question', width=120,
                                         command=lambda: self._credit_action('drop'))
        self.drop_button.pack(side='left', padx=(6, 0))
        ctk.CTkLabel(two, text='Note').pack(side='left', padx=(18, 6))
        self.q_note_entry = ctk.CTkEntry(two, placeholder_text='why, for the edits list')
        self.q_note_entry.pack(side='left', fill='x', expand=True)
        # Packed from the bottom up, and the table last, so a short window
        # shortens the table rather than hiding the actions
        actions.pack(side='bottom', fill='x', pady=(8, 0))
        detail.pack(side='bottom', fill='x', pady=(8, 0))
        frame.pack(fill='both', expand=True)
        self._question_buttons = (self.change_key_button, self.also_button,
                                  self.set_points_button, self.full_button, self.drop_button)
        self._enable(self._question_buttons, False)
        return f

    def _students_view(self):
        f = ctk.CTkFrame(self.body, fg_color='transparent')
        right = ctk.CTkFrame(f, fg_color='transparent')
        right.pack(side='right', fill='both', padx=(10, 0))
        left = ctk.CTkFrame(f, fg_color='transparent')
        left.pack(side='left', fill='both', expand=True)
        self.s_tree, frame = self._tree(left, [
            ('name', 'Student', 170), ('id', 'ID', 80), ('version', 'Version', 60),
            ('total', 'Total', 60), ('adjusted', 'Adjusted', 70), ('pct', '%', 60)], height=16)
        frame.pack(fill='both', expand=True)
        self.s_tree.bind('<<TreeviewSelect>>', lambda e: self._show_student())
        self.student_label = ctk.CTkLabel(right, text='Select a student.', anchor='w',
                                          font=ctk.CTkFont(weight='bold'))
        self.student_label.pack(fill='x')
        self.a_tree, frame = self._tree(right, [
            ('q', 'Question', 80), ('ans', 'Answer', 70), ('key', 'Key', 70),
            ('pts', 'Points', 80)], height=13)
        answers = frame
        self.a_tree.bind('<<TreeviewSelect>>', lambda e: self._show_answer())
        row = ctk.CTkFrame(right, fg_color='transparent')
        ctk.CTkLabel(row, text='Points').pack(side='left', padx=(0, 6))
        self.o_points_entry = ctk.CTkEntry(row, width=60)
        self.o_points_entry.pack(side='left')
        self.override_button = ctk.CTkButton(row, text='Set', width=60,
                                             command=self._set_override)
        self.override_button.pack(side='left', padx=(6, 0))
        self.clear_override_button = ctk.CTkButton(row, text='Clear', width=60,
                                                   command=self._clear_override)
        self.clear_override_button.pack(side='left', padx=(6, 0))
        self.o_note_entry = ctk.CTkEntry(right, placeholder_text='note, for the edits list')
        legend = ctk.CTkLabel(right, text='* points set by hand', anchor='w', text_color='gray',
                              font=ctk.CTkFont(size=12))
        self._enable((self.override_button, self.clear_override_button), False)
        self.marked_button = ctk.CTkButton(right, text='Open marked sheet', width=160,
                                           state='disabled', command=self._open_marked)
        # From the bottom up, the answers table last, as on Questions
        self.marked_button.pack(side='bottom', anchor='e', pady=(4, 0))
        legend.pack(side='bottom', fill='x')
        self.o_note_entry.pack(side='bottom', fill='x', pady=(6, 0))
        row.pack(side='bottom', fill='x')
        answers.pack(fill='both', expand=True, pady=(4, 6))
        return f

    def _edits_view(self):
        f = ctk.CTkFrame(self.body, fg_color='transparent')
        self.e_tree, frame = self._tree(f, [
            ('what', 'Edit', 330), ('note', 'Note', 220), ('time', 'Made', 130)], height=14)
        self.e_tree.bind('<<TreeviewSelect>>', lambda e: self._show_edit())
        ctk.CTkLabel(f, text='Edits apply in this order: key changes, then credit, then points '
                             'set by hand, then points added. Deleting an edit undoes it. Shaded '
                             'edits matched nothing in these results.',
                     anchor='w', justify='left', text_color='gray', wraplength=640,
                     font=ctk.CTkFont(size=12)).pack(side='bottom', fill='x', pady=(6, 0))
        row = ctk.CTkFrame(f, fg_color='transparent')
        row.pack(side='bottom', fill='x', pady=(6, 0))
        ctk.CTkLabel(row, text='Note').pack(side='left', padx=(0, 6))
        self.e_note_entry = ctk.CTkEntry(row)
        self.e_note_entry.pack(side='left', fill='x', expand=True)
        self.save_note_button = ctk.CTkButton(row, text='Save note', width=100,
                                              command=self._save_note)
        self.save_note_button.pack(side='left', padx=(6, 0))
        self.delete_button = ctk.CTkButton(row, text='Delete edit', width=100,
                                           fg_color=ERROR_COLOR, hover_color=('#962D22', '#C9584B'),
                                           command=self._delete_edit)
        self.delete_button.pack(side='left', padx=(6, 0))
        frame.pack(fill='both', expand=True)
        self._enable((self.save_note_button, self.delete_button), False)
        return f

    @staticmethod
    def _enable(buttons, on: bool):
        for b in buttons:
            b.configure(state='normal' if on else 'disabled')

    def _show(self, view: str):
        for name, frame in self.frames.items():
            if name == view:
                frame.pack(fill='both', expand=True)
            else:
                frame.pack_forget()

    # ── Loading ────────────────────────────────────────────────────────────

    def _choose(self):
        folder = filedialog.askdirectory(title='Choose the ExamScanner_outputs folder')
        if folder:
            self.open(folder)

    def open(self, outdir) -> bool:
        """Show the results in an outputs folder; False, with the reason in
        the log, when it holds none."""
        if not outdir:
            return False
        try:
            res = rm.open_folder(outdir)
        except ValueError as exc:
            self.log_fn(str(exc))
            return False
        self._load(res)
        self._say('')
        return True

    def _load(self, res: rm.Results):
        """Show res, keeping whatever question, student, and edit was selected
        when it is the same folder again."""
        same = self.res is not None and self.res.outdir == res.outdir
        keep = (self._selected(self.q_tree, '_questions', lambda q: q.label),
                self._selected(self.s_tree, '_students', lambda s: (s.version, s.row)),
                self._selected(self.a_tree, '_answers', lambda a: a.question),
                self._selected(self.e_tree, '_edits', lambda e: e['id'])) if same else (None,) * 4
        self.res = res
        self.folder_entry.delete(0, 'end')
        self.folder_entry.insert(0, str(res.outdir))
        self._style_trees()
        self._fill_status()
        self._fill_summary()
        self._fill_questions()
        self._fill_students()
        self._fill_edits()
        self.export_button.configure(state='normal')
        q, s, a, e = keep
        self._reselect(self.q_tree, '_questions', lambda x: x.label, q, self._show_question)
        if self._reselect(self.s_tree, '_students', lambda x: (x.version, x.row), s,
                          self._show_student):
            self._reselect(self.a_tree, '_answers', lambda x: x.question, a, self._show_answer)
        self._reselect(self.e_tree, '_edits', lambda x: x['id'], e, self._show_edit)

    def _selected(self, tree, table: str, ident):
        sel = tree.selection()
        rows = getattr(self, table, {})
        return ident(rows[sel[0]]) if sel and sel[0] in rows else None

    def _reselect(self, tree, table: str, ident, wanted, show) -> bool:
        if wanted is None:
            return False
        for iid, row in getattr(self, table, {}).items():
            if ident(row) == wanted:
                tree.selection_set(iid)
                tree.see(iid)
                show()          # now, not on the event, so what follows sees it
                return True
        return False

    def _say(self, text: str, error: bool = False):
        """The last action's outcome, after whether the edits are exported."""
        res = self.res
        parts = []
        if res is not None:
            if res.unexported:
                parts.append('Edits made since the last export: Export rewrites gradebook.xlsx '
                             'and canvas_upload.csv with them.')
            elif res.edits:
                parts.append('gradebook.xlsx and canvas_upload.csv carry every edit.')
        if text:
            parts.append(text)
        color = ERROR_COLOR if error else PENDING_COLOR if res is not None and res.unexported \
            else ('gray20', 'gray80')
        self.notice.configure(text='  '.join(parts), text_color=color)

    def _edit(self, make, done: str = '', clear=None):
        """Run one edit (make returns the results opened again), then show
        them and empty the note entry clear."""
        if self.res is None:
            return
        try:
            res = make()
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        except OSError as exc:
            self._say(f'Could not save the edit: {exc}', error=True)
            return
        if clear is not None:
            clear.delete(0, 'end')
        self._load(res)
        self._say(done)

    def _fill_status(self):
        res = self.res
        n = sum(len(g.students) for g in res.graded)
        parts = [res.title or res.outdir.parent.name,
                 f'{n} students' + (f', {len(res.graded)} versions' if res.multi else '')]
        if res.edits:
            parts.append(f'{len(res.edits)} edit{"s" if len(res.edits) != 1 else ""} applied')
        if res.problems:
            parts.append(f'{len(res.problems)} edit(s) matched nothing (see the log)')
            for msg in res.problems:
                self.log_fn(msg)
        if res.legacy:
            parts.append('scanned before grading settings were recorded: a key change would '
                         'rescore with the Scan tab\'s defaults')
        self.status.configure(text='  ·  '.join(parts))

    def _fill_summary(self):
        res = self.res
        for w in self.stats_grid.winfo_children():
            w.destroy()
        adjusted = bool(res.adjust)
        cols = rm.columns(res)
        bold = ctk.CTkFont(weight='bold')
        header = []
        for c in cols:
            header += [c.label] + (['Adjusted'] if adjusted else [])
        for j, text in enumerate([''] + header):
            ctk.CTkLabel(self.stats_grid, text=text, font=bold).grid(
                row=0, column=j, padx=8, sticky='e' if j else 'w')
        # Points added, under each column as in the gradebook: the class, then
        # each version, a student getting the class's plus their version's
        ctk.CTkLabel(self.stats_grid, text='Points added').grid(row=1, column=0, padx=8,
                                                                sticky='w')
        self.adjust_entries = {}
        versions = [''] + ([g.version for g in res.graded] if res.multi else [])
        for j, v in enumerate(versions):
            entry = ctk.CTkEntry(self.stats_grid, width=70, justify='right')
            entry.insert(0, _fmt(res.adjust.get(v, 0)))
            entry.bind('<Return>', lambda e: self._apply_adjustments())
            entry.grid(row=1, column=1 + j * (2 if adjusted else 1),
                       columnspan=2 if adjusted else 1, padx=8, pady=(2, 4), sticky='e')
            self.adjust_entries[v] = entry
        self.adjust_button.configure(state='normal')
        rows = [('Students', lambda s, p: _fmt(s['n'])),
                ('Points possible', lambda s, p: _fmt(p) if p else 'varies'),
                ('Mean', lambda s, p: _with_pct(s['mean'], p)),
                ('Median', lambda s, p: _with_pct(s['median'], p)),
                ('Standard deviation', lambda s, p: _fmt(s['sd'])),
                ('Highest', lambda s, p: _with_pct(s['highest'], p)),
                ('Lowest', lambda s, p: _with_pct(s['lowest'], p))]
        for i, (label, show) in enumerate(rows, 2):
            ctk.CTkLabel(self.stats_grid, text=label).grid(row=i, column=0, padx=8, sticky='w')
            values = []
            for c in cols:
                values.append(show(c.before, c.possible))
                if adjusted:
                    values.append(show(c.after, c.possible))
            for j, v in enumerate(values, 1):
                ctk.CTkLabel(self.stats_grid, text=v).grid(row=i, column=j, padx=8, sticky='e')
        i = len(rows) + 2
        ctk.CTkLabel(self.stats_grid, text="Reliability (Cronbach's alpha)").grid(
            row=i, column=0, padx=8, sticky='w')
        for j, c in enumerate(cols):
            ctk.CTkLabel(self.stats_grid, text=_fmt(c.alpha)).grid(
                row=i, column=1 + j * (2 if adjusted else 1), padx=8, sticky='e')

        if adjusted:
            parts = [f'{"Everyone" if v == "" else "Version " + v} +{_fmt(p)}'
                     for v, p in sorted(res.adjust.items())]
            self.adjust_note.configure(text='Adjustments: ' + ', '.join(parts)
                                       + '. Not capped at the points possible.')
        else:
            self.adjust_note.configure(text='Type points to add (a negative number takes '
                                            'points away) and apply them.')
        before, after = rm.grade_counts(res)
        bands = [b[0] for b in analysis.BANDS]
        series = [('Unadjusted', [before[b] for b in bands], charts.UNADJUSTED_COLOR)]
        if adjusted:
            series.append(('Adjusted', [after[b] for b in bands], charts.ADJUSTED_COLOR))
        else:
            series = [('Students', series[0][1], charts.ADJUSTED_COLOR)]
        self.grade_chart.set_data(bands, series)

    def _fill_questions(self):
        self.q_tree.delete(*self.q_tree.get_children())
        self._questions = {}
        for i, q in enumerate(rm.questions(self.res)):
            iid = str(i)
            self._questions[iid] = q
            self.q_tree.insert('', 'end', iid=iid, tags=('flag',) if q.flagged else (), values=(
                q.label, q.where, q.key, _fmt(q.points), q.n, _fmt(q.mean), _fmt(q.r),
                _fmt(q.di)))
        self.choice_bars.set_data([], set())
        self._enable(self._question_buttons, False)

    def _question(self) -> rm.Question | None:
        sel = self.q_tree.selection()
        return self._questions.get(sel[0]) if sel else None

    def _show_question(self):
        q = self._question()
        if q is None:
            return
        self._enable(self._question_buttons, True)
        self._enable((self.change_key_button, self.also_button), not q.written)
        for entry, value in ((self.key_entry, '' if q.written else q.key.replace(' or ', ', ')),
                             (self.q_points_entry, _fmt(q.points))):
            entry.delete(0, 'end')
            entry.insert(0, value)
        lines = [f'{q.label}  ({q.where})']
        if q.text:
            lines.append(q.text)
        lines.append(f'Key: {q.key}')
        if q.written:
            lines.append('Written: its acceptable answers change on the Re-grade tab.')
        self.q_text.configure(text='\n'.join(lines))
        if q.written:
            # A written answer's 'choices' are the grader's CC, CX, and the rest
            labels = {'CC': 'Full credit', 'CX': 'Half credit'}
            rows = [(labels.get(k, 'No credit'), v) for k, v in q.counts.items()]
            merged = {}
            for k, v in rows:
                merged[k] = merged.get(k, 0) + v
            self.choice_bars.set_data(list(merged.items()), {'Full credit'})
        else:
            keys = {ch for k in q.key.split(' or ') for ch in k}
            self.choice_bars.set_data(list(q.counts.items()), keys)

    def _fill_students(self):
        self.s_tree.delete(*self.s_tree.get_children())
        self._students = {}
        for i, s in enumerate(rm.students(self.res)):
            iid = str(i)
            self._students[iid] = s
            pct = s.adjusted / s.possible if s.possible else None
            self.s_tree.insert('', 'end', iid=iid, values=(
                s.name, s.student_id, s.version, _fmt(s.total), _fmt(s.adjusted),
                f'{pct:.1%}' if pct is not None else ''))
        self.a_tree.delete(*self.a_tree.get_children())
        self._answers = {}
        self.student_label.configure(text='Select a student.')
        self.marked_button.configure(state='disabled')
        self._enable((self.override_button, self.clear_override_button), False)

    def _student(self) -> rm.Student | None:
        sel = self.s_tree.selection()
        return self._students.get(sel[0]) if sel else None

    def _show_student(self):
        sel = self.s_tree.selection()
        if not sel:
            return
        s = self._students[sel[0]]
        self.student_label.configure(
            text=s.name + (f'  ·  Version {s.version}' if self.res.multi else ''))
        self.a_tree.delete(*self.a_tree.get_children())
        self._answers = {}
        self._enable((self.override_button, self.clear_override_button), False)
        for i, a in enumerate(rm.answers(self.res, s.version, s.row)):
            if a.possible is None:
                pts = 'dropped' if a.earned is not None else ''
            elif a.earned is None:
                pts = 'not on form'
            else:
                pts = f'{_fmt(a.earned)} / {_fmt(a.possible)}' + (' *' if a.overridden else '')
            wrong = a.earned is not None and a.possible and a.earned < a.possible
            self._answers[str(i)] = a
            self.a_tree.insert('', 'end', iid=str(i), values=(a.question, a.answer, a.key, pts),
                               tags=('flag',) if wrong else ())
        pages = rm.marked_pages(self.res, s.version, s.row)
        self._marked = pages
        self.marked_button.configure(state='normal' if pages else 'disabled')

    def _answer(self) -> rm.Answer | None:
        sel = self.a_tree.selection()
        return self._answers.get(sel[0]) if sel else None

    def _show_answer(self):
        a = self._answer()
        if a is None:
            return
        # Not on the student's form, or dropped: there are no points to set
        settable = a.earned is not None and a.possible is not None
        self._enable((self.override_button,), settable)
        self._enable((self.clear_override_button,), a.overridden)
        self.o_points_entry.delete(0, 'end')
        if settable:
            self.o_points_entry.insert(0, _fmt(a.earned))

    def _open_marked(self):
        for page in getattr(self, '_marked', []):
            open_file(page)

    # ── Edits ──────────────────────────────────────────────────────────────

    @staticmethod
    def _note(entry) -> str:
        return entry.get().strip()

    def _apply_adjustments(self):
        try:
            points = {v: _number(e.get(), 'Points added') for v, e in self.adjust_entries.items()}
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        if all(p == self.res.adjust.get(v, 0) for v, p in points.items()):
            self._say('The points added are unchanged.')
            return
        note = self._note(self.adjust_note_entry)
        self._edit(lambda: rm.set_adjustments(self.res, points, note), 'Points added applied.',
                   self.adjust_note_entry)

    def _key_action(self, also: bool):
        q = self._question()
        if q is None:
            return
        try:
            keys = rm.parse_keys(self.key_entry.get())
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        note = self._note(self.q_note_entry)
        left = len(rm.overrides_on(self.res, q))
        done = f'{q.label}: {"also accepting" if also else "key changed to"} {" or ".join(keys)}.'
        if left:
            done += (f' {left} point{"s" if left != 1 else ""} set by hand on this question '
                     'still stand over the new key.')
        self._edit(lambda: rm.add(self.res, rm.key_edit(self.res, q, keys, also, note)), done,
                   self.q_note_entry)

    def _credit_action(self, action: str):
        q = self._question()
        if q is None:
            return
        try:
            points = _number(self.q_points_entry.get()) if action == 'points' else None
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        note = self._note(self.q_note_entry)
        done = {'full': f'{q.label}: full credit to everyone who had it.',
                'drop': f'{q.label} dropped. Delete the edit on the Edits view to bring it back.',
                'points': f'{q.label} is worth {_fmt(points)} points.'}[action]
        self._edit(lambda: rm.add(self.res, rm.credit_edit(self.res, q, action, points, note)),
                   done, self.q_note_entry)

    def _set_override(self):
        s, a = self._student(), self._answer()
        if s is None or a is None:
            return
        try:
            points = _number(self.o_points_entry.get())
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        note = self._note(self.o_note_entry)
        self._edit(lambda: rm.add(self.res, rm.override_edit(
            self.res, s.version, s.row, a.question, points, note)),
                   f'{s.name}, {a.question}: {_fmt(points)} points.', self.o_note_entry)

    def _clear_override(self):
        s, a = self._student(), self._answer()
        if s is None or a is None:
            return
        ids = [e['id'] for e in self.res.edits if e['type'] == 'override'
               and e.get('version') == s.version and str(e.get('row')) == s.row
               and e.get('question') == a.question]
        self._edit(lambda: rm.delete(self.res, ids), f'{s.name}, {a.question}: scored as graded.')

    def _fill_edits(self):
        self.e_tree.delete(*self.e_tree.get_children())
        self._edits = {}
        unmatched = {msg.split(' ')[2] for msg in self.res.problems}    # 'kind edit <id> …'
        for i, e in enumerate(self.res.edits):
            iid = str(i)
            self._edits[iid] = e
            self.e_tree.insert('', 'end', iid=iid,
                               tags=('flag',) if e['id'] in unmatched else (),
                               values=(rm.describe(self.res, e), e.get('note', ''),
                                       e.get('time', '').replace('T', ' ')))
        self.e_note_entry.delete(0, 'end')
        self._enable((self.save_note_button, self.delete_button), False)

    def _edit_selected(self) -> dict | None:
        sel = self.e_tree.selection()
        return self._edits.get(sel[0]) if sel else None

    def _show_edit(self):
        e = self._edit_selected()
        if e is None:
            return
        self._enable((self.save_note_button, self.delete_button), True)
        self.e_note_entry.delete(0, 'end')
        self.e_note_entry.insert(0, e.get('note', ''))

    def _save_note(self):
        e = self._edit_selected()
        if e is not None:
            self._edit(lambda: rm.set_note(self.res, e['id'], self.e_note_entry.get().strip()),
                       'Note saved.')

    def _delete_edit(self):
        e = self._edit_selected()
        if e is not None:
            self._edit(lambda: rm.delete(self.res, e['id']),
                       f'Deleted: {rm.describe(self.res, e)}.')

    # ── Export ─────────────────────────────────────────────────────────────

    def _export(self):
        """Rewrite the gradebook and Canvas file with every edit in. What
        outputs.write prints goes to the log."""
        if self.res is None:
            return
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            saved = outputs.write(self.res.outdir)
        for line in printed.getvalue().splitlines():
            self.log_fn(line)
        try:
            res = rm.open_folder(self.res.outdir)
        except ValueError as exc:
            self._say(str(exc), error=True)
            return
        self._load(res)
        if not saved:
            self._say('Export failed: a file could not be saved (see the log). Close '
                      'gradebook.xlsx or canvas_upload.csv if they are open, and export again.',
                      error=True)
            return
        done = 'Exported.'
        if any(e['type'] in ('key', 'credit') for e in res.edits):
            done += (' The marked sheets (marked/, marked.pdf) still show the original key '
                     'and points.')
        self._say(done)
