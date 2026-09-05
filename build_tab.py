"""
build_tab.py

customtkinter port of pyExamPaper's exam-builder window (its gui.py,
PySide6/Qt), as a fourth tab in pyExamKit's existing CTkTabview.
Reproduces its layout and behavior field-for-field. Deliberate departures
from the original: validation failures log to the shared status box
instead of a QMessageBox popup (this app has no messagebox usage
anywhere else), and pool rows get their own remove button instead of
multi-select-then-batch-remove (customtkinter has no selectable-table
widget).

The pure functions below (compute_pool_totals, validate_build_fields,
build_config_from_fields) hold every piece of business logic and take
plain values, not widgets, so they're unit-testable without a live Tk
root — see tests/test_build_tab_logic.py.
"""
from __future__ import annotations

import traceback
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog

from exam_builder import BuildConfig, ExamBuilder, PoolConfig
from exam_config import load_config, save_config
from exam_key_writer import save_key
from parser import parse_file
from renderer import ExamRenderer, safe_name

VERSION_POSITION_LABELS = {'at end of exam': 'last', 'at start of exam': 'first'}
VERSION_POSITION_VALUES = {v: k for k, v in VERSION_POSITION_LABELS.items()}


# ---------------------------------------------------------------------------
# Pure logic -- no widgets, so this half is unit-testable without a live Tk
# root. Mirrors ExamCreatorWindow/PoolTable in pyExamPaper's gui.py exactly.
# ---------------------------------------------------------------------------

def compute_pool_totals(rows: list[dict], default_points: float) -> tuple[int, float]:
    """rows: [{'count_text': str, 'points_text': str}, ...].

    Mirrors PoolTable.get_totals: bad '# to pull' text falls back to 10,
    bad or blank 'Pts/Q' text falls back to default_points. Purely
    arithmetic -- does not touch the 'in bank' count or the filesystem.
    """
    total_count = 0
    total_pts = 0.0
    for row in rows:
        try:
            count = int(row.get('count_text', '') or '0')
        except ValueError:
            count = 10
        pts_text = (row.get('points_text', '') or '').strip()
        if pts_text:
            try:
                pts = float(pts_text)
            except ValueError:
                pts = default_points
        else:
            pts = default_points
        total_count += count
        total_pts += count * pts
    return total_count, total_pts


def validate_build_fields(*, title: str, output_folder: str, mode: str,
                           exact_path: str, pool_rows: list[dict]) -> str | None:
    """mode: 'exact' or 'pools'. pool_rows: [{'filepath': str,
    'count_text': str, 'points_text': str}, ...], only consulted when
    mode == 'pools'.

    Returns the first validation failure, matching pyExamPaper's exact
    wording and checking order, or None if everything passes. Touches the
    filesystem only via Path.exists().
    """
    if not title.strip():
        return "Please enter an exam title."
    if not output_folder.strip():
        return "Please select an output folder."

    if mode == 'exact':
        if not exact_path.strip():
            return "Please select a question file."
        if not Path(exact_path).exists():
            return f"File not found:\n{exact_path}"
        return None

    # Pool mode: check every row's Pts/Q text first, stop at the first bad one.
    for idx, row in enumerate(pool_rows):
        pts_text = (row.get('points_text', '') or '').strip()
        if pts_text:
            try:
                float(pts_text)
            except ValueError:
                filepath = row.get('filepath', '')
                name = Path(filepath).name if filepath else f'row {idx + 1}'
                return (f'Invalid Pts/Q value "{pts_text}" for:\n{name}\n\n'
                        f'Enter a number or leave blank to use the global default.')

    if not pool_rows:
        return "Please add at least one pool file."

    for row in pool_rows:
        filepath = row.get('filepath', '')
        if not Path(filepath).exists():
            return f"Pool file not found:\n{filepath}"
        try:
            count = int(row.get('count_text', '') or '0')
        except ValueError:
            count = 10
        if count < 1:
            return f"Question count must be ≥ 1 for:\n{Path(filepath).name}"

    return None


