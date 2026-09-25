"""
practical_tab.py

The Build Practical tab: a lab practical's source .md in, its printed
materials out (form sheets, a combined dealing-order sheet PDF, placards,
the setup guide, and the instructor key), by practical_build.build.

It logs to the app's shared status box, as Build Exam does. The field
checks are plain functions (check_fields) so they test without Tk.
"""
from __future__ import annotations

import traceback
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog

import practical
import practical_build


def check_fields(source: str, outdir: str, students: str) -> tuple[str, int]:
    """(error message or '', number of students). A blank class size is
    allowed and skips the combined sheet PDF."""
    if not source.strip():
        return 'Choose the practical\'s source file first.', 0
    if not Path(source).expanduser().is_file():
        return f'The source file {source} does not exist.', 0
    if not outdir.strip():
        return 'Choose an output folder.', 0
    text = students.strip()
    if not text:
        return '', 0
    try:
        n = int(text)
    except ValueError:
        return f'Class size must be a whole number, not "{text}".', 0
    if n < 0:
        return 'Class size cannot be negative.', 0
    return '', n


def summarize(p: practical.Practical) -> str:
    """One line describing a parsed practical, shown under the source field."""
    counts = {len(s.questions) for s in p.stations}
    per = f'{counts.pop()} questions each' if len(counts) == 1 else 'questions per station vary'
    return (f'{p.title}: {len(p.stations)} stations, {per}; '
            f'forms {", ".join(p.forms)}')


class BuildPracticalUI(ctk.CTkFrame):
    def __init__(self, parent, log_fn):
        super().__init__(parent, fg_color='transparent')
        self.log_fn = log_fn
        self._build_ui()

    def _build_ui(self):
        # The action sits in a footer, as on the other tabs
        footer = ctk.CTkFrame(self, fg_color='transparent')
        footer.pack(side='bottom', fill='x', pady=(6, 0))
        ctk.CTkButton(footer, text='Build Practical', height=40, width=220,
                      font=ctk.CTkFont(size=15, weight='bold'),
                      fg_color='#2563eb', hover_color='#1d4ed8',
                      command=self._on_build).pack(side='right', padx=10)

        content = ctk.CTkFrame(self, fg_color='transparent')
        content.pack(fill='both', expand=True)
        bold = ctk.CTkFont(weight='bold')
        small = ctk.CTkFont(size=11)

        ctk.CTkLabel(content, text='Practical source file', font=bold).pack(anchor='w')
        row = ctk.CTkFrame(content, fg_color='transparent')
        row.pack(fill='x', pady=(2, 0))
        self.source_entry = ctk.CTkEntry(row, width=420)
        self.source_entry.pack(side='left')
        ctk.CTkButton(row, text='Browse…', width=90, command=self._browse_source).pack(
            side='left', padx=(6, 0))
        self.summary_label = ctk.CTkLabel(content, text='', text_color='gray', font=small,
                                          anchor='w', justify='left', wraplength=560)
        self.summary_label.pack(anchor='w', pady=(2, 12))

        ctk.CTkLabel(content, text='Output folder', font=bold).pack(anchor='w')
        row = ctk.CTkFrame(content, fg_color='transparent')
        row.pack(fill='x', pady=(2, 12))
        self.output_entry = ctk.CTkEntry(row, width=420)
        self.output_entry.pack(side='left')
        ctk.CTkButton(row, text='Browse…', width=90, command=self._browse_output).pack(
            side='left', padx=(6, 0))

        ctk.CTkLabel(content, text='Class size', font=bold).pack(anchor='w')
        row = ctk.CTkFrame(content, fg_color='transparent')
        row.pack(fill='x', pady=(2, 0))
        self.students_entry = ctk.CTkEntry(row, width=80, justify='center')
        self.students_entry.pack(side='left')
        ctk.CTkLabel(row, text='students', font=small).pack(side='left', padx=(6, 0))
        ctk.CTkLabel(content, font=small, text_color='gray', anchor='w', justify='left',
                     wraplength=560,
                     text='Also writes one PDF with a sheet per student, forms dealt in the '
                          'order the source file lists them, so a stack handed down a row '
                          'gives neighbors different forms. Leave blank to skip it.').pack(
            anchor='w', pady=(2, 12))

        ctk.CTkLabel(content, font=small, text_color='gray', anchor='w', justify='left',
                     wraplength=560,
                     text='Writes a form sheet for each form, placards (one station per '
                          'page), the setup guide, and the instructor key. The source file '
                          'is also the key for Scan Exams.').pack(anchor='w')

    # -- pickers ----------------------------------------------------------------

    def _browse_source(self):
        start = Path(self.source_entry.get().strip()).expanduser().parent
        path = filedialog.askopenfilename(
            title='Select the practical source file',
            initialdir=str(start) if start.is_dir() else None,
            filetypes=[('Markdown files', '*.md'), ('All files', '*.*')])
        if not path:
            return
        self.source_entry.delete(0, 'end')
        self.source_entry.insert(0, path)
        self._show_summary(Path(path))

    def _show_summary(self, path: Path):
        try:
            p = practical.load(path)
        except practical.PracticalError as exc:
            self.summary_label.configure(text=f'Cannot use this file:\n{exc}',
                                         text_color='#b91c1c')
            return
        except OSError as exc:
            self.summary_label.configure(text=f'Cannot read this file: {exc}',
                                         text_color='#b91c1c')
            return
        text = summarize(p)
        if p.warnings:
            text += f'\n{len(p.warnings)} warning(s); they are listed in the log when you build.'
        self.summary_label.configure(text=text, text_color='gray')
        if not self.output_entry.get().strip():
            self.output_entry.insert(0, str(practical_build.default_outdir(p)))

    def _browse_output(self):
        start = Path(self.output_entry.get().strip()).expanduser()
        path = filedialog.askdirectory(
            title='Select output folder',
            initialdir=str(start) if start.is_dir() else None)
        if not path:
            return
        self.output_entry.delete(0, 'end')
        self.output_entry.insert(0, path)

    # -- build ------------------------------------------------------------------

    def _on_build(self):
        source, outdir = self.source_entry.get().strip(), self.output_entry.get().strip()
        error, students = check_fields(source, outdir, self.students_entry.get())
        if error:
            self.log_fn(error)
            return
        try:
            p = practical.load(Path(source).expanduser())
        except practical.PracticalError as exc:
            self.log_fn(f'Cannot build from {Path(source).name}:\n{exc}')
            return
        self.log_fn(f'Building {summarize(p)}…')
        for w in p.warnings:
            self.log_fn(f'  WARNING: {w}')
        try:
            written, warnings = practical_build.build(p, Path(outdir).expanduser(), students)
        except Exception as exc:              # shown in the log rather than lost
            self.log_fn(f'Build failed: {exc}')
            self.log_fn(traceback.format_exc())
            return
        for w in warnings:
            self.log_fn(f'  WARNING: {w}')
        for path in written:
            self.log_fn(f'  → {path.name}')
        self.log_fn(f'Wrote {len(written)} files to {Path(outdir).expanduser()}')
        if not students:
            self.log_fn('  No class size given, so no combined sheet PDF was written.')
