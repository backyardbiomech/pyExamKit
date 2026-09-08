# Installation

Download the latest release for your system from the [Releases page](https://github.com/backyardbiomech/pyExamKit/releases/latest). The download contains everything the app needs; there is no Python to install and no environment to set up.

## Windows

Download `PyExamKit-Windows.zip` and extract it — right-click the file and choose **Extract All**. Keep the extracted `PyExamKit` folder together, because `PyExamKit.exe` needs the files next to it to run. Double-click `PyExamKit.exe` inside that folder.

Windows may show a **SmartScreen** warning ("Windows protected your PC"). Click **More info**, then **Run anyway**. The warning appears because the app is not code-signed, not because anything is wrong with it. On future launches, just double-click `PyExamKit.exe` again.

## Mac

Download `PyExamKit-macOS.dmg`, open it, and drag `PyExamKit.app` into your **Applications** folder (or onto your Desktop).

**Before opening it**, open Terminal and remove the macOS quarantine flag. If you moved the app to Applications:

```bash
xattr -cr /Applications/PyExamKit.app
```

If you left it on the Desktop instead:

```bash
xattr -cr ~/Desktop/PyExamKit.app
```

macOS marks anything downloaded from the internet with a quarantine attribute and blocks unsigned apps that carry it. `xattr -cr` removes that attribute so Gatekeeper allows the app to run.

Then double-click `PyExamKit.app` to launch it. If you still see an "unidentified developer" warning, right-click the app icon, choose **Open**, then click **Open** in the dialog.

## Running from source

The packaged app is the supported way to run pyExamKit, but the repository runs directly under Python 3.11 or newer. [uv](https://docs.astral.sh/uv/) handles the environment:

```bash
git clone https://github.com/backyardbiomech/pyExamKit.git
cd pyExamKit
uv sync
uv run python pyExamKit.py
```

The dependencies are Pillow, numpy, pandas, opencv-python-headless, PyMuPDF, fpdf2, customtkinter, anthropic, openpyxl, and Jinja2. Everything is a pure-Python or self-contained wheel, so there is no compiler step and no conda involved.

To build the packaged app yourself, add the dev dependency group and run PyInstaller against the bundled spec:

```bash
uv sync --group dev
uv run pyinstaller pyexamkit.spec
```

The version number comes from the git tag by way of hatch-vcs, so a build made off a tag reports that tag and a build made between tags reports a development version.

## What to print

The `images/` folder in the repository holds ready-made answer sheet PDFs in 30, 60, 90, 120, and 150 question sizes, plus the Adobe Illustrator source. See [Answer sheets](answer-sheets.md) for which one to use and how far it can be modified.

---

Next: [Question bank format](question-bank-format.md)