def build_config_from_fields(*, title: str, course: str, num_versions: int,
                              shuffle_questions: bool, shuffle_answers: bool,
                              mode: str, exact_path: str, pool_rows: list[dict],
                              version_question: bool, version_question_position: str,
                              default_points: float, same_questions: bool) -> BuildConfig:
    """Mirrors ExamCreatorWindow._collect_config's field construction,
    including its blank-title-becomes-'Untitled' fallback (harmless when
    called from the generate path, where title is already validated
    non-blank; needed for the save-config path, which has no validation)."""
    kwargs = dict(
        title=title.strip() or 'Untitled',
        course=course.strip(),
        num_versions=num_versions,
        shuffle_questions=shuffle_questions,
        shuffle_answers=shuffle_answers,
        version_question=version_question,
        version_question_position=version_question_position,
        default_points=default_points,
        same_questions=same_questions,
    )
    if mode == 'exact':
        kwargs['exact_file'] = Path(exact_path) if exact_path.strip() else None
        kwargs['pools'] = []
    else:
        pools = []
        for row in pool_rows:
            try:
                count = int(row.get('count_text', '') or '0')
            except ValueError:
                count = 10
            pts_text = (row.get('points_text', '') or '').strip()
            if pts_text:
                try:
                    points = float(pts_text)
                except ValueError:
                    points = None
            else:
                points = None
            pools.append(PoolConfig(filepath=Path(row['filepath']), count=count, points=points))
        kwargs['pools'] = pools
        kwargs['exact_file'] = None
    return BuildConfig(**kwargs)


# ---------------------------------------------------------------------------
# Widget class
# ---------------------------------------------------------------------------

