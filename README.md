<img src="images/AppIcon.png" width="96" alt="pyExamKit icon">

# pyExamKit

A desktop app for building bubble-sheet exams from question banks, then scanning and grading them. Both halves — building and grading — share one file format and one download; there is nothing else to install.

---

## Installation

Download the latest release for your system from the [Releases page](https://github.com/backyardbiomech/pyExamKit/releases/latest).

### Windows

1. Download `PyExamKit-Windows.zip` and extract it — right-click the file and choose **Extract All**. Keep the extracted `PyExamKit` folder together; `PyExamKit.exe` needs the files next to it to run.
2. Double-click `PyExamKit.exe` inside the extracted folder.
   - Windows may show a **SmartScreen** warning ("Windows protected your PC"). Click **More info**, then **Run anyway**. This appears because the app isn't code-signed, not because anything is wrong with it.
3. On future launches, just double-click `PyExamKit.exe` again.

### Mac

1. Download `PyExamKit-macOS.dmg` and open it.
2. Drag `PyExamKit.app` into your **Applications** folder (or onto your Desktop).
3. **Before opening**, open `Terminal` and remove the macOS quarantine flag. If you moved the app to Applications:

   ```bash
   xattr -cr /Applications/PyExamKit.app
   ```

   If you left it on the Desktop instead:

   ```bash
   xattr -cr ~/Desktop/PyExamKit.app
   ```

   > **Why is this necessary?** macOS marks anything downloaded from the internet with a quarantine attribute and blocks unsigned apps that carry it. `xattr -cr` removes that attribute so Gatekeeper allows the app to run.

4. Double-click `PyExamKit.app` to launch it. If you still see an "unidentified developer" warning, right-click the app icon, choose **Open**, then click **Open** in the dialog.

---

## Quick start

The app opens to one window with four tabs, sharing a single log at the bottom.

- **Build Exam** — build a printable exam from one or more question-bank text files: pick pools and how many questions to draw from each, set shuffle and version options, and generate scrambled versions plus an answer key. Supports multiple choice, multiple answer, multiple dropdown, true/false, short answer, and the ordering/matching question types.
- **Build Key** — fill in an answer key by hand-scanning a marked answer sheet, or let the app fill in the bubbles for you from a plain list of answers.
- **Scan Exams** — scan a stack of completed answer sheets (with the key as the first page) and grade them against it.
- **Re-grade** — re-run grading against already-scanned images, without rescanning, if you need to change the key or answer-choice rules after the fact.

For the full walkthrough of making a key and scanning exams, see [Usage_Instructions.md](Usage_Instructions.md).

---

## License

GPLv3 — see [LICENSE](LICENSE).
