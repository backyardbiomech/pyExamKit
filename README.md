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

## Building an exam

The **Build Exam** tab turns one or more plain-text question banks into a printable exam: an HTML and a Markdown version to print or post, plus a key CSV the **Scan Exams** tab grades against. Point it at either a single **Exact File**, used exactly as written in file order, or one or more **Question Pools**, where you choose how many questions to randomly draw from each pool and at what point value — adding a pool file shows how many questions it actually contains and defaults the draw count to 10, or the bank's own total if smaller. A pool's own **Pts/Q** column overrides the exam-wide **Default pts/question**, but a `(N pts)` tag inside the source file always wins over both.

Shuffle question order and answer order independently, generate up to six lettered versions (A–F, the most the six-bubble answer sheet can encode) in one pass, and optionally force every version to draw the identical set of questions rather than a fresh random sample each time. An optional version-identifier question, placed at the start or end of the exam, adds a "fill in the bubble for version X" question so the scanner can tell versions apart automatically when grading.

### Question bank format

Each question is a blank-line-separated block of plain text: an optional two-letter type code on its own line (`MC` if omitted), an optional `image: filename.png` line, an optional point-value line like `(2 pts)`, then the numbered stem. These are the same files qtiConverter reads for Canvas, so one bank works for both.

```
MC
(2 pts)
1. Which layer of the epidermis is deepest?
*A. stratum basale
B. stratum corneum
C. stratum lucidum
D. stratum granulosum
```

`MA` (multiple answer) is the same shape with more than one `*`-starred answer — a plain `MC` block is promoted to `MA` automatically the moment a second star shows up, so the type line rarely needs to say `MA` by hand. `TF` takes one `A: True` or `A: False` line instead of lettered answers. `SA` (short answer) lists acceptable answers the same way as MC, `*` marking full credit and unstarred answers worth partial credit — or all of them full credit, if none are starred — and a run of three or more underscores in the stem (`___`) renders as a fill-in blank. `MD` (multiple dropdown) places a `[label]` placeholder inline in the stem for each dropdown, then lists that dropdown's options as `label: text` / `*label: text` for the correct one:

```
MD
1. The [bone] articulates with the humerus, forming the [joint].
*bone: scapula
bone: clavicle
joint: elbow
*joint: shoulder
```

`OR` (ordering) and `MT` (matching) are paper-specific: they come from qtiConverter unchanged, but each occupies one answer bubble per item on the printed sheet, capped at **six** by the sheet's six-bubble layout, with points split evenly across those slots. An `OR` block lists its items already in the correct order, bracketed by a `toplabel`/`bottomlabel` pair — pyExamKit always scrambles the display order regardless of the shuffle-answers setting, since printing them in source order would print the answer key as the question:

```
OR
1. Order these skin layers from most to least superficial.
toplabel: most superficial
1: stratum corneum
2: stratum granulosum
3: stratum spinosum
4: stratum basale
bottomlabel: least superficial
```

An `MT` block gives each left item's correct right-hand label in brackets, then lists every right option including distractors; multiple lefts may share one right, and rights beyond the six-option cap get trimmed down to it, keeping every right that's somebody's correct answer and randomly sampling distractors for what's left. As with `OR`, the right-hand options are always scrambled regardless of the shuffle-answers setting — banks usually declare the lefts in the same order as the rights they point at, so printing them in source order would run the answer key straight down the page:

```
MT
1. Match each epithelium to its function.
[right1]left1: simple squamous epithelium
[right2]left2: simple columnar epithelium
right1: diffusion
right2: absorption
right3: protection
```

Other qtiConverter block types (`ES`, `MB`, `NU`, `CT`, `HS`) are Canvas-only — pyExamKit skips them with a warning in the log rather than failing the whole bank.

---

## License

GPLv3 — see [LICENSE](LICENSE).
