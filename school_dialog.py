'''
The Sheet settings dialog: the school's logo, ID label, ID prefix, and ID
length, which every sheet printed afterward uses (see school.py).
'''
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

import school


def open_school_dialog(parent, log_fn, on_saved=None):
    '''on_saved is called after a save, so a field elsewhere showing one of
    these settings (the Scan tab's prefix) can refresh.'''
    win = ctk.CTkToplevel(parent)
    win.title('Sheet settings')
    win.transient(parent.winfo_toplevel())
    win.grab_set()
    pad = {'padx': 12, 'pady': 4, 'sticky': 'w'}
    small = ctk.CTkFont(size=11)

    ctk.CTkLabel(win, text='Every answer sheet printed from now on uses these. Sheets '
                           'already printed still scan as they were printed.',
                 font=small, text_color='gray', wraplength=420, justify='left').grid(
        row=0, column=0, columnspan=3, padx=12, pady=(12, 6), sticky='w')

    # Logo: the bundled one, a file of the user's, or none
    stored = school.logo_setting()
    choice = ctk.StringVar(value='default' if stored in (None, school.USE_DEFAULT)
                           else 'none' if stored == '' else 'file')
    logo_path = ctk.StringVar(value=stored if choice.get() == 'file' else '')
    ctk.CTkLabel(win, text='Logo:').grid(row=1, column=0, **pad)
    ctk.CTkRadioButton(win, text='Longwood', variable=choice, value='default').grid(
        row=1, column=1, **pad)
    ctk.CTkRadioButton(win, text='None', variable=choice, value='none').grid(
        row=1, column=2, **pad)
    file_row = ctk.CTkFrame(win, fg_color='transparent')
    file_row.grid(row=2, column=1, columnspan=2, padx=12, pady=2, sticky='w')
    ctk.CTkRadioButton(file_row, text='File:', variable=choice, value='file').pack(side='left')
    file_label = ctk.CTkLabel(file_row, text='', text_color='gray', anchor='w', width=180)
    file_label.pack(side='left', padx=6)

    def show_file(*_):
        file_label.configure(text=Path(logo_path.get()).name if logo_path.get() else 'none chosen')
    logo_path.trace_add('write', show_file)
    show_file()

    def browse():
        path = filedialog.askopenfilename(
            parent=win, title='Choose a logo',
            filetypes=[('PDF or image', '*.pdf *.png *.jpg *.jpeg')])
        if path:
            logo_path.set(path)
            choice.set('file')
    ctk.CTkButton(file_row, text='Choose…', width=80, command=browse).pack(side='left')
    ctk.CTkLabel(win, text='A wide logo prints 2.5 in wide; a taller one is shrunk to fit. '
                           'A PDF prints sharpest.',
                 font=small, text_color='gray').grid(row=3, column=1, columnspan=2,
                                                     padx=12, sticky='w')

    ctk.CTkLabel(win, text='ID heading:').grid(row=4, column=0, **pad)
    label = ctk.CTkEntry(win, width=220)
    label.insert(0, school.id_label())
    label.grid(row=4, column=1, columnspan=2, **pad)

    ctk.CTkLabel(win, text='ID prefix:').grid(row=5, column=0, **pad)
    prefix = ctk.CTkEntry(win, width=60, placeholder_text='none')
    prefix.insert(0, school.id_prefix())
    prefix.grid(row=5, column=1, **pad)
    ctk.CTkLabel(win, text='Printed before the ID boxes, and put before each ID in the '
                           'Canvas file. Leave it blank if your IDs are only digits.',
                 font=small, text_color='gray', wraplength=420, justify='left').grid(
        row=6, column=0, columnspan=3, padx=12, sticky='w')

    ctk.CTkLabel(win, text='ID digits:').grid(row=7, column=0, **pad)
    digits = ctk.StringVar(value=str(school.id_digits()))
    ctk.CTkOptionMenu(win, variable=digits, width=70,
                      values=[str(n) for n in range(school.MIN_DIGITS,
                                                    school.MAX_DIGITS + 1)]).grid(
        row=7, column=1, **pad)

    def save():
        logo = {'default': school.USE_DEFAULT, 'none': ''}.get(choice.get(), logo_path.get())
        try:
            if choice.get() == 'file' and not logo:
                raise ValueError('Choose a logo file, or pick Longwood or None.')
            n = school.check(logo, digits.get())
        except ValueError as exc:
            messagebox.showerror('Sheet settings', str(exc), parent=win)
            return
        school.save(logo_path=logo, label=label.get(), prefix=prefix.get(), digits=n)
        log_fn(f'Sheet settings saved: {n}-digit ID'
               + (f' after "{school.id_prefix()}"' if school.id_prefix() else ''))
        if on_saved:
            on_saved()
        win.destroy()

    ctk.CTkButton(win, text='Save', command=save).grid(
        row=8, column=0, columnspan=3, pady=(10, 12))
