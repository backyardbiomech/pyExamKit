"""
results_tab.py

The Results tab: a scan's results with their edits applied, as summary
statistics and a grade chart, a table of questions, and a table of students.
A scan opens it on its own outputs folder when it finishes; Choose… opens
any earlier one. This phase only shows; the edits themselves are made in
phase 3 (docs/dev/results-tab.md). The numbers come from results_model.py.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import customtkinter as ctk

import analysis
import charts
import results_model as rm

VIEWS = ('Summary', 'Questions', 'Students')
FLAG_FILL = {'Light': '#F8CBAD', 'Dark': '#6B3A2A'}     # the gradebook's flag color, and a dark one


def _fmt(x, digits: int = 2) -> str:
    if x is None:
        return ''
    x = round(float(x), digits)
    return f'{int(x)}' if x.is_integer() else f'{x:g}'


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
        self.status = ctk.CTkLabel(self, text='Scan exams, or choose the ExamScanner_outputs '
                                              'folder of an earlier scan.',
                                   anchor='w', justify='left', text_color='gray',
                                   font=ctk.CTkFont(size=12))
        self.status.pack(fill='x', pady=(4, 4))
        # Wrap to the tab's width, not the label's own: a label that sets its
        # wrap from its own size resizes itself, and so on without end
        self.bind('<Configure>', lambda e: self.status.configure(wraplength=max(e.width - 8, 200)))

        self.switch = ctk.CTkSegmentedButton(self, values=list(VIEWS), command=self._show)
        self.switch.pack(anchor='w', pady=(0, 6))
        self.switch.set(VIEWS[0])
        self.body = ctk.CTkFrame(self, fg_color='transparent')
        self.body.pack(fill='both', expand=True)
        self._style_trees()
        self.frames = {'Summary': self._summary_view(), 'Questions': self._questions_view(),
                       'Students': self._students_view()}
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
        tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
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
        self.adjust_note = ctk.CTkLabel(f, text='', anchor='w', text_color='gray',
                                        font=ctk.CTkFont(size=12))
        self.adjust_note.pack(fill='x', pady=(6, 2))
        self.grade_chart = charts.GradeChart(f, height=240)
        self.grade_chart.pack(fill='both', expand=True, pady=(4, 0))
        return f

    def _questions_view(self):
        f = ctk.CTkFrame(self.body, fg_color='transparent')
        self.q_tree, frame = self._tree(f, [
            ('label', 'Question', 150), ('where', 'On sheet', 90), ('key', 'Key', 70),
            ('points', 'Points', 55), ('n', 'Students', 65), ('mean', 'Mean score', 80),
            ('r', 'Discrimination', 95), ('di', 'Canvas DI', 75)], height=9)
        frame.pack(fill='both', expand=True)
        self.q_tree.bind('<<TreeviewSelect>>', lambda e: self._show_question())
        detail = ctk.CTkFrame(f, fg_color='transparent')
        detail.pack(fill='x', pady=(8, 0))
        self.q_text = ctk.CTkLabel(detail, text='Select a question to see how it was answered. '
                                                'Shaded questions have a discrimination below '
                                                '0.2: worth rereading.',
                                   anchor='nw', justify='left', width=300, wraplength=290)
        self.q_text.pack(side='left', fill='y', padx=(0, 8))
        self.choice_bars = charts.ChoiceBars(detail, height=170)
        self.choice_bars.pack(side='left', fill='both', expand=True)
        return f

    def _students_view(self):
        f = ctk.CTkFrame(self.body, fg_color='transparent')
        left = ctk.CTkFrame(f, fg_color='transparent')
        left.pack(side='left', fill='both', expand=True)
        self.s_tree, frame = self._tree(left, [
            ('name', 'Student', 170), ('id', 'ID', 80), ('version', 'Version', 60),
            ('total', 'Total', 60), ('adjusted', 'Adjusted', 70), ('pct', '%', 60)], height=16)
        frame.pack(fill='both', expand=True)
        self.s_tree.bind('<<TreeviewSelect>>', lambda e: self._show_student())
        right = ctk.CTkFrame(f, fg_color='transparent')
        right.pack(side='left', fill='both', padx=(10, 0))
        self.student_label = ctk.CTkLabel(right, text='Select a student.', anchor='w',
                                          font=ctk.CTkFont(weight='bold'))
        self.student_label.pack(fill='x')
        self.a_tree, frame = self._tree(right, [
            ('q', 'Question', 80), ('ans', 'Answer', 70), ('key', 'Key', 70),
            ('pts', 'Points', 70)], height=13)
        frame.pack(fill='both', expand=True, pady=(4, 6))
        self.marked_button = ctk.CTkButton(right, text='Open marked sheet', width=160,
                                           state='disabled', command=self._open_marked)
        self.marked_button.pack(anchor='e')
        return f

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
        self.res = res
        self.folder_entry.delete(0, 'end')
        self.folder_entry.insert(0, str(res.outdir))
        self._style_trees()
        self._fill_status()
        self._fill_summary()
        self._fill_questions()
        self._fill_students()
        return True

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
        rows = [('Students', lambda s, p: _fmt(s['n'])),
                ('Points possible', lambda s, p: _fmt(p) if p else 'varies'),
                ('Mean', lambda s, p: _with_pct(s['mean'], p)),
                ('Median', lambda s, p: _with_pct(s['median'], p)),
                ('Standard deviation', lambda s, p: _fmt(s['sd'])),
                ('Highest', lambda s, p: _with_pct(s['highest'], p)),
                ('Lowest', lambda s, p: _with_pct(s['lowest'], p))]
        for i, (label, show) in enumerate(rows, 1):
            ctk.CTkLabel(self.stats_grid, text=label).grid(row=i, column=0, padx=8, sticky='w')
            values = []
            for c in cols:
                values.append(show(c.before, c.possible))
                if adjusted:
                    values.append(show(c.after, c.possible))
            for j, v in enumerate(values, 1):
                ctk.CTkLabel(self.stats_grid, text=v).grid(row=i, column=j, padx=8, sticky='e')
        i = len(rows) + 1
        ctk.CTkLabel(self.stats_grid, text="Reliability (Cronbach's alpha)").grid(
            row=i, column=0, padx=8, sticky='w')
        for j, c in enumerate(cols):
            ctk.CTkLabel(self.stats_grid, text=_fmt(c.alpha)).grid(
                row=i, column=1 + j * (2 if adjusted else 1), padx=8, sticky='e')

        if adjusted:
            parts = [f'{"Everyone" if v == "" else "Version " + v} +{_fmt(p)}'
                     for v, p in sorted(res.adjust.items())]
            self.adjust_note.configure(text='Adjustments: ' + ', '.join(parts))
        else:
            self.adjust_note.configure(text='No adjustment.')
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

    def _show_question(self):
        sel = self.q_tree.selection()
        if not sel:
            return
        q = self._questions[sel[0]]
        lines = [f'{q.label}  ({q.where})']
        if q.text:
            lines.append(q.text)
        lines.append(f'Key: {q.key}')
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
        self.student_label.configure(text='Select a student.')
        self.marked_button.configure(state='disabled')

    def _show_student(self):
        sel = self.s_tree.selection()
        if not sel:
            return
        s = self._students[sel[0]]
        self.student_label.configure(
            text=s.name + (f'  ·  Version {s.version}' if self.res.multi else ''))
        self.a_tree.delete(*self.a_tree.get_children())
        for a in rm.answers(self.res, s.version, s.row):
            if a.possible is None:
                pts = 'dropped' if a.earned is not None else ''
            elif a.earned is None:
                pts = 'not on form'
            else:
                pts = f'{_fmt(a.earned)} / {_fmt(a.possible)}'
            wrong = a.earned is not None and a.possible and a.earned < a.possible
            self.a_tree.insert('', 'end', values=(a.question, a.answer, a.key, pts),
                               tags=('flag',) if wrong else ())
        pages = rm.marked_pages(self.res, s.version, s.row)
        self._marked = pages
        self.marked_button.configure(state='normal' if pages else 'disabled')

    def _open_marked(self):
        for page in getattr(self, '_marked', []):
            open_file(page)
