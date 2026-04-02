import sys
import io
from scanner import Scanner
from keymaker import KeyMaker
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
        self.parent.resizable(False, False)
        self.pack(fill='both', expand=True, padx=16, pady=16)

        # ── Tab view ──────────────────────────────────────────────────────
        tabs = ctk.CTkTabview(self)
        tabs.pack(fill='both', expand=True)

        scan_tab   = tabs.add("Scan Exams")
        key_tab    = tabs.add("Make Key")
        regrade_tab = tabs.add("Re-grade")

        # ════════════════════════════════════════════════════════
        # TAB 1 — Scan Exams
        # ════════════════════════════════════════════════════════
        scan_frame = ctk.CTkFrame(scan_tab, fg_color='transparent')
        scan_frame.pack(fill='x', pady=(0, 8))

        ctk.CTkButton(scan_frame, text="Choose PDF of scans or JPG of key",
                      command=self.button_browse_callback).grid(
            row=0, column=0, padx=10, pady=4, sticky='w')
        self.fileEntry = ctk.CTkEntry(scan_frame, width=400)
        self.fileEntry.grid(row=0, column=1, padx=10, pady=4, sticky='ew')

        ctk.CTkLabel(scan_frame, text="Number of questions to grade:").grid(
            row=1, column=0, padx=10, pady=4, sticky='w')
        self.numQEntry = ctk.CTkEntry(scan_frame, width=80)
        self.numQEntry.grid(row=1, column=1, padx=10, pady=4, sticky='w')

        ctk.CTkLabel(scan_frame, text="Question numbers to ignore (comma-separated):").grid(
            row=2, column=0, padx=10, pady=4, sticky='w')
        self.ignoreEntry = ctk.CTkEntry(scan_frame, width=300)
        self.ignoreEntry.grid(row=2, column=1, padx=10, pady=4, sticky='w')

        self.setavar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(scan_frame, text="Select-all-that-apply questions?",
                        variable=self.setavar).grid(
            row=3, column=0, columnspan=2, padx=10, pady=4, sticky='w')

        self.openQvar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(scan_frame, text="Open-ended questions to grade on-screen? (with OCR assist)",
                        variable=self.openQvar,
                        command=self._toggle_ai_frame).grid(
            row=4, column=0, columnspan=2, padx=10, pady=4, sticky='w')

        # ── AI OCR sub-frame (shown only when open-ended is checked) ──────
        self._ai_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        self._ai_frame.grid(row=5, column=0, columnspan=2, padx=(30, 10), pady=(0, 2), sticky='w')
        self._ai_frame.grid_remove()

        # Acceptable answers file picker
        acc_file_row = ctk.CTkFrame(self._ai_frame, fg_color='transparent')
        acc_file_row.grid(row=0, column=0, columnspan=3, padx=0, pady=(2, 2), sticky='w')
        ctk.CTkLabel(acc_file_row,
                     text="Acceptable answers file (optional):").grid(
            row=0, column=0, padx=(0, 6), pady=2, sticky='w')
        self.accAnswersEntry = ctk.CTkEntry(
            acc_file_row, width=320,
            placeholder_text=".json or .csv — leave blank to type answers during grading")
        self.accAnswersEntry.grid(row=0, column=1, padx=(0, 6), pady=2, sticky='w')
        ctk.CTkButton(acc_file_row, text="Browse…",
                      command=self._browse_acc_answers, width=80).grid(
            row=0, column=2, padx=(0, 4), pady=2, sticky='w')

        self.aiOcrVar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(self._ai_frame, text="Use AI OCR (Claude) for handwriting recognition",
                        variable=self.aiOcrVar,
                        command=self._toggle_ai_context_row).grid(
            row=1, column=0, columnspan=3, padx=0, pady=(2, 2), sticky='w')

        # Context selection row (shown only when AI OCR is checked)
        self._ai_context_row = ctk.CTkFrame(self._ai_frame, fg_color='transparent')
        self._ai_context_row.grid(row=2, column=0, columnspan=3, padx=(20, 0), pady=(0, 2), sticky='w')
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

        self.corrvar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(scan_frame, text="Mark correct answers on graded sheets?",
                        variable=self.corrvar).grid(
            row=6, column=0, columnspan=2, padx=10, pady=4, sticky='w')

        ctk.CTkLabel(scan_frame, text="Points per bubble question:").grid(
            row=7, column=0, padx=10, pady=4, sticky='w')
        self.bubbleValEntry = ctk.CTkEntry(scan_frame, width=80)
        self.bubbleValEntry.insert(0, '1')
        self.bubbleValEntry.grid(row=7, column=1, padx=10, pady=4, sticky='w')

        ctk.CTkLabel(scan_frame, text="Points per open-ended question:").grid(
            row=8, column=0, padx=10, pady=4, sticky='w')
        self.openValEntry = ctk.CTkEntry(scan_frame, width=80)
        self.openValEntry.insert(0, '2')
        self.openValEntry.grid(row=8, column=1, padx=10, pady=4, sticky='w')

        ctk.CTkLabel(
            scan_frame,
            text="Fill threshold (0.20 = lighter marks, 0.30 = ignore light erases):",
        ).grid(row=9, column=0, padx=10, pady=4, sticky='w')
        thresh_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        thresh_frame.grid(row=9, column=1, padx=10, pady=4, sticky='w')
        self.threshVar = ctk.DoubleVar(value=0.25)
        self.threshSlider = ctk.CTkSlider(thresh_frame, from_=0.10, to=0.40,
                                          variable=self.threshVar,
                                          command=self._update_thresh_label,
                                          width=200)
        self.threshSlider.pack(side='left')
        self.threshLabel = ctk.CTkLabel(thresh_frame, text='0.25', width=40)
        self.threshLabel.pack(side='left', padx=6)

        ctk.CTkButton(scan_frame, text="Run Scan",
                      command=self.button_go_callback,
                      fg_color='#2563eb', hover_color='#1d4ed8').grid(
            row=10, column=0, columnspan=2, pady=10)

        # ════════════════════════════════════════════════════════
        # TAB 2 — Make Key
        # ════════════════════════════════════════════════════════
        key_frame = ctk.CTkFrame(key_tab, fg_color='transparent')
        key_frame.pack(fill='x', pady=(0, 8))

        ctk.CTkButton(key_frame, text="Choose JPG of blank answer sheet",
                      command=self.button_keyimg_callback).grid(
            row=0, column=0, padx=10, pady=4, sticky='w')
        self.keyImgEntry = ctk.CTkEntry(key_frame, width=400)
        self.keyImgEntry.grid(row=0, column=1, padx=10, pady=4, sticky='ew')

        ctk.CTkButton(key_frame, text="Choose CSV of answers",
                      command=self.button_keyFile_callback).grid(
            row=1, column=0, padx=10, pady=4, sticky='w')
        self.keyFileEntry = ctk.CTkEntry(key_frame, width=400)
        self.keyFileEntry.grid(row=1, column=1, padx=10, pady=4, sticky='ew')

        ctk.CTkLabel(key_frame, text="Exam version letter (A–D):").grid(
            row=2, column=0, padx=10, pady=4, sticky='w')
        self.keyVersionEntry = ctk.CTkEntry(key_frame, width=60)
        self.keyVersionEntry.insert(0, 'A')
        self.keyVersionEntry.grid(row=2, column=1, padx=10, pady=4, sticky='w')

        ctk.CTkButton(key_frame, text="Make the Key",
                      command=self.button_makekey_callback).grid(
            row=3, column=0, columnspan=2, pady=10)

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

    def _browse_acc_answers(self):
        filename = filedialog.askopenfilename(
            title='Choose acceptable answers file',
            filetypes=[('JSON files', '*.json'), ('CSV files', '*.csv'),
                       ('All files', '*.*')])
        if filename:
            self.accAnswersEntry.delete(0, 'end')
            self.accAnswersEntry.insert(0, filename)

    def _browse_regrade_csv(self):
        filename = filedialog.askopenfilename(
            filetypes=[('CSV files', '*.csv'), ('All files', '*.*')])
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

    def _update_thresh_label(self, value):
        self.threshLabel.configure(text=f'{value:.2f}')

    def _log(self, message):
        self.log_box.configure(state='normal')
        self.log_box.insert('end', message + '\n')
        self.log_box.configure(state='disabled')
        self.log_box.see('end')

    def button_browse_callback(self):
        filename = filedialog.askopenfilename()
        self.fileEntry.delete(0, 'end')
        self.fileEntry.insert(0, filename)

    def button_keyimg_callback(self):
        filename = filedialog.askopenfilename()
        self.keyImgEntry.delete(0, 'end')
        self.keyImgEntry.insert(0, filename)

    def button_keyFile_callback(self):
        filename = filedialog.askopenfilename()
        self.keyFileEntry.delete(0, 'end')
        self.keyFileEntry.insert(0, filename)

    def button_go_callback(self):
        input_file  = self.fileEntry.get()
        try:
            quests    = int(self.numQEntry.get())
            bubbleVal = float(self.bubbleValEntry.get())
            openVal   = float(self.openValEntry.get())
        except ValueError as exc:
            self._log(f'Input error: {exc}. Check number of questions and point values.')
            return
        if not input_file:
            self._log('Please choose an input file first.')
            return
        markmissing = bool(self.setavar.get())
        openQ       = bool(self.openQvar.get())
        corrmark    = bool(self.corrvar.get())
        ignores     = self.ignoreEntry.get()
        thresh      = self.threshVar.get()

        use_ai, api_key, ai_context = self._get_ai_params()
        if use_ai and not api_key:
            self._log('AI OCR is enabled but no API key is configured. '
                      'Click "Configure API Key…" to add one.')
            return
        acc_answers_file = self.accAnswersEntry.get().strip() if self.openQvar.get() else ''

        self._log('Starting scan…')
        old_stdout = sys.stdout
        sys.stdout = TextRedirector(self.log_box)
        try:
            Scanner(input_file, quests, markmissing, openQ, corrmark,
                    ignores, thresh, bubbleVal, openVal,
                    parent=self.parent,
                    ai_ocr=use_ai, api_key=api_key, ai_context=ai_context,
                    preloaded_file=acc_answers_file)
        finally:
            sys.stdout = old_stdout
        self._log('Done.')

    def button_makekey_callback(self):
        keyImg     = self.keyImgEntry.get()
        keyFile    = self.keyFileEntry.get()
        keyVersion = self.keyVersionEntry.get()
        self._log('Making key…')
        old_stdout = sys.stdout
        sys.stdout = TextRedirector(self.log_box)
        try:
            KeyMaker(keyImg, keyFile, keyVersion)
        finally:
            sys.stdout = old_stdout
        self._log('Key created.')