class BuildExamUI(ctk.CTkFrame):
    """One tab's worth of UI. `log_fn` is pyScanUI's existing shared
    status-log appender (self._log) -- this tab has no log pane of its
    own, matching the house convention of one shared log across tabs."""

    def __init__(self, parent, log_fn):
        super().__init__(parent, fg_color='transparent')
        self.log_fn = log_fn
        self._source_mode = ctk.StringVar(value='exact')
        self._pool_rows: list[dict] = []
        self.pack(fill='both', expand=True)
        self._build_ui()

    # -- layout ------------------------------------------------------------

    def _build_ui(self):
        content = ctk.CTkScrollableFrame(self, fg_color='transparent')
        content.pack(fill='both', expand=True, pady=(0, 8))

        self._build_header_section(content)
        self._build_source_section(content)
        self._build_options_section(content)
        self._build_output_section(content)
        self._build_config_buttons(content)
        ctk.CTkFrame(content, height=2, fg_color='gray60').pack(fill='x', pady=8)
        self._build_generate_button(content)

        self._on_source_mode_changed()
        self._update_same_questions_visibility()

    def _build_header_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color='transparent')
        frame.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(frame, text='Exam Header', font=ctk.CTkFont(weight='bold')).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))

        ctk.CTkLabel(frame, text='Title:').grid(row=1, column=0, padx=(0, 6), pady=2, sticky='w')
        self.title_entry = ctk.CTkEntry(frame, width=350)
        self.title_entry.insert(0, 'Exam 1')
        self.title_entry.grid(row=1, column=1, pady=2, sticky='w')

        ctk.CTkLabel(frame, text='Course:').grid(row=2, column=0, padx=(0, 6), pady=2, sticky='w')
        self.course_entry = ctk.CTkEntry(frame, width=350)
        self.course_entry.grid(row=2, column=1, pady=2, sticky='w')

    def _build_source_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color='transparent')
        frame.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(frame, text='Question Source', font=ctk.CTkFont(weight='bold')).grid(
            row=0, column=0, columnspan=3, sticky='w', pady=(0, 4))

        radio_row = ctk.CTkFrame(frame, fg_color='transparent')
        radio_row.grid(row=1, column=0, columnspan=3, sticky='w')
        ctk.CTkRadioButton(radio_row, text='Exact File', variable=self._source_mode,
                            value='exact', command=self._on_source_mode_changed).pack(
            side='left', padx=(0, 16))
        ctk.CTkRadioButton(radio_row, text='Question Pools', variable=self._source_mode,
                            value='pools', command=self._on_source_mode_changed).pack(side='left')

        self._exact_frame = ctk.CTkFrame(frame, fg_color='transparent')
        self._exact_frame.grid(row=2, column=0, columnspan=3, sticky='w', pady=(6, 0))
        ctk.CTkLabel(self._exact_frame, text='File:').grid(row=0, column=0, padx=(0, 6), sticky='w')
        self.exact_entry = ctk.CTkEntry(self._exact_frame, width=350)
        self.exact_entry.grid(row=0, column=1, sticky='w')
        ctk.CTkButton(self._exact_frame, text='Browse…', width=90,
                       command=self._browse_exact).grid(row=0, column=2, padx=(6, 0), sticky='w')

        self._pool_frame = ctk.CTkFrame(frame, fg_color='transparent')
        self._pool_frame.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(6, 0))
        self._build_pool_section(self._pool_frame)

    def _build_pool_section(self, parent):
        btn_row = ctk.CTkFrame(parent, fg_color='transparent')
        btn_row.pack(fill='x', anchor='w')
        ctk.CTkButton(btn_row, text='Add Pool File…', command=self._add_pool_files).pack(side='left')

        header = ctk.CTkFrame(parent, fg_color='transparent')
        header.pack(fill='x', pady=(6, 0))
        ctk.CTkLabel(header, text='File Path', font=ctk.CTkFont(weight='bold'),
                     width=260, anchor='w').grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(header, text='In Bank', font=ctk.CTkFont(weight='bold'),
                     width=70, anchor='center').grid(row=0, column=1)
        ctk.CTkLabel(header, text='# to pull', font=ctk.CTkFont(weight='bold'),
                     width=70, anchor='center').grid(row=0, column=2)
        ctk.CTkLabel(header, text='Pts/Q', font=ctk.CTkFont(weight='bold'),
                     width=65, anchor='center').grid(row=0, column=3)
        ctk.CTkLabel(header, text='', width=30).grid(row=0, column=4)

        ctk.CTkLabel(parent, text=('Pts/Q: leave blank to use the global default below. '
                                    'A pts: tag in the source file always takes priority.'),
                     font=ctk.CTkFont(size=11), text_color='gray',
                     anchor='w', justify='left', wraplength=520).pack(fill='x', pady=(0, 4))

        self._pool_rows_frame = ctk.CTkFrame(parent, fg_color='transparent')
        self._pool_rows_frame.pack(fill='x')

        self._pool_total_label = ctk.CTkLabel(parent, text='Total: 0 questions — 0.0 pts',
                                               font=ctk.CTkFont(size=11), text_color='gray')
        self._pool_total_label.pack(anchor='w', pady=(4, 0))

    def _build_options_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color='transparent')
        frame.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(frame, text='Options', font=ctk.CTkFont(weight='bold')).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))

        self.shuffle_q_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(frame, text='Shuffle question order', variable=self.shuffle_q_var).grid(
            row=1, column=0, columnspan=2, sticky='w', pady=2)

        self.shuffle_a_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(frame, text='Shuffle answer order', variable=self.shuffle_a_var).grid(
            row=2, column=0, columnspan=2, sticky='w', pady=2)

        ctk.CTkLabel(frame, text='Number of versions:').grid(
            row=3, column=0, padx=(0, 6), pady=2, sticky='w')
        self.num_versions_entry = ctk.CTkEntry(frame, width=60)
        self.num_versions_entry.insert(0, '1')
        self.num_versions_entry.grid(row=3, column=1, pady=2, sticky='w')
        self.num_versions_entry.bind('<KeyRelease>', lambda e: self._update_same_questions_visibility())

        ctk.CTkLabel(frame, text='Default pts/question:').grid(
            row=4, column=0, padx=(0, 6), pady=2, sticky='w')
        self.default_pts_entry = ctk.CTkEntry(frame, width=60)
        self.default_pts_entry.insert(0, '1.0')
        self.default_pts_entry.grid(row=4, column=1, pady=2, sticky='w')
        self.default_pts_entry.bind('<KeyRelease>', lambda e: self._update_pool_totals())

        self._same_q_frame = ctk.CTkFrame(frame, fg_color='transparent')
        self._same_q_frame.grid(row=5, column=0, columnspan=2, sticky='w', pady=2)
        self.same_questions_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self._same_q_frame,
            text='Use same questions across all versions (shuffle by default)',
            variable=self.same_questions_var, command=self._on_same_questions_toggled,
        ).pack(anchor='w')

        self.version_q_var = ctk.BooleanVar(value=False)
        vq_row = ctk.CTkFrame(frame, fg_color='transparent')
        vq_row.grid(row=6, column=0, columnspan=2, sticky='w', pady=2)
        ctk.CTkCheckBox(vq_row, text='Add version identifier question', variable=self.version_q_var,
                         command=self._on_version_q_toggled).pack(side='left')
        self.version_pos_menu = ctk.CTkOptionMenu(vq_row, values=list(VERSION_POSITION_LABELS.keys()),
                                                    width=140, state='disabled')
        self.version_pos_menu.pack(side='left', padx=(8, 0))

    def _build_output_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color='transparent')
        frame.pack(fill='x', pady=(0, 4))
        ctk.CTkLabel(frame, text='Output folder:').grid(row=0, column=0, padx=(0, 6), sticky='w')
        self.output_entry = ctk.CTkEntry(frame, width=350)
        self.output_entry.grid(row=0, column=1, sticky='w')
        ctk.CTkButton(frame, text='Browse…', width=90, command=self._browse_output).grid(
            row=0, column=2, padx=(6, 0), sticky='w')

    def _build_config_buttons(self, parent):
        frame = ctk.CTkFrame(parent, fg_color='transparent')
        frame.pack(fill='x', pady=(0, 4), anchor='w')
        ctk.CTkButton(frame, text='Load Config…', command=self._load_config_file).pack(
            side='left', padx=(0, 8))
        ctk.CTkButton(frame, text='Save Config…', command=self._save_config_file).pack(side='left')

    def _build_generate_button(self, parent):
        ctk.CTkButton(parent, text='Generate Exam', height=36, font=ctk.CTkFont(weight='bold'),
                       fg_color='#2563eb', hover_color='#1d4ed8',
                       command=self._on_generate).pack(fill='x', pady=(4, 8))

    # -- source-mode / conditional-row wiring -------------------------------

    def _on_source_mode_changed(self):
        if self._source_mode.get() == 'exact':
            self._exact_frame.grid()
            self._pool_frame.grid_remove()
        else:
            self._pool_frame.grid()
            self._exact_frame.grid_remove()
        self._update_same_questions_visibility()

    def _update_same_questions_visibility(self):
        try:
            num_versions = int(self.num_versions_entry.get() or '1')
        except ValueError:
            num_versions = 1
        if num_versions > 1 and self._source_mode.get() == 'pools':
            self._same_q_frame.grid()
        else:
            self._same_q_frame.grid_remove()
            self.same_questions_var.set(False)

    def _on_same_questions_toggled(self):
        if self.same_questions_var.get():
            self.shuffle_q_var.set(True)
            self.shuffle_a_var.set(True)

    def _on_version_q_toggled(self):
        self.version_pos_menu.configure(state='normal' if self.version_q_var.get() else 'disabled')

    # -- pool rows -----------------------------------------------------------

    @staticmethod
    def _elide_left(path: str, max_chars: int = 42) -> str:
        if len(path) <= max_chars:
            return path
        return '…' + path[-(max_chars - 1):]

    def _add_pool_row(self, filepath: str, count=10, points_str='') -> dict:
        row_frame = ctk.CTkFrame(self._pool_rows_frame, fg_color='transparent')
        row_frame.pack(fill='x', pady=1)

        path_label = ctk.CTkLabel(row_frame, text=self._elide_left(filepath), width=260, anchor='w')
        path_label.grid(row=0, column=0, sticky='w')
        in_bank_label = ctk.CTkLabel(row_frame, text='…', width=70, anchor='center')
        in_bank_label.grid(row=0, column=1)
        count_entry = ctk.CTkEntry(row_frame, width=70, justify='center')
        count_entry.insert(0, str(count))
        count_entry.grid(row=0, column=2, padx=2)
        points_entry = ctk.CTkEntry(row_frame, width=65, justify='center')
        points_entry.insert(0, points_str)
        points_entry.grid(row=0, column=3, padx=2)
        remove_btn = ctk.CTkButton(row_frame, text='✕', width=30,
                                    fg_color='gray40', hover_color='gray30')
        remove_btn.grid(row=0, column=4, padx=(4, 0))

        row = {'frame': row_frame, 'filepath': filepath, 'in_bank_label': in_bank_label,
               'count_entry': count_entry, 'points_entry': points_entry}
        remove_btn.configure(command=lambda: self._remove_pool_row(row))
        count_entry.bind('<KeyRelease>', lambda e: self._update_pool_totals())
        points_entry.bind('<KeyRelease>', lambda e: self._update_pool_totals())

        self._pool_rows.append(row)
        self._update_pool_totals()
        return row

    def _remove_pool_row(self, row: dict):
        row['frame'].destroy()
        self._pool_rows.remove(row)
        self._update_pool_totals()

    def _add_pool_files(self):
        paths = filedialog.askopenfilenames(
            title='Select pool file(s)',
            filetypes=[('Text/Markdown files', '*.txt *.md'), ('All files', '*.*')])
        if not paths:
            return
        if not self.output_entry.get().strip():
            self.output_entry.insert(0, str(Path(paths[0]).parent))
        for path in paths:
            row = self._add_pool_row(path, count=10, points_str='')
            try:
                qs, warnings = parse_file(Path(path))
                n = len(qs)
                row['in_bank_label'].configure(text=str(n))
                if n < 10:
                    row['count_entry'].delete(0, 'end')
                    row['count_entry'].insert(0, str(n))
            except Exception:
                row['in_bank_label'].configure(text='0')
        self._update_pool_totals()

    def _collect_pool_row_data(self) -> list[dict]:
        return [{'filepath': r['filepath'], 'count_text': r['count_entry'].get(),
                  'points_text': r['points_entry'].get()} for r in self._pool_rows]

    def _parse_default_points(self) -> float:
        try:
            return float(self.default_pts_entry.get())
        except ValueError:
            return 1.0

    def _update_pool_totals(self):
        rows = [{'count_text': r['count_entry'].get(), 'points_text': r['points_entry'].get()}
                for r in self._pool_rows]
        count, pts = compute_pool_totals(rows, self._parse_default_points())
        self._pool_total_label.configure(text=f'Total: {count} questions — {pts:.1f} pts')

    # -- file pickers ---------------------------------------------------------

    def _browse_exact(self):
        path = filedialog.askopenfilename(
            title='Select question file',
            filetypes=[('Text/Markdown files', '*.txt *.md'), ('All files', '*.*')])
        if not path:
            return
        self.exact_entry.delete(0, 'end')
        self.exact_entry.insert(0, path)
        if not self.output_entry.get().strip():
            self.output_entry.insert(0, str(Path(path).parent))

    def _browse_output(self):
        path = filedialog.askdirectory(title='Select output folder')
        if not path:
            return
        self.output_entry.delete(0, 'end')
        self.output_entry.insert(0, path)

    # -- generate ---------------------------------------------------------------

    @staticmethod
    def _safe_int(text: str, default: int) -> int:
        try:
            return int(text or default)
        except ValueError:
            return default

    def _on_generate(self):
        title = self.title_entry.get()
        output_folder = self.output_entry.get().strip()
        mode = self._source_mode.get()
        exact_path = self.exact_entry.get()
        pool_rows = self._collect_pool_row_data()

        error = validate_build_fields(title=title, output_folder=output_folder, mode=mode,
                                       exact_path=exact_path, pool_rows=pool_rows)
        if error:
            self.log_fn(error)
            return

        num_versions = max(1, min(26, self._safe_int(self.num_versions_entry.get(), 1)))
        default_points = self._parse_default_points()
        version_position = VERSION_POSITION_LABELS.get(self.version_pos_menu.get(), 'last')

        config = build_config_from_fields(
            title=title, course=self.course_entry.get(), num_versions=num_versions,
            shuffle_questions=self.shuffle_q_var.get(), shuffle_answers=self.shuffle_a_var.get(),
            mode=mode, exact_path=exact_path, pool_rows=pool_rows,
            version_question=self.version_q_var.get(), version_question_position=version_position,
            default_points=default_points, same_questions=self.same_questions_var.get(),
        )
        output_path = Path(output_folder)

        self.log_fn('Parsing question sources…')
        try:
            builder = ExamBuilder()
            renderer = ExamRenderer()
            versions, warnings = builder.build(config)
            for w in warnings:
                self.log_fn(f'  WARNING: {w}')
            self.log_fn(f'Building {len(versions)} version(s)…')
            total_versions = len(versions)
            for version in versions:
                v_letter = version.version_letter
                self.log_fn(f'\n  Version {v_letter} ({len(version.questions)} questions)')
                html_path = renderer.to_html(version, output_path, total_versions, config.default_points)
                self.log_fn(f'    HTML  → {html_path.name}')
                md_path = renderer.to_markdown(version, output_path)
                self.log_fn(f'    MD    → {md_path.name}')
                key_name = f'{safe_name(version.title)}_v{v_letter}_key.csv'
                key_path = output_path / key_name
                save_key(version, key_path, config.default_points)
                self.log_fn(f'    Key   → {key_path.name}')

            try:
                config_name = f'{safe_name(config.title)}.exam.json'
                save_config(config, output_path, output_path / config_name)
                self.log_fn(f'    Config → {config_name}')
            except Exception:
                pass  # Non-fatal, matches the original.

            self.log_fn('\nDone.')
            self.log_fn(f'\nOutput saved to: {self.output_entry.get().strip()}')
        except Exception:
            self.log_fn(f'\nERROR:\n{traceback.format_exc()}')

    # -- config load/save ---------------------------------------------------

    def _load_config_file(self):
        path = filedialog.askopenfilename(
            title='Load Exam Config',
            filetypes=[('Exam config files', '*.exam.json'), ('JSON files', '*.json'),
                       ('All files', '*.*')])
        if not path:
            return
        try:
            config, output_folder = load_config(Path(path))
            self._populate_from_config(config, output_folder)
        except Exception as exc:
            self.log_fn(f'Could not load config:\n{exc}')

    def _save_config_file(self):
        title = self.title_entry.get().strip() or 'exam'
        suggested = f'{safe_name(title)}.exam.json'
        path = filedialog.asksaveasfilename(
            title='Save Exam Config', initialfile=suggested,
            filetypes=[('Exam config files', '*.exam.json'), ('JSON files', '*.json'),
                       ('All files', '*.*')])
        if not path:
            return
        dest = Path(path)
        if dest.suffix != '.json':
            dest = dest.with_suffix('.exam.json')
        try:
            config = build_config_from_fields(
                title=self.title_entry.get(), course=self.course_entry.get(),
                num_versions=self._safe_int(self.num_versions_entry.get(), 1),
                shuffle_questions=self.shuffle_q_var.get(), shuffle_answers=self.shuffle_a_var.get(),
                mode=self._source_mode.get(), exact_path=self.exact_entry.get(),
                pool_rows=self._collect_pool_row_data(),
                version_question=self.version_q_var.get(),
                version_question_position=VERSION_POSITION_LABELS.get(
                    self.version_pos_menu.get(), 'last'),
                default_points=self._parse_default_points(),
                same_questions=self.same_questions_var.get(),
            )
            output_folder = Path(self.output_entry.get().strip() or '.')
            save_config(config, output_folder, dest)
        except Exception as exc:
            self.log_fn(f'Could not save config:\n{exc}')

    def _populate_from_config(self, config: BuildConfig, output_folder: Path):
        self.title_entry.delete(0, 'end')
        self.title_entry.insert(0, config.title)
        self.course_entry.delete(0, 'end')
        self.course_entry.insert(0, config.course)
        self.num_versions_entry.delete(0, 'end')
        self.num_versions_entry.insert(0, str(config.num_versions))
        self.shuffle_q_var.set(config.shuffle_questions)
        self.shuffle_a_var.set(config.shuffle_answers)
        self.version_q_var.set(config.version_question)
        self._on_version_q_toggled()
        self.version_pos_menu.set(
            VERSION_POSITION_VALUES.get(config.version_question_position, 'at end of exam'))
        self.default_pts_entry.delete(0, 'end')
        self.default_pts_entry.insert(0, str(config.default_points))

        out_str = str(output_folder) if str(output_folder) not in ('', '.') else ''
        self.output_entry.delete(0, 'end')
        self.output_entry.insert(0, out_str)

        for row in list(self._pool_rows):
            self._remove_pool_row(row)
        self.exact_entry.delete(0, 'end')

        if config.exact_file:
            self._source_mode.set('exact')
            self.exact_entry.insert(0, str(config.exact_file))
        else:
            self._source_mode.set('pools')
            for pool in config.pools:
                pts_str = str(pool.points) if pool.points is not None else ''
                row = self._add_pool_row(str(pool.filepath), count=pool.count, points_str=pts_str)
                try:
                    qs, warnings = parse_file(pool.filepath)
                    row['in_bank_label'].configure(text=str(len(qs)))
                except Exception:
                    row['in_bank_label'].configure(text='0')
        self._on_source_mode_changed()

        # Set same_questions last -- its visibility depends on versions and
        # source mode already being set (see _update_same_questions_visibility).
        self.same_questions_var.set(config.same_questions)
