# Results tab

Planned 2026-10-29. Phases 1 (foundations) and 2 (the read-only tab) shipped the same day; see "Phase 1 as built" and "Phase 2 as built" at the end. The gradebook's adjustment row (Exam stats, Points added) shipped the same day as `156cb92` and is the starting point: it showed that adjusting scores is worth doing, but in Excel the instructor sees the effect only after typing, can't fix a key, and still has to paste scores into the Canvas file by hand.

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

## Phase 1 as built (2026-10-29)

Two gaps in "The raw scan" turned out not to be gaps. `gradeResults` does rewrite `results.csv`, but it only appends derived columns (`score`, `partialscore`) and a `numb_correct` row; the answers and the key row are left as read, and `outputs` already ignores the derived ones. So the answers file stays the raw layer and the scorer still writes it. The key files need no copies either: row 0 of each results file is the key, and the grading record holds the sources, choices, texts and points, which is everything rescoring uses.

`grade_functions.score_answer` is the scoring rule pulled out of `gradeResults`, with a list of accepted keys added; on 300 random gradings across every combination of select-all, written answers, strictness and point values it gives the same points as before. The grading record now keeps a `settings` entry (partial credit, strictness, default points) so a key edit scores the way the scan did.

`edits.py` owns `edits.json` and `apply()`, and `outputs.write` applies the edits every time, so Re-grade keeps them. A new scan into the folder renames the old file to `edits_replaced_<time>.json` rather than applying it to different sheets. Adjustments fill the gradebook's Points added cells and are added to the Canvas file's scores.

`analysis.py` holds the statistics in Python, and `outputs` takes `BANDS` and `DI_GROUP` from it. One subtlety: the gradebook's band counts join the cutoff into the COUNTIFS criterion as text (`">="&0.93*30`), and Excel writes that number to 15 significant digits, so 27.9 of 30 is an A in the workbook although 0.93 × 30 is 27.900000000000002 as a double. `analysis` rounds its cutoffs the same way (checked in Excel).

## Phase 2 as built (2026-10-29)

`results_model.py` computes everything the tab shows from a folder with its edits applied, with no Tk, so it is tested without a display; `results_tab.py` draws it, and `charts.py` holds the two Canvas charts (the grade bands before and after adjusting, and one question's answers with the key in green). The tab sits after Scan Exams, and a finished scan, exam or practical, opens it on its own outputs folder. The adjusted columns and the second chart series appear only once there is an adjustment, so an unadjusted exam isn't shown everything twice.

A student's marked pages are found by name and ID. Their filenames also carry the sheet's place in the stack, which a version's results rows don't record, so two students whose names and IDs were both unread would share a match.

One layout trap, worth knowing before adding to the tab: a label that sets its own `wraplength` from its own `<Configure>` width changes its size, which sends `<Configure>` again. In the full window that loop ran inside Tk until Python's recursion limit. Wrap to a parent's width or a fixed width instead. `tests/test_results_tab.py` shows every view in a child process with a time limit, which catches a loop that never settles; with the small fixture the old loop settled slowly rather than running away, so the test doesn't reproduce that particular one.

## Where it stands (handoff, 2026-10-29)

Phases 1 and 2 are on main (`6338a0a`, `f67470b`). Brandon looked at the tab on the synthetic demo and was satisfied for now; he had no layout changes. Next is phase 3: the adjustment inputs, the question actions (change key, also accept, full credit, drop, change points), point overrides from the Students view, the edits list with notes and delete, and Export. All of it goes through `edits.make`/`edits.save` and then a reload of `results_model.open_folder`; Export calls `outputs.write`, which already applies the edits. Defaults 1 to 4 at the top of this file are settled. User docs (`docs/outputs.md` and a page for the tab) follow phase 3.

Open item: Brandon's folder `~/Desktop/2nd_exam/ExamScanner_outputs` (scanned 2026-10-28) wouldn't open. It holds `ALERT.txt`, `marked/` and `app_data/aligned` and `scanJPGs`, but no results files, gradebook or Canvas file anywhere, so the tab rightly found nothing to show. Ask him whether he moved those files or the scan stopped partway; if the scan stopped, that's a scanner bug to find. Either way, the tab's message could say what it looked for. Don't open or list `marked/` (its filenames are student names) or read any results file into the conversation (FERPA).

Running Tk in the agent's shell: the sandbox sometimes can't find Tcl, so export `TCL_LIBRARY` and `TK_LIBRARY` pointing at `lib/tcl8.6` and `lib/tk8.6` of the uv-managed Python. Screen capture isn't permitted there, so layout checks go through Tk geometry (widget boxes, canvas text bounding boxes) rather than screenshots.
