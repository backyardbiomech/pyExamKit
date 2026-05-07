import sys
import io
import json
from pathlib import Path
from scanner import Scanner
import customtkinter as ctk
from tkinter import filedialog
import ai_ocr


class TextRedirector(io.TextIOBase):
    """Redirects stdout writes to a CTkTextbox widget."""

    def __init__(self, widget):
        self._widget = widget

    def write(self, string):
        self._widget.configure(state='normal')
        self._widget.insert('end', string)
        self._widget.configure(state='disabled')
        self._widget.see('end')
        self._widget.update()
        return len(string)

    def flush(self):
        pass


class pyScanUI(ctk.CTkFrame):
    """
    Main GUI frame for pyExamScan.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.__initUI()

    def __initUI(self):
        self.parent.title("Python ExamScan")
        self.parent.resizable(True, True)
        self.parent.geometry('840x860')
        self.parent.minsize(700, 580)
        self.pack(fill='both', expand=True, padx=16, pady=16)

        # ── Tab view ──────────────────────────────────────────────────────
        tabs = ctk.CTkTabview(self)
        tabs.pack(fill='both', expand=True)

        scan_tab   = tabs.add("Scan Exams")
        key_tab    = tabs.add("Build Key")
        regrade_tab = tabs.add("Re-grade")

        # ════════════════════════════════════════════════════════
        # TAB 1 — Scan Exams
        # ════════════════════════════════════════════════════════
        scan_frame = ctk.CTkScrollableFrame(scan_tab, fg_color='transparent')
        scan_frame.pack(fill='both', expand=True, pady=(0, 8))

        # ── Key File row — load first so its metadata auto-fills fields below ──
        key_file_row = ctk.CTkFrame(scan_frame, fg_color='transparent')
        key_file_row.grid(row=0, column=0, columnspan=2, padx=10, pady=4, sticky='w')
        ctk.CTkButton(key_file_row, text="Load Key File…",
                      command=self._browse_key_file, width=180).pack(side='left', padx=(0, 6))
        self.scanKeyFileEntry = ctk.CTkEntry(
            key_file_row, width=400,
            placeholder_text="Load the key CSV built in the 'Build Key' tab (auto-fills question count & skips)")
        self.scanKeyFileEntry.pack(side='left', padx=(0, 6))
        ctk.CTkButton(key_file_row, text="Create / Edit…",
                      command=self._open_key_file_editor, width=110).pack(side='left')

        ctk.CTkButton(scan_frame, text="Choose PDF of scans or JPG of key",
                      command=self.button_browse_callback).grid(
            row=1, column=0, padx=10, pady=4, sticky='w')
        self.fileEntry = ctk.CTkEntry(scan_frame, width=400)
        self.fileEntry.grid(row=1, column=1, padx=10, pady=4, sticky='ew')

        ctk.CTkLabel(scan_frame, text="Number of questions to grade:").grid(
            row=2, column=0, padx=10, pady=4, sticky='w')
        self.numQEntry = ctk.CTkEntry(scan_frame, width=80)
        self.numQEntry.grid(row=2, column=1, padx=10, pady=4, sticky='w')

        ctk.CTkLabel(scan_frame, text="Question numbers to ignore (comma-separated):").grid(
            row=3, column=0, padx=10, pady=4, sticky='w')
        self.ignoreEntry = ctk.CTkEntry(scan_frame, width=300)
        self.ignoreEntry.grid(row=3, column=1, padx=10, pady=4, sticky='w')

        self.setavar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(scan_frame, text="Select-all-that-apply questions?",
                        variable=self.setavar).grid(
            row=4, column=0, columnspan=2, padx=10, pady=4, sticky='w')

        self.openQvar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(scan_frame, text="Open-ended questions to grade on-screen? (with OCR assist)",
                        variable=self.openQvar,
                        command=self._toggle_ai_frame).grid(
            row=5, column=0, columnspan=2, padx=10, pady=4, sticky='w')

        # ── AI OCR sub-frame (shown only when open-ended is checked) ──────
        self._ai_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        self._ai_frame.grid(row=6, column=0, columnspan=2, padx=(30, 10), pady=(0, 2), sticky='w')
        self._ai_frame.grid_remove()

        self.aiOcrVar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(self._ai_frame, text="Use AI OCR (Claude) for handwriting recognition",
                        variable=self.aiOcrVar,
                        command=self._toggle_ai_context_row).grid(
            row=0, column=0, columnspan=3, padx=0, pady=(2, 2), sticky='w')

        # Context selection row (shown only when AI OCR is checked)
        self._ai_context_row = ctk.CTkFrame(self._ai_frame, fg_color='transparent')
        self._ai_context_row.grid(row=1, column=0, columnspan=3, padx=(20, 0), pady=(0, 2), sticky='w')
        self._ai_context_row.grid_remove()

        ctk.CTkLabel(self._ai_context_row, text="Exam context:").grid(
            row=0, column=0, padx=(0, 6), pady=2, sticky='w')
        self.aiContextVar = ctk.StringVar(value=ai_ocr.PRESET_LABELS[0])
        ctk.CTkOptionMenu(self._ai_context_row,
                          values=ai_ocr.PRESET_LABELS,
                          variable=self.aiContextVar,
                          command=self._on_ai_context_change,
                          width=260).grid(row=0, column=1, padx=(0, 8), pady=2, sticky='w')
        ctk.CTkButton(self._ai_context_row, text="Configure API Key…",
                      command=self._open_ai_settings,
                      width=160).grid(row=0, column=2, padx=(0, 4), pady=2, sticky='w')

        self.aiCustomContextEntry = ctk.CTkEntry(
            self._ai_context_row, width=440,
            placeholder_text="Describe the subject / exam type for the AI model…")
        self.aiCustomContextEntry.grid(row=1, column=1, columnspan=2, padx=(0, 4), pady=(0, 2), sticky='w')
        self.aiCustomContextEntry.grid_remove()

        ctk.CTkLabel(
            self._ai_context_row,
            text="⚠  This sends cropped answer images and an anonymized index to a cloud server.\n"
                 "    No identifiable student information is sent unless it appears in the answer area.",
            justify='left',
            text_color='#b45309',
            font=ctk.CTkFont(size=11),
        ).grid(row=2, column=0, columnspan=3, padx=(0, 4), pady=(4, 2), sticky='w')

        self.reviewPerfectVar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(self._ai_frame,
                        text="Review perfect matches? (confirm even high-confidence correct answers)",
                        variable=self.reviewPerfectVar).grid(
            row=3, column=0, columnspan=3, padx=0, pady=(4, 2), sticky='w')

        self.saveMarkedVar = ctk.IntVar(value=1)
        ctk.CTkCheckBox(scan_frame, text="Save marked answer sheets? (marked/ folder + marked.pdf)",
                        variable=self.saveMarkedVar).grid(
            row=7, column=0, columnspan=2, padx=10, pady=4, sticky='w')

        self.corrvar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(scan_frame, text="Mark correct answers on graded sheets?",
                        variable=self.corrvar).grid(
            row=8, column=0, columnspan=2, padx=10, pady=(0, 4), sticky='w')

        ctk.CTkLabel(scan_frame, text="Pages per student (multi-page exams):").grid(
            row=9, column=0, padx=10, pady=4, sticky='w')
        self.pagesPerStudentEntry = ctk.CTkEntry(scan_frame, width=60)
        self.pagesPerStudentEntry.insert(0, '1')
        self.pagesPerStudentEntry.grid(row=9, column=1, padx=10, pady=4, sticky='w')

        ctk.CTkLabel(scan_frame, text="Points per bubble question:").grid(
            row=10, column=0, padx=10, pady=4, sticky='w')
        self.bubbleValEntry = ctk.CTkEntry(scan_frame, width=80)
        self.bubbleValEntry.insert(0, '1')
        self.bubbleValEntry.grid(row=10, column=1, padx=10, pady=4, sticky='w')

        ctk.CTkLabel(scan_frame, text="Points per open-ended question:").grid(
            row=11, column=0, padx=10, pady=4, sticky='w')
        self.openValEntry = ctk.CTkEntry(scan_frame, width=80)
        self.openValEntry.insert(0, '2')
        self.openValEntry.grid(row=11, column=1, padx=10, pady=4, sticky='w')

        ctk.CTkLabel(
            scan_frame,
            text="Fill threshold (0.20 = lighter marks, 0.30 = ignore light erases):",
        ).grid(row=12, column=0, padx=10, pady=4, sticky='w')
        thresh_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        thresh_frame.grid(row=12, column=1, padx=10, pady=4, sticky='w')
        self.threshVar = ctk.DoubleVar(value=0.25)
        self.threshSlider = ctk.CTkSlider(thresh_frame, from_=0.10, to=0.40,
                                          variable=self.threshVar,
                                          command=self._update_thresh_label,
                                          width=200)
        self.threshSlider.pack(side='left')
        self.threshLabel = ctk.CTkLabel(thresh_frame, text='0.25', width=40)
        self.threshLabel.pack(side='left', padx=6)

        ctk.CTkLabel(
            scan_frame,
            text="Partial credit strictness (0=generous, 1=strict; open-ended questions only):",
        ).grid(row=13, column=0, padx=10, pady=4, sticky='w')
        strictness_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        strictness_frame.grid(row=13, column=1, padx=10, pady=4, sticky='w')
        self.strictnessVar = ctk.DoubleVar(value=0.5)
        self.strictnessSlider = ctk.CTkSlider(strictness_frame, from_=0.0, to=1.0,
                                              variable=self.strictnessVar,
                                              command=self._update_strictness_label,
                                              width=200)
        self.strictnessSlider.pack(side='left')
        self.strictnessLabel = ctk.CTkLabel(strictness_frame, text='0.50', width=40)
        self.strictnessLabel.pack(side='left', padx=6)

        ctk.CTkButton(scan_frame, text="Run Scan",
                      command=self.button_go_callback,
                      fg_color='#2563eb', hover_color='#1d4ed8').grid(
            row=14, column=0, columnspan=2, pady=10)

        # ── Re-use aligned images ───────────────────────────────────────────────
        self.reuseAlignedVar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(
            scan_frame,
            text="Skip alignment — re-use existing aligned images (fast threshold re-scan)",
            variable=self.reuseAlignedVar,
        ).grid(row=15, column=0, columnspan=2, padx=10, pady=(0, 4), sticky='w')

        # ── Multiple exam versions ──────────────────────────────────────────────
        self.multiVersionVar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(scan_frame,
                        text="Multiple exam versions? (A/B/C/D/E/F versions graded separately)",
                        variable=self.multiVersionVar,
                        command=self._toggle_version_frame).grid(
            row=16, column=0, columnspan=2, padx=10, pady=(8, 2), sticky='w')

        self._version_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        self._version_frame.grid(row=17, column=0, columnspan=2,
                                 padx=(30, 10), pady=(0, 8), sticky='w')
        self._version_frame.grid_remove()

        ctk.CTkLabel(self._version_frame,
                     text="Version question number:").grid(
            row=0, column=0, padx=(0, 6), pady=2, sticky='w')
        self.versionQEntry = ctk.CTkEntry(self._version_frame, width=80,
                                          placeholder_text="e.g. 64")
        self.versionQEntry.grid(row=0, column=1, padx=(0, 6), pady=2, sticky='w')
        ctk.CTkLabel(self._version_frame,
                     text="(students fill A/B/C/D/E/F on this question to identify their version)",
                     font=ctk.CTkFont(size=11), text_color='gray').grid(
            row=0, column=2, padx=(0, 4), pady=2, sticky='w')

        self._version_key_entries: dict[str, ctk.CTkEntry] = {}
        self._version_key_paths: dict[str, str] = {}
        for _vi, _ver in enumerate(['A', 'B', 'C', 'D', 'E', 'F']):
            ctk.CTkLabel(self._version_frame,
                         text=f"Version {_ver} key file:").grid(
                row=_vi + 1, column=0, padx=(0, 6), pady=2, sticky='w')
            _entry = ctk.CTkEntry(self._version_frame, width=350,
                                  placeholder_text=f"Key CSV for version {_ver} (leave blank to skip)")
            _entry.grid(row=_vi + 1, column=1, padx=(0, 6), pady=2, sticky='w')
            ctk.CTkButton(self._version_frame, text="Browse…",
                          command=lambda e=_entry, v=_ver: self._browse_version_key(v, e),
                          width=80).grid(row=_vi + 1, column=2, padx=(0, 2), pady=2, sticky='w')
            self._version_key_entries[_ver] = _entry

        # ════════════════════════════════════════════════════════
        # TAB 2 — Build Key
        # ════════════════════════════════════════════════════════
        key_frame = ctk.CTkFrame(key_tab, fg_color='transparent')
        key_frame.pack(fill='x', pady=(0, 8))

        ctk.CTkLabel(key_frame,
                     text="Build an answer key from a scanned answer sheet:",
                     font=ctk.CTkFont(weight='bold')).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(8, 4), sticky='w')

        # ── Mode selection ─────────────────────────────────────────────
        self._buildKeyModeVar = ctk.IntVar(value=0)
        ctk.CTkRadioButton(
            key_frame,
            text="Blank sheet — mark open-ended answer-box locations only",
            variable=self._buildKeyModeVar, value=0,
            command=self._toggle_key_filled_frame).grid(
            row=1, column=0, columnspan=2, padx=10, pady=(2, 1), sticky='w')
        ctk.CTkRadioButton(
            key_frame,
            text="Instructor-filled sheet — auto-scan MC bubbles + OCR handwriting",
            variable=self._buildKeyModeVar, value=1,
            command=self._toggle_key_filled_frame).grid(
            row=2, column=0, columnspan=2, padx=10, pady=(1, 4), sticky='w')

        # ── Filled-sheet options (hidden until filled mode is selected) ──
        self._key_filled_frame = ctk.CTkFrame(key_frame, fg_color='transparent')
        self._key_filled_frame.grid(row=3, column=0, columnspan=2,
                                     padx=(30, 10), pady=(0, 4), sticky='w')
        self._key_filled_frame.grid_remove()

        ctk.CTkLabel(self._key_filled_frame,
                     text="Number of bubble MC questions:").grid(
            row=0, column=0, padx=0, pady=2, sticky='w')
        self._keyBuildNumMCEntry = ctk.CTkEntry(self._key_filled_frame, width=80)
        self._keyBuildNumMCEntry.grid(row=0, column=1, padx=10, pady=2, sticky='w')

        ctk.CTkLabel(self._key_filled_frame,
                     text="Questions to skip (comma-separated):").grid(
            row=1, column=0, padx=0, pady=2, sticky='w')
        self._keyBuildIgnoreEntry = ctk.CTkEntry(self._key_filled_frame, width=300)
        self._keyBuildIgnoreEntry.grid(row=1, column=1, padx=10, pady=2, sticky='w')

        self._keyBuildAiVar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(
            self._key_filled_frame,
            text="Use AI OCR (Claude) for handwriting recognition",
            variable=self._keyBuildAiVar,
            command=self._toggle_key_build_ai_row).grid(
            row=2, column=0, columnspan=2, padx=0, pady=(4, 2), sticky='w')

        self._key_build_ai_row = ctk.CTkFrame(self._key_filled_frame,
                                               fg_color='transparent')
        self._key_build_ai_row.grid(row=3, column=0, columnspan=2,
                                     padx=(20, 0), pady=(0, 2), sticky='w')
        self._key_build_ai_row.grid_remove()

        ctk.CTkLabel(self._key_build_ai_row, text="Exam context:").grid(
            row=0, column=0, padx=(0, 6), pady=2, sticky='w')
        self._keyBuildAiContextVar = ctk.StringVar(
            value=ai_ocr.PRESET_LABELS[0])
        ctk.CTkOptionMenu(
            self._key_build_ai_row,
            values=ai_ocr.PRESET_LABELS,
            variable=self._keyBuildAiContextVar,
            command=self._on_key_build_context_change,
            width=260).grid(row=0, column=1, padx=(0, 8), pady=2, sticky='w')
        ctk.CTkButton(
            self._key_build_ai_row, text="Configure API Key…",
            command=self._open_ai_settings,
            width=160).grid(row=0, column=2, padx=(0, 4), pady=2, sticky='w')

        self._keyBuildCustomContextEntry = ctk.CTkEntry(
            self._key_build_ai_row, width=440,
            placeholder_text="Describe the subject / exam type for the AI model…")
        self._keyBuildCustomContextEntry.grid(
            row=1, column=1, columnspan=2, padx=(0, 4), pady=(0, 2), sticky='w')
        self._keyBuildCustomContextEntry.grid_remove()

        ctk.CTkButton(key_frame, text="Build Key from Exam Scan…",
                      command=self._open_key_builder).grid(
            row=4, column=0, columnspan=2, pady=10)

        # ════════════════════════════════════════════════════════
        # TAB 3 — Re-grade
        # ════════════════════════════════════════════════════════
        regrade_frame = ctk.CTkFrame(regrade_tab, fg_color='transparent')
        regrade_frame.pack(fill='x', pady=(0, 8))

        ctk.CTkLabel(regrade_frame,
                     text="Update acceptable answers for fill-in-the-blank questions\n"
                          "and retroactively adjust grades in an existing results.csv.",
                     justify='left').grid(
            row=0, column=0, columnspan=2, padx=10, pady=(8, 4), sticky='w')
        ctk.CTkButton(regrade_frame, text="Choose results.csv",
                      command=self._browse_regrade_csv).grid(
            row=1, column=0, padx=10, pady=4, sticky='w')
        self.regradeEntry = ctk.CTkEntry(regrade_frame, width=400)
        self.regradeEntry.grid(row=1, column=1, padx=10, pady=4, sticky='ew')
        ctk.CTkButton(regrade_frame, text="Open Re-grader",
                      command=self._open_regrade_dialog,
                      fg_color='#2563eb', hover_color='#1d4ed8').grid(
            row=2, column=0, columnspan=2, pady=10)

        # ── Status log (shared, below tabs) ───────────────────────────────
        ctk.CTkFrame(self, height=2, fg_color='gray60').pack(fill='x', pady=8)
        ctk.CTkLabel(self, text="Status Log",
                     font=ctk.CTkFont(size=13, weight='bold')).pack(anchor='w', padx=4)
        self.log_box = ctk.CTkTextbox(self, height=120, state='disabled',
                                      font=ctk.CTkFont(family='Courier', size=11))
        self.log_box.pack(fill='x', padx=4, pady=(2, 8))

        # ── Exit ──────────────────────────────────────────────────────────
        ctk.CTkButton(self, text='Exit', command=sys.exit,
                      fg_color='gray40', hover_color='gray30').pack(pady=(0, 4))

    # ── Callbacks ─────────────────────────────────────────────────────────

    def _toggle_ai_frame(self):
        """Show or hide the AI OCR sub-frame based on the open-ended checkbox."""
        if self.openQvar.get():
            self._ai_frame.grid()
        else:
            self.aiOcrVar.set(0)
            self._ai_frame.grid_remove()
            self._ai_context_row.grid_remove()

    def _toggle_version_frame(self):
        """Show or hide the multiple-versions sub-frame."""
        if self.multiVersionVar.get():
            self._version_frame.grid()
        else:
            self._version_frame.grid_remove()

    def _browse_version_key(self, ver: str, entry: 'ctk.CTkEntry'):
        """Browse for a key file for the given version letter."""
        path = filedialog.askopenfilename(
            title=f'Select key file for version {ver}',
            filetypes=[('CSV key files', '*.csv'), ('JSON key files', '*.json')])
        if path:
            self._version_key_paths[ver] = path
            entry.delete(0, 'end')
            entry.insert(0, Path(path).name)

    def _browse_regrade_csv(self):
        filename = filedialog.askopenfilename(
            filetypes=[('CSV files', '*.csv')])
        if filename:
            self.regradeEntry.delete(0, 'end')
            self.regradeEntry.insert(0, filename)

    def _open_regrade_dialog(self):
        csv_path = self.regradeEntry.get().strip()
        if not csv_path:
            self._log('Please select a results.csv first.')
            return
        from openQ import RegradeDialog
        RegradeDialog(self.parent, csv_path,
                      strictness=self.strictnessVar.get(),
                      on_complete=lambda n: self._log(
                          f'Re-grading complete: {n} grade(s) upgraded.'))

    def _toggle_ai_context_row(self):
        """Show or hide the context / API key row based on the AI OCR checkbox."""
        if self.aiOcrVar.get():
            self._ai_context_row.grid()
        else:
            self._ai_context_row.grid_remove()

    def _on_ai_context_change(self, selected: str):
        """Show the custom context entry when 'Custom…' is chosen."""
        if ai_ocr.PRESET_VALUES.get(selected) is None:
            self.aiCustomContextEntry.grid()
        else:
            self.aiCustomContextEntry.grid_remove()

    def _open_ai_settings(self):
        """Open a dialog for the user to enter and save their Anthropic API key."""
        dlg = ctk.CTkToplevel(self)
        dlg.title('AI OCR — API Key Settings')
        dlg.resizable(False, False)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text='Anthropic API Key',
                     font=ctk.CTkFont(size=14, weight='bold')).grid(
            row=0, column=0, columnspan=3, padx=16, pady=(14, 4), sticky='w')
        ctk.CTkLabel(dlg,
                     text='Your key is stored in ~/.pyexamscan_config.json (mode 600).\n'
                          'Get a key at console.anthropic.com.',
                     justify='left').grid(
            row=1, column=0, columnspan=3, padx=16, pady=(0, 8), sticky='w')

        saved_key = ai_ocr.load_config().get('anthropic_api_key', '')
        key_var = ctk.StringVar(value=saved_key)
        key_entry = ctk.CTkEntry(dlg, textvariable=key_var, width=380, show='*')
        key_entry.grid(row=2, column=0, columnspan=2, padx=16, pady=4, sticky='w')

        show_var = ctk.BooleanVar(value=False)
        def _toggle_show():
            key_entry.configure(show='' if show_var.get() else '*')
        ctk.CTkCheckBox(dlg, text='Show', variable=show_var,
                        command=_toggle_show).grid(
            row=2, column=2, padx=(6, 16), pady=4, sticky='w')

        btn_frame = ctk.CTkFrame(dlg, fg_color='transparent')
        btn_frame.grid(row=3, column=0, columnspan=3, pady=(8, 14), padx=16, sticky='e')

        def _save():
            raw = key_var.get().strip()
            ai_ocr.save_config({'anthropic_api_key': raw})
            dlg.destroy()

        ctk.CTkButton(btn_frame, text='Save', command=_save,
                      fg_color='#2563eb', hover_color='#1d4ed8').pack(side='left', padx=(0, 8))
        ctk.CTkButton(btn_frame, text='Cancel', command=dlg.destroy,
                      fg_color='gray40', hover_color='gray30').pack(side='left')

    def _get_ai_params(self) -> tuple[bool, str, str]:
        """Return (use_ai, api_key, context_string) from current UI state."""
        use_ai = bool(self.openQvar.get() and self.aiOcrVar.get())
        if not use_ai:
            return False, '', ''
        api_key = ai_ocr.load_config().get('anthropic_api_key', '')
        selected = self.aiContextVar.get()
        preset_val = ai_ocr.PRESET_VALUES.get(selected)
        if preset_val is None:   # "Custom…"
            context = self.aiCustomContextEntry.get().strip()
        else:
            context = preset_val
        return True, api_key, context

    def _browse_key_file(self):
        filename = filedialog.askopenfilename(
            title='Choose exam key file',
            filetypes=[('CSV key file', '*.csv'),
                       ('JSON files', '*.json')])
        if filename:
            self.scanKeyFileEntry.delete(0, 'end')
            self.scanKeyFileEntry.insert(0, filename)
            self._load_key_metadata(filename)

    def _load_key_metadata(self, path: str):
        """Read metadata from a key file and populate num questions / skip fields."""
        try:
            from openQ import load_key_file
            data = load_key_file(path)
            if data is None:
                return
            meta = data.get('metadata', {})
            num_q = meta.get('num_questions')
            # Fall back to counting bubble_answers when metadata is absent
            if num_q is None:
                num_q = len(data.get('bubble_answers', {}))
            skip_q = meta.get('questions_to_skip', '')
            self.numQEntry.delete(0, 'end')
            self.numQEntry.insert(0, str(num_q))
            if skip_q:
                self.ignoreEntry.delete(0, 'end')
                self.ignoreEntry.insert(0, str(skip_q))
            # Auto-update pages per student from the highest page number in open questions
            open_qs = data.get('open_questions', {})
            pages_note = ''
            if open_qs:
                max_page = max((int(qdata.get('page', 1) or 1) for qdata in open_qs.values()), default=1)
                current_pps = int(self.pagesPerStudentEntry.get() or '1')
                if max_page > current_pps:
                    self.pagesPerStudentEntry.delete(0, 'end')
                    self.pagesPerStudentEntry.insert(0, str(max_page))
                    pages_note = f', pages/student set to {max_page}'
                # Auto-check "open-ended questions" checkbox when the key has open questions
                if not self.openQvar.get():
                    self.openQvar.set(1)
                    self._toggle_ai_frame()
            skip_info = f', skip: {skip_q}' if skip_q else ''
            self._log(f'Key metadata loaded: {num_q} questions{skip_info}{pages_note}')
        except Exception as exc:
            self._log(f'Could not read key metadata: {exc}')

    def _open_key_file_editor(self):
        from openQ import KeyFileEditorDialog
        current_path = self.scanKeyFileEntry.get().strip()
        dlg = KeyFileEditorDialog(self.parent, path=current_path)
        if dlg.saved_path:
            self.scanKeyFileEntry.delete(0, 'end')
            self.scanKeyFileEntry.insert(0, dlg.saved_path)

    def _toggle_key_filled_frame(self):
        if self._buildKeyModeVar.get() == 1:
            self._key_filled_frame.grid()
        else:
            self._keyBuildAiVar.set(0)
            self._key_filled_frame.grid_remove()
            self._key_build_ai_row.grid_remove()

    def _toggle_key_build_ai_row(self):
        if self._keyBuildAiVar.get():
            self._key_build_ai_row.grid()
        else:
            self._key_build_ai_row.grid_remove()

    def _on_key_build_context_change(self, selected: str):
        if ai_ocr.PRESET_VALUES.get(selected) is None:
            self._keyBuildCustomContextEntry.grid()
        else:
            self._keyBuildCustomContextEntry.grid_remove()

    def _open_key_builder(self):
        import ast
        from openQ import KeyBuilderDialog
        mode = 'filled' if self._buildKeyModeVar.get() == 1 else 'blank'
        num_mc = 0
        ignores = None
        use_ai = False
        api_key = ''
        ai_context = ''
        if mode == 'filled':
            try:
                num_mc = int(self._keyBuildNumMCEntry.get().strip() or '0')
            except ValueError:
                num_mc = 0
            raw_ign = self._keyBuildIgnoreEntry.get().strip()
            if raw_ign:
                try:
                    ignores = list(ast.literal_eval(raw_ign + ','))
                except Exception:
                    ignores = None
                    self._log(
                        f'Warning: could not parse "Questions to skip" value "{raw_ign}" '
                        '— ignored questions will not be skipped. '
                        'Use comma-separated numbers, e.g.: 3,7,12')
            use_ai = bool(self._keyBuildAiVar.get())
            if use_ai:
                api_key = ai_ocr.load_config().get('anthropic_api_key', '')
                selected = self._keyBuildAiContextVar.get()
                preset_val = ai_ocr.PRESET_VALUES.get(selected)
                ai_context = (
                    self._keyBuildCustomContextEntry.get().strip()
                    if preset_val is None else preset_val)
        dlg = KeyBuilderDialog(self.parent, mode=mode,
                               num_mc_questions=num_mc,
                               ignores=ignores,
                               use_ai=use_ai,
                               api_key=api_key,
                               ai_context=ai_context)
        if dlg.saved_path:
            self._log(f'Key saved: {dlg.saved_path}')

    def _update_thresh_label(self, value):
        self.threshLabel.configure(text=f'{value:.2f}')

    def _update_strictness_label(self, value):
        self.strictnessLabel.configure(text=f'{value:.2f}')

    def _log(self, message):
        self.log_box.configure(state='normal')
        self.log_box.insert('end', message + '\n')
        self.log_box.configure(state='disabled')
        self.log_box.see('end')

    def button_browse_callback(self):
        filename = filedialog.askopenfilename()
        self.fileEntry.delete(0, 'end')
        self.fileEntry.insert(0, filename)

    def button_go_callback(self):
        input_file  = self.fileEntry.get()
        try:
            quests    = int(self.numQEntry.get() or '0')
            bubbleVal = float(self.bubbleValEntry.get())
            openVal   = float(self.openValEntry.get())
            pages_per_student = max(1, int(self.pagesPerStudentEntry.get() or '1'))
        except ValueError as exc:
            self._log(f'Input error: {exc}. Check number of questions and point values.')
            return
        if not input_file:
            self._log('Please choose an input file first.')
            return
        markmissing  = bool(self.setavar.get())
        openQ        = bool(self.openQvar.get())
        save_marked  = bool(self.saveMarkedVar.get())
        corrmark     = bool(self.corrvar.get())
        ignores      = self.ignoreEntry.get()
        thresh       = self.threshVar.get()
        strictness   = self.strictnessVar.get()

        use_ai, api_key, ai_context = self._get_ai_params()
        if use_ai and not api_key:
            self._log('AI OCR is enabled but no API key is configured. '
                      'Click "Configure API Key…" to add one.')
            return
        review_perfect   = bool(self.reviewPerfectVar.get()) if self.openQvar.get() else True
        key_file_path    = self.scanKeyFileEntry.get().strip()

        # ── Multi-version params ───────────────────────────────────────────────
        version_question = 0
        version_key_paths: dict[str, str] = {}
        if self.multiVersionVar.get():
            vq_str = self.versionQEntry.get().strip()
            try:
                version_question = int(vq_str)
                if version_question < 1:
                    raise ValueError('must be >= 1')
            except ValueError:
                self._log('Version question number must be a positive integer (e.g. 64). Please fix and retry.')
                return
            for ver, entry in self._version_key_entries.items():
                # Use full path from _version_key_paths; fall back to entry text
                # (entry only shows basename, so direct entry.get() is not sufficient)
                p = self._version_key_paths.get(ver, '').strip() or entry.get().strip()
                if p:
                    version_key_paths[ver] = p
            if not version_key_paths:
                self._log('Multiple versions is checked but no version key files are loaded. '
                          'Browse for at least one version key file.')
                return

        reuse_aligned = bool(self.reuseAlignedVar.get())

        self._log('Starting scan…')
        old_stdout = sys.stdout
        sys.stdout = TextRedirector(self.log_box)
        try:
            Scanner(input_file, quests, markmissing, openQ, corrmark,
                    ignores, thresh, bubbleVal, openVal,
                    parent=self.parent,
                    ai_ocr=use_ai, api_key=api_key, ai_context=ai_context,
                    review_perfect=review_perfect,
                    key_file_path=key_file_path,
                    pages_per_student=pages_per_student,
                    save_marked=save_marked,
                    strictness=strictness,
                    version_question=version_question,
                    version_key_paths=version_key_paths or None,
                    reuse_aligned=reuse_aligned)
        finally:
            sys.stdout = old_stdout
        self._log('Done.')

