# Results tab

Planned 2026-10-29; phase 1 under way. The gradebook's adjustment row (Exam stats, Points added) shipped the same day as `156cb92` and is the starting point: it showed that adjusting scores is worth doing, but in Excel the instructor sees the effect only after typing, can't fix a key, and still has to paste scores into the Canvas file by hand.

## Settled defaults (Brandon accepted all four, 2026-10-29)

1. **Export: a button, or on every edit?** Default: a button. Edits save to `edits.json` as they are made, but the gradebook and Canvas file are rewritten only on **Export**. Rewriting on every edit would fail whenever the gradebook is open in Excel (Windows locks an open file), and would overwrite it while it was being read.
2. **Re-marking sheets after a key change: first release or later?** Default: later (phase 4). Until then, Export warns that `marked/` and `marked.pdf` still show the original key.
3. **Charts: Tk canvas or matplotlib?** Default: Tk canvas. A histogram and bars need nothing more, and matplotlib noticeably enlarges the packaged app.
4. **Folders scanned before this ships**, which don't record their grading settings: default is to open them using the Scan tab's current settings, with a banner saying so. The alternative is opening them read-only.

## Decisions (Brandon, 2026-10-29)

- **The app is the source of truth, and Excel is downstream.** The app writes `gradebook.xlsx` and `canvas_upload.csv`, overwriting both, and never reads them back. An instructor who edits the gradebook by hand has chosen to finish in Excel and won't reload into the app.
- **Results is a new tab, separate from Re-grade.** Re-grade edits the acceptable answers for written questions; Results covers everything after grading: stats, key fixes, credit, adjustments, export. Results can offer a button that opens the Re-grader for a folder with written answers, and reloads once it closes.
- **A scan opens Results automatically** on its own outputs folder when it finishes.
- **`canvas_upload.csv` carries the final scores**, every edit included, so it uploads as is. The workbook's Canvas scores tab stays as the route for anyone adjusting in Excel afterward.

## Three layers of files

The design separates what the scanner read (never changed), what the instructor decided (a list of edits), and what is shown or exported (always recomputed from the first two). All of it lives in the existing `ExamScanner_outputs/` folder, so "Open results" chooses that folder, as Re-grade does, and there is no new file format to open.

### 1. The raw scan, for archiving

Most of this exists already in `app_data/`: the answers as read with the key on row 0 (`results*.csv`), the written-answer transcriptions and acceptable answers, and the aligned page images. Three gaps:

- `gradeResults` overwrites `results.csv` in place, adding score columns and a `numb_correct` row. Scoring should become a pure function from answers, key and settings to points, which leaves the answers file as the scanner wrote it (plus Re-grade's written-answer judgments, which are part of the base). `results_points.csv` stays as a cache that other code can read, rebuilt on every save.
- The grading settings aren't recorded: select-all, partial-credit strictness, the default bubble and written point values, and the per-question point values. Without them, scoring can't be redone the same way. They go into the grading record (`results_grading.json`) at scan time.
- The key files aren't kept. Copy each into `app_data/keys/` at scan time, so the folder still makes sense after the original key file is edited or lost. The roster is not needed: names are already resolved into the results.

### 2. The edit layer

One file, `app_data/edits.json`: an ordered list, saved after every edit. Each edit has an id, a type, a target, a value, a time, and an optional note ("Q12 stem was ambiguous"). Deleting an edit undoes it, and the list doubles as a record of what changed and why. The types:

- **Key change** for a question on one version: replace the key, or also accept another answer. "Also accept" is new grading behavior: today a bubble question scores against a single key string, so a list of accepted answers has to go into the scoring function.
- **Question credit**, targeted by bank question (`source`) so it reaches every version that printed it, or by version and column for keys without sources. It can do any of these:
  - give everyone who had the question full credit, with points possible unchanged
  - drop the question, removing it from points possible
  - change its point value
- **Point override** for one student on one question: a regrade dispute. Targeted by version and results row, with the student ID stored alongside it as a check, since row order is fixed once the raw layer is.
- **Adjustment**: points added to the class, and per version, as in the gradebook today.

They apply in that order: key changes and credit change how points are earned, overrides then set individual cells, and adjustments go on top of the totals. If a key change lands on a cell that already has an override, the override wins and the app flags it.

### 3. What is shown and exported

Recomputed whenever the edit list changes: raw + edits → `Graded` objects → statistics. Export runs today's `outputs.write` on those objects. Key changes, credit and overrides go into the points, and so into each Total. The adjustments fill the gradebook's Points added cells, so the workbook still shows unadjusted beside adjusted, and the Canvas file gets the adjusted totals.

## Statistics in one place

The workbook computes its stats as Excel formulas; the tab needs the same numbers in Python, live. Move them into a new `analysis.py`, and have both the tab and the workbook writer use it: mean, median, standard deviation, Cronbach's alpha, Canvas's discrimination index (same 27% groups and tie rule), the grade bands (`BANDS` moves there), and the item statistics already in `outputs.item_stats`. The workbook keeps its formulas, so hand edits still recalculate. A test builds a gradebook and checks the Python figures against values worked out by hand from the formula definitions, so the two can't drift silently.

Recomputing must feel instant: under about 100 ms for 300 students and 150 questions. Plain pandas on these sizes is fine; scoring goes once per edit, not once per redraw.

## The tab

customtkinter has no table widget, so tables are `ttk.Treeview` (stdlib), and charts are drawn on a `tk.Canvas`.

- **Header:** the folder, Open…, Export, and a line saying whether there are edits not yet exported.
- **Summary:** the Exam stats figures, unadjusted beside adjusted, with the adjustment inputs; and a grade histogram by band, the unadjusted bars in gray behind the adjusted ones in blue, as in the workbook.
- **Questions:** the item analysis as a sortable table (question, where it sat on each version, key, mean score, discrimination, choice counts, flagged below 0.2). Selecting one shows its choice distribution as bars, with the key marked, plus the key-change and credit actions. A distractor that outdrew the key is the case this exists for.
- **Students:** name, version, total, adjusted. Selecting one shows their answers and points by question, where a points cell can be overridden, plus a button that opens their marked page.
- **Edits:** the list, each with its note and a delete button.

A lab practical (several forms, blanks for questions a form didn't include) goes through the same `Graded` objects and must work from the start. Its tests in `tests/test_practical_*.py` cover the outputs it already has.

## Phases

1. **Foundations, no UI.** A pure scoring function (with "also accept"), grading settings and key copies recorded at scan time, `analysis.py`, and `edits.json` read and applied when building `Graded`, so `outputs.write` honors edits. Tested by building edits in code and checking the exported workbook and CSV.
2. **Read-only tab.** Open a folder, show the summary, histogram, questions and students; open automatically after a scan (scan exams and practicals).
3. **Editing.** Adjustments, question actions, overrides, the edits list, Export.
4. **Afterward.** Re-marking sheets after a key change: `markSheets` needs the aligned images plus the layout and row areas computed during the scan, which would have to be recorded too. Also folders scanned before phase 1 (default 4).

The user docs (`docs/outputs.md`, and a new page for the tab) follow phases 2 and 3.
