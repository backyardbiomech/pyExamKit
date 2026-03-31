import sys
import io
from scanner import Scanner
from keymaker import KeyMaker
import customtkinter as ctk
from tkinter import filedialog


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

        # ── Scan section ──────────────────────────────────────────────────
        scan_frame = ctk.CTkFrame(self)
        scan_frame.pack(fill='x', pady=(0, 8))

        ctk.CTkLabel(scan_frame, text="Scan Exams",
                     font=ctk.CTkFont(size=16, weight='bold')).grid(
            row=0, column=0, columnspan=2, sticky='w', padx=10, pady=(8, 4))

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
                        variable=self.openQvar).grid(
            row=5, column=0, columnspan=2, padx=10, pady=4, sticky='w')

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

        # ── Key maker section ──────────────────────────────────────────────
        sep = ctk.CTkFrame(self, height=2, fg_color='gray60')
        sep.pack(fill='x', pady=8)

        key_frame = ctk.CTkFrame(self)
        key_frame.pack(fill='x', pady=(0, 8))

        ctk.CTkLabel(key_frame, text="Make an Answer Key",
                     font=ctk.CTkFont(size=16, weight='bold')).grid(
            row=0, column=0, columnspan=2, sticky='w', padx=10, pady=(8, 4))

        ctk.CTkButton(key_frame, text="Choose JPG of blank answer sheet",
                      command=self.button_keyimg_callback).grid(
            row=1, column=0, padx=10, pady=4, sticky='w')
        self.keyImgEntry = ctk.CTkEntry(key_frame, width=400)
        self.keyImgEntry.grid(row=1, column=1, padx=10, pady=4, sticky='ew')

        ctk.CTkButton(key_frame, text="Choose CSV of answers",
                      command=self.button_keyFile_callback).grid(
            row=2, column=0, padx=10, pady=4, sticky='w')
        self.keyFileEntry = ctk.CTkEntry(key_frame, width=400)
        self.keyFileEntry.grid(row=2, column=1, padx=10, pady=4, sticky='ew')

        ctk.CTkLabel(key_frame, text="Exam version letter (A–D):").grid(
            row=3, column=0, padx=10, pady=4, sticky='w')
        self.keyVersionEntry = ctk.CTkEntry(key_frame, width=60)
        self.keyVersionEntry.insert(0, 'A')
        self.keyVersionEntry.grid(row=3, column=1, padx=10, pady=4, sticky='w')

        ctk.CTkButton(key_frame, text="Make the Key",
                      command=self.button_makekey_callback).grid(
            row=4, column=0, columnspan=2, pady=10)

        # ── Status log ────────────────────────────────────────────────────
        sep2 = ctk.CTkFrame(self, height=2, fg_color='gray60')
        sep2.pack(fill='x', pady=8)

        ctk.CTkLabel(self, text="Status Log",
                     font=ctk.CTkFont(size=13, weight='bold')).pack(anchor='w', padx=4)
        self.log_box = ctk.CTkTextbox(self, height=120, state='disabled',
                                      font=ctk.CTkFont(family='Courier', size=11))
        self.log_box.pack(fill='x', padx=4, pady=(2, 8))

        # ── Exit ──────────────────────────────────────────────────────────
        ctk.CTkButton(self, text='Exit', command=sys.exit,
                      fg_color='gray40', hover_color='gray30').pack(pady=(0, 4))

    # ── Callbacks ─────────────────────────────────────────────────────────

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

        self._log('Starting scan…')
        old_stdout = sys.stdout
        sys.stdout = TextRedirector(self.log_box)
        try:
            Scanner(input_file, quests, markmissing, openQ, corrmark,
                    ignores, thresh, bubbleVal, openVal,
                    parent=self.parent)
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
