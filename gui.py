import sys
import io
import json
from pathlib import Path
from scanner import Scanner
import customtkinter as ctk
from tkinter import filedialog, messagebox
import ai_ocr
import bubbles
import scan_keys
import sheet_layout
from build_tab import BuildExamUI, open_sheet_dialog


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
    Main GUI frame for pyExamKit.
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
        # Build Exam comes first: building an exam here, with its sheet and
        # key, is the usual workflow. Each tab keeps its one action in a
        # footer outside its scrolling settings, so it is always in view.
        tabs = ctk.CTkTabview(self)
        tabs.pack(fill='both', expand=True)

        build_tab  = tabs.add("Build Exam")
        scan_tab   = tabs.add("Scan Exams")
        regrade_tab = tabs.add("Re-grade")
        key_tab    = tabs.add("Standard Sheet")
        BuildExamUI(build_tab, log_fn=self._log).pack(fill='both', expand=True)

        # ════════════════════════════════════════════════════════
        # TAB 1 — Scan Exams
        # ════════════════════════════════════════════════════════
        bold = ctk.CTkFont(weight='bold')
        small = ctk.CTkFont(size=11)
        self._keys = None            # scan_keys.KeySet once key files are chosen
        self._scan_path = ''
        self._roster_path = ''

        scan_footer = ctk.CTkFrame(scan_tab, fg_color='transparent')
        scan_footer.pack(side='bottom', fill='x', pady=(6, 0))
        ctk.CTkButton(scan_footer, text="Scan and Grade", height=40, width=220,
                      font=ctk.CTkFont(size=15, weight='bold'),
                      fg_color='#2563eb', hover_color='#1d4ed8',
                      command=self.button_go_callback).pack(side='right', padx=10)
        self.readyLabel = ctk.CTkLabel(scan_footer, text='', text_color='gray', anchor='w')
        self.readyLabel.pack(side='left', padx=10, fill='x', expand=True)

        scan_frame = ctk.CTkScrollableFrame(scan_tab, fg_color='transparent')
        scan_frame.pack(fill='both', expand=True)
        scan_frame.grid_columnconfigure(0, weight=1)

        def step(row, text, note=''):
            f = ctk.CTkFrame(scan_frame, fg_color='transparent')
            f.grid(row=row, column=0, padx=10, pady=(10, 2), sticky='ew')
            ctk.CTkLabel(f, text=text, font=bold).pack(side='left')
            if note:
                ctk.CTkLabel(f, text=note, text_color='gray').pack(side='left', padx=6)
            return f

        def file_row(row, button, command, placeholder):
            f = ctk.CTkFrame(scan_frame, fg_color='transparent')
            f.grid(row=row, column=0, padx=(24, 10), pady=2, sticky='ew')
            ctk.CTkButton(f, text=button, command=command, width=170).pack(side='left')
            label = ctk.CTkLabel(f, text=placeholder, text_color='gray', anchor='w')
            label.pack(side='left', padx=10)
            return f, label

        # ── 1. Answer key ────────────────────────────────────────────────
        step(0, "1   Answer key")
        key_row, self.keyLabel = file_row(
            1, "Choose key files…", self._browse_key_file,
            "The key CSV from Build Exam; the other versions' keys are found beside it")
        ctk.CTkButton(key_row, text="Edit…", width=70,
                      command=self._open_key_file_editor).pack(side='right')
        self.keySummary = ctk.CTkLabel(scan_frame, text='', anchor='w', justify='left',
                                       wraplength=640)
        self.keySummary.grid(row=2, column=0, padx=(24, 10), pady=(0, 2), sticky='w')

        # Without a key file, the first scanned page is the key and the
        # question count has to be given here.
        self._nokey_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        self._nokey_frame.grid(row=3, column=0, padx=(24, 10), pady=(0, 2), sticky='w')
        ctk.CTkLabel(self._nokey_frame,
                     text="No key file? Put a key sheet you filled in first in the stack, "
                          "and give the number of questions:",
                     text_color='gray', font=small).grid(row=0, column=0, columnspan=2,
                                                        sticky='w')
        ctk.CTkLabel(self._nokey_frame, text="Number of questions:").grid(
            row=1, column=0, pady=2, sticky='w')
        self.numQEntry = ctk.CTkEntry(self._nokey_frame, width=80)
        self.numQEntry.grid(row=1, column=1, padx=10, pady=2, sticky='w')

        # Point defaults, needed only when the key does not carry points
        self._points_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        self._points_frame.grid(row=4, column=0, padx=(24, 10), pady=(0, 2), sticky='w')
        ctk.CTkLabel(self._points_frame, text="Points per bubble question:").grid(
            row=0, column=0, pady=2, sticky='w')
        self.bubbleValEntry = ctk.CTkEntry(self._points_frame, width=80)
        self.bubbleValEntry.insert(0, '1')
        self.bubbleValEntry.grid(row=0, column=1, padx=10, pady=2, sticky='w')
        ctk.CTkLabel(self._points_frame, text="Points per written question:").grid(
            row=1, column=0, pady=2, sticky='w')
        self.openValEntry = ctk.CTkEntry(self._points_frame, width=80)
        self.openValEntry.insert(0, '2')
        self.openValEntry.grid(row=1, column=1, padx=10, pady=2, sticky='w')

        # ── 2. Scans ─────────────────────────────────────────────────────
        step(5, "2   Scanned sheets")
        _, self.scanLabel = file_row(6, "Choose scans…", self.button_browse_callback,
                                     "A PDF of the scanned stack, or the first JPG of a folder")

        # ── 3. Roster ────────────────────────────────────────────────────
        step(7, "3   Class roster", "(optional)")
        roster_row, self.rosterLabel = file_row(
            8, "Choose roster…", self._browse_roster,
            "Canvas gradebook export, or a LastName, FirstName, ID CSV")
        ctk.CTkButton(roster_row, text="Clear", width=70,
                      command=self._clear_roster).pack(side='right')

        # ── Written answers (shown when there are any to grade) ─────────
        self._written_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        self._written_frame.grid(row=9, column=0, padx=10, pady=(12, 2), sticky='ew')
        ctk.CTkLabel(self._written_frame, text="Written answers", font=bold).grid(
            row=0, column=0, sticky='w')
        self.openQvar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(self._written_frame, text="Grade written answers on screen",
                        variable=self.openQvar,
                        command=self._toggle_ai_frame).grid(
            row=1, column=0, padx=(14, 0), pady=2, sticky='w')

        # ── AI OCR sub-frame (shown only when written answers are graded) ──
        self._ai_frame = ctk.CTkFrame(self._written_frame, fg_color='transparent')
        self._ai_frame.grid(row=2, column=0, padx=(34, 10), pady=(0, 2), sticky='w')
        self._ai_frame.grid_remove()

        self.aiOcrVar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(self._ai_frame, text="Transcribe handwriting with AI (Claude)",
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
            font=small,
        ).grid(row=2, column=0, columnspan=3, padx=(0, 4), pady=(4, 2), sticky='w')

        self.reviewPerfectVar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(self._ai_frame,
                        text="Review perfect matches? (confirm even high-confidence correct answers)",
                        variable=self.reviewPerfectVar).grid(
            row=3, column=0, columnspan=3, padx=0, pady=(4, 2), sticky='w')

        strictness_frame = ctk.CTkFrame(self._ai_frame, fg_color='transparent')
        strictness_frame.grid(row=4, column=0, columnspan=3, pady=(4, 2), sticky='w')
        ctk.CTkLabel(strictness_frame,
                     text="Partial credit strictness (0 = generous, 1 = strict):").pack(side='left')
        self.strictnessVar = ctk.DoubleVar(value=0.5)
        self.strictnessSlider = ctk.CTkSlider(strictness_frame, from_=0.0, to=1.0,
                                              variable=self.strictnessVar,
                                              command=self._update_strictness_label,
                                              width=160)
        self.strictnessSlider.pack(side='left', padx=(8, 0))
        self.strictnessLabel = ctk.CTkLabel(strictness_frame, text='0.50', width=40)
        self.strictnessLabel.pack(side='left', padx=6)

        # ── More options (collapsed) ─────────────────────────────────────
        self._more_button = ctk.CTkButton(
            scan_frame, text="▸  More options", anchor='w', width=160,
            fg_color='transparent', text_color=('gray20', 'gray80'),
            hover_color=('gray85', 'gray25'), command=self._toggle_more)
        self._more_button.grid(row=10, column=0, padx=4, pady=(12, 0), sticky='w')
        self._more_frame = ctk.CTkFrame(scan_frame, fg_color='transparent')
        self._more_frame.grid(row=11, column=0, padx=(24, 10), pady=(0, 8), sticky='w')
        self._more_frame.grid_remove()
        mf = self._more_frame

        # Defaults on: these are what most scans want, and they are out of
        # sight here.
        self.saveMarkedVar = ctk.IntVar(value=1)
        ctk.CTkCheckBox(mf, text="Save marked answer sheets (marked/ folder and marked.pdf)",
                        variable=self.saveMarkedVar).grid(
            row=0, column=0, columnspan=2, pady=2, sticky='w')
        self.corrvar = ctk.IntVar(value=1)
        ctk.CTkCheckBox(mf, text="Show the correct answers on marked sheets",
                        variable=self.corrvar).grid(
            row=1, column=0, columnspan=2, pady=2, sticky='w')
        self.setavar = ctk.IntVar(value=1)
        ctk.CTkCheckBox(mf, text="Partial credit on select-all-that-apply questions",
                        variable=self.setavar).grid(
            row=2, column=0, columnspan=2, pady=2, sticky='w')

        ctk.CTkLabel(mf, text="Fill cutoff (lower counts lighter marks, "
                              "higher ignores more erasures):").grid(
            row=3, column=0, pady=(8, 2), sticky='w')
        thresh_frame = ctk.CTkFrame(mf, fg_color='transparent')
        thresh_frame.grid(row=3, column=1, padx=10, pady=(8, 2), sticky='w')
        self.threshVar = ctk.DoubleVar(value=0.35)
        self.threshSlider = ctk.CTkSlider(thresh_frame, from_=0.25, to=0.60,
                                          variable=self.threshVar,
                                          command=self._update_thresh_label,
                                          width=160)
        self.threshSlider.pack(side='left')
        self.threshLabel = ctk.CTkLabel(thresh_frame, text='0.35', width=40)
        self.threshLabel.pack(side='left', padx=6)

        self.ignoreLabel = ctk.CTkLabel(mf, text="Questions to skip (comma-separated):")
        self.ignoreLabel.grid(row=4, column=0, pady=2, sticky='w')
        self.ignoreEntry = ctk.CTkEntry(mf, width=200, placeholder_text="e.g. 12, 30")
        self.ignoreEntry.grid(row=4, column=1, padx=10, pady=2, sticky='w')

        ctk.CTkLabel(mf, text="Pages per student:").grid(row=5, column=0, pady=2, sticky='w')
        self.pagesPerStudentEntry = ctk.CTkEntry(mf, width=60)
        self.pagesPerStudentEntry.insert(0, '1')
        self.pagesPerStudentEntry.grid(row=5, column=1, padx=10, pady=2, sticky='w')

        ctk.CTkLabel(mf, text="Older sheets without version bubbles: question where\n"
                              "students bubbled their version (several versions only):",
                     justify='left').grid(row=6, column=0, pady=2, sticky='w')
        self.versionQEntry = ctk.CTkEntry(mf, width=60, placeholder_text="blank")
        self.versionQEntry.grid(row=6, column=1, padx=10, pady=2, sticky='w')

        self.reuseAlignedVar = ctk.IntVar(value=0)
        ctk.CTkCheckBox(
            mf, text="Re-read without aligning again (fast re-read at a new fill cutoff)",
            variable=self.reuseAlignedVar).grid(
            row=7, column=0, columnspan=2, pady=(8, 2), sticky='w')

        self._refresh_scan_tab()

        # ════════════════════════════════════════════════════════
        # TAB 2 — Standard Sheet: a generic answer sheet and a key built
        # by scanning it, for exams not built on the Build Exam tab
        # ════════════════════════════════════════════════════════
        sheet_frame = ctk.CTkFrame(key_tab, fg_color='transparent')
        sheet_frame.pack(fill='x', pady=(0, 4))
        ctk.CTkLabel(sheet_frame, text="For an exam made outside this app:",
                     font=ctk.CTkFont(weight='bold')).grid(
            row=0, column=0, padx=10, pady=(8, 2), sticky='w')
        ctk.CTkLabel(sheet_frame,
                     text="Print a standard answer sheet, then build its key below from a "
                          "sheet you fill in yourself.\nExams from Build Exam come with their "
                          "own sheet and key, and do not need this tab.",
                     justify='left', text_color='gray').grid(
            row=1, column=0, padx=10, pady=(0, 4), sticky='w')
        ctk.CTkButton(sheet_frame, text="Make Answer Sheet…",
                      command=lambda: open_sheet_dialog(self, self._log)).grid(
            row=2, column=0, padx=10, pady=(2, 8), sticky='w')

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
        regrade_footer = ctk.CTkFrame(regrade_tab, fg_color='transparent')
        regrade_footer.pack(side='bottom', fill='x', pady=(6, 0))
        ctk.CTkButton(regrade_footer, text="Open Re-grader", height=40, width=220,
                      font=ctk.CTkFont(size=15, weight='bold'),
                      command=self._open_regrade_dialog,
                      fg_color='#2563eb', hover_color='#1d4ed8').pack(side='right', padx=10)
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

        # ── Status log (shared, below tabs) ───────────────────────────────
        # No Exit button: the window's own close button does that, and an
        # Exit beside the log was being clicked in place of Run Scan.
        ctk.CTkLabel(self, text="Status log",
                     font=ctk.CTkFont(size=13, weight='bold')).pack(anchor='w', padx=4,
                                                                     pady=(8, 0))
        self.log_box = ctk.CTkTextbox(self, height=120, state='disabled',
                                      font=ctk.CTkFont(family='Courier', size=11))
        self.log_box.pack(fill='x', padx=4, pady=(2, 4))

    # ── Callbacks ─────────────────────────────────────────────────────────

    def _toggle_ai_frame(self):
        """Show or hide the AI OCR sub-frame based on the open-ended checkbox."""
        if self.openQvar.get():
            self._ai_frame.grid()
        else:
            self.aiOcrVar.set(0)
            self._ai_frame.grid_remove()
            self._ai_context_row.grid_remove()

    def _toggle_more(self):
        if self._more_frame.winfo_ismapped():
            self._more_frame.grid_remove()
            self._more_button.configure(text="▸  More options")
        else:
            self._more_frame.grid()
            self._more_button.configure(text="▾  More options")

    def _refresh_scan_tab(self):
        """Show what the chosen keys need, and hide what they make unneeded."""
        ks = self._keys
        if ks is None:
            self._nokey_frame.grid()
            self._points_frame.grid()
            self._written_frame.grid()
            self.keySummary.configure(text='')
            self.ignoreLabel.configure(text="Questions to skip (comma-separated):")
        else:
            self._nokey_frame.grid_remove()
            if ks.has_points:
                self._points_frame.grid_remove()
            else:
                self._points_frame.grid()
            if ks.written:
                self._written_frame.grid()
            else:
                self._written_frame.grid_remove()
            text = '✓  ' + ks.summary()
            if ks.notes:
                text += '\n⚠  ' + '\n⚠  '.join(ks.notes)
            self.keySummary.configure(
                text=text, text_color=('#b45309', '#f59e0b') if ks.notes
                else ('#15803d', '#4ade80'))
            self.ignoreLabel.configure(text="Also skip questions (beyond the key's written ones):")
        self._update_ready()

    def _update_ready(self):
        if not self._scan_path:
            text = 'Choose the scans to grade.'
        elif self._keys is None:
            text = (f'Ready: {Path(self._scan_path).name}, with its first page as the key '
                    '(no key file chosen).')
        else:
            n = len(self._keys.paths)
            text = f'Ready: {Path(self._scan_path).name}, {n} key{"s" if n > 1 else ""}.'
        self.readyLabel.configure(text=text)

    def _clear_roster(self):
        self._roster_path = ''
        self.rosterLabel.configure(
            text="Canvas gradebook export, or a LastName, FirstName, ID CSV", text_color='gray')

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
                     text='Your key is stored in plain text in ~/.pyexamkit_config.json,\n'
                          'readable only by your account. Get a key at console.anthropic.com.',
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
        filenames = filedialog.askopenfilenames(
            title='Choose the key file (the other versions are found beside it)',
            filetypes=[('CSV key file', '*.csv'), ('JSON files', '*.json')])
        if filenames:
            self._load_keys(list(filenames))

    def _browse_roster(self):
        filename = filedialog.askopenfilename(
            title='Choose class roster', filetypes=[('CSV file', '*.csv')])
        if filename:
            self._roster_path = filename
            self.rosterLabel.configure(text=Path(filename).name,
                                       text_color=('gray10', 'gray90'))

    def _load_keys(self, paths: list[str]):
        """Load the chosen keys (and sibling versions) and fit the tab to them."""
        try:
            ks = scan_keys.load_keys(paths)
        except scan_keys.KeySetError as exc:
            self._keys = None
            self.keyLabel.configure(text=str(exc), text_color=('#b91c1c', '#f87171'))
            self._log(f'Key not loaded: {exc}')
            self._refresh_scan_tab()
            return
        self._keys = ks
        names = [Path(ks.paths[v]).name for v in sorted(ks.paths)]
        self.keyLabel.configure(
            text=names[0] + (f'  + {len(names) - 1} more' if len(names) > 1 else ''),
            text_color=('gray10', 'gray90'))
        if ks.pages > int(self.pagesPerStudentEntry.get() or '1'):
            self.pagesPerStudentEntry.delete(0, 'end')
            self.pagesPerStudentEntry.insert(0, str(ks.pages))
        if ks.written and not self.openQvar.get():
            self.openQvar.set(1)
            self._toggle_ai_frame()
        self._log('Keys loaded: ' + ', '.join(names) + f'. {ks.summary()}')
        for note in ks.notes:
            self._log(f'  Note: {note}')
        self._refresh_scan_tab()

    def _open_key_file_editor(self):
        from openQ import KeyFileEditorDialog
        current = self._keys.paths[sorted(self._keys.paths)[0]] if self._keys else ''
        dlg = KeyFileEditorDialog(self.parent, path=current)
        if dlg.saved_path:
            self._load_keys([dlg.saved_path] if not self._keys or not self._keys.multi
                            else list(self._keys.paths.values()))

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
        filename = filedialog.askopenfilename(
            title='Choose the scanned sheets',
            filetypes=[('Scans', '*.pdf *.jpg *.jpeg'), ('All files', '*')])
        if not filename:
            return
        self._scan_path = filename
        note = ''
        if filename.lower().endswith('.pdf'):
            try:
                import fitz
                with fitz.open(filename) as doc:
                    note = f'  ·  {doc.page_count} pages'
            except Exception:
                pass
        self.scanLabel.configure(text=Path(filename).name + note,
                                 text_color=('gray10', 'gray90'))
        self._update_ready()

    def button_go_callback(self):
        input_file = self._scan_path
        if not input_file:
            self._log('Choose the scanned sheets first.')
            return
        ks = self._keys
        try:
            quests = ks.num_questions if ks else int(self.numQEntry.get() or '0')
            bubbleVal = float(self.bubbleValEntry.get())
            openVal = float(self.openValEntry.get())
            pages_per_student = max(1, int(self.pagesPerStudentEntry.get() or '1'))
        except ValueError as exc:
            self._log(f'Input error: {exc}. Check the number of questions, points, '
                      'and pages per student.')
            return
        if not quests:
            self._log('With no key file, give the number of questions.')
            return
        extra = self.ignoreEntry.get().replace(' ', '').strip(',')
        try:
            extra_rows = [int(n) for n in extra.split(',') if n]
        except ValueError:
            self._log(f'Questions to skip should be numbers separated by commas, not "{extra}".')
            return
        ignores = ','.join(str(n) for n in sorted(set((ks.skip if ks else []) + extra_rows)))
        markmissing  = bool(self.setavar.get())
        openQ        = bool(self.openQvar.get())
        save_marked  = bool(self.saveMarkedVar.get())
        corrmark     = bool(self.corrvar.get())
        thresh       = self.threshVar.get()
        strictness   = self.strictnessVar.get()

        use_ai, api_key, ai_context = self._get_ai_params()
        if use_ai and not api_key:
            self._log('AI transcription is on but no API key is configured. '
                      'Click "Configure API Key…" to add one.')
            return
        review_perfect = bool(self.reviewPerfectVar.get()) if openQ else True

        # One key grades the stack directly; several are sorted by the
        # version each student bubbled.
        key_file_path = ''
        version_question = 0
        version_key_paths: dict[str, str] = {}
        if ks and ks.multi:
            version_key_paths = dict(ks.paths)
            vq_str = self.versionQEntry.get().strip()
            try:
                version_question = int(vq_str) if vq_str else 0
                if version_question < 0:
                    raise ValueError
            except ValueError:
                self._log('The version question number must be blank (sheets with version '
                          'bubbles in the header) or a question number, such as 64.')
                return
        elif ks:
            key_file_path = next(iter(ks.paths.values()))

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
                    reuse_aligned=reuse_aligned,
                    roster_path=self._roster_path)
        except (bubbles.KeyedSheetError, sheet_layout.RunsError) as exc:
            sys.stdout = old_stdout
            self._log(f'Scan stopped: {exc}')
            messagebox.showerror('Scan stopped', str(exc))
            return
        finally:
            sys.stdout = old_stdout
        self._log('Done.')

