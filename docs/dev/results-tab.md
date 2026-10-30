# Results tab

Planned 2026-10-29. Phases 1 (foundations), 2 (the read-only tab) and 3 (editing) were built the same day; see the "as built" sections at the end. The gradebook's adjustment row (Exam stats, Points added) shipped the same day as `156cb92` and is the starting point: it showed that adjusting scores is worth doing, but in Excel the instructor sees the effect only after typing, can't fix a key, and still has to paste scores into the Canvas file by hand.

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

The user docs are `docs/outputs.md` and `docs/results.md`.

## Phase 1 as built (2026-10-29)

Two gaps in "The raw scan" turned out not to be gaps. `gradeResults` does rewrite `results.csv`, but it only appends derived columns (`score`, `partialscore`) and a `numb_correct` row; the answers and the key row are left as read, and `outputs` already ignores the derived ones. So the answers file stays the raw layer and the scorer still writes it. The key files need no copies either: row 0 of each results file is the key, and the grading record holds the sources, choices, texts and points, which is everything rescoring uses.

`grade_functions.score_answer` is the scoring rule pulled out of `gradeResults`, with a list of accepted keys added; on 300 random gradings across every combination of select-all, written answers, strictness and point values it gives the same points as before. The grading record now keeps a `settings` entry (partial credit, strictness, default points) so a key edit scores the way the scan did.

`edits.py` owns `edits.json` and `apply()`, and `outputs.write` applies the edits every time, so Re-grade keeps them. A new scan into the folder renames the old file to `edits_replaced_<time>.json` rather than applying it to different sheets. Adjustments fill the gradebook's Points added cells and are added to the Canvas file's scores.

`analysis.py` holds the statistics in Python, and `outputs` takes `BANDS` and `DI_GROUP` from it. One subtlety: the gradebook's band counts join the cutoff into the COUNTIFS criterion as text (`">="&0.93*30`), and Excel writes that number to 15 significant digits, so 27.9 of 30 is an A in the workbook although 0.93 × 30 is 27.900000000000002 as a double. `analysis` rounds its cutoffs the same way (checked in Excel).

## Phase 2 as built (2026-10-29)

`results_model.py` computes everything the tab shows from a folder with its edits applied, with no Tk, so it is tested without a display; `results_tab.py` draws it, and `charts.py` holds the two Canvas charts (the grade bands before and after adjusting, and one question's answers with the key in green). The tab sits after Scan Exams, and a finished scan, exam or practical, opens it on its own outputs folder. The adjusted columns and the second chart series appear only once there is an adjustment, so an unadjusted exam isn't shown everything twice.

A student's marked pages are found by name and ID. Their filenames also carry the sheet's place in the stack, which a version's results rows don't record, so two students whose names and IDs were both unread would share a match.

One layout trap, worth knowing before adding to the tab: a label that sets its own `wraplength` from its own `<Configure>` width changes its size, which sends `<Configure>` again. In the full window that loop ran inside Tk until Python's recursion limit. Wrap to a parent's width or a fixed width instead. `tests/test_results_tab.py` shows every view in a child process with a time limit, which catches a loop that never settles; with the small fixture the old loop settled slowly rather than running away, so the test doesn't reproduce that particular one.

## Phase 3 as built (2026-10-29)

Editing lives in `results_model` as plain functions that save an edit and return the folder opened again (`add`, `delete`, `set_note`, `set_adjustments`), plus builders that turn what the tab knows into an edit (`key_edit`, `credit_edit`, `override_edit`); `results_tab` only reads its entries and calls them. A new edit replaces any earlier one it makes moot (a key change for the same target unless it only also-accepts, an override of the same cell, a point value or adjustment for the same target), so the list holds what is in force rather than every click. An adjustment of 0 removes the earlier one.

Key edits now take `source`, like credit, so a key fix on a matched exam reaches every version. The tab shows keys in the bank's letters, so a source-targeted key edit stores bank letters and `edits._key` puts them into each sheet's letters through `Graded.sheet_letters`, the reverse of `bank_letters`. A version-targeted key edit is translated in the model and stores sheet letters, as phase 1 defined it.

"Edits not yet exported" is a digest of the edit list (notes left out) stored in `edits.json` under `exported`. `outputs.write` records it whenever both files saved and it wrote the listed results, so a scan and a Re-grade count as exports too. File times would have been simpler, but copying a folder changes them. `outputs.write` now returns whether both files saved and wraps each in its own try, because Windows locks a file open in Excel; the Canvas file used to be unguarded.

The tab packs each view's controls from the bottom up and its table last, and each table's scrollbar before the table, so a short or narrow window shrinks the tables rather than hiding buttons. Before this, the answers table's scrollbar was squeezed out at the default size. `tests/test_results_tab.py` checks, at the default size and the window's minimum, that no control is hidden, smaller than it asks to be, or past the window's edge (tables and charts may shrink), and drives one edit of each kind through the tab's own buttons, then Export, and checks the Canvas file.

A folder that opens with nothing now says what it looked for (`results_model.why_empty`): no `app_data`, results files named in `outputs.json` but missing, or none found, and whether a gradebook sits there unused. Choosing the folder that holds `ExamScanner_outputs` opens it.

Not done: written questions' keys stay on Re-grade (the tab has no button that opens the Re-grader yet, which the decisions above allow for); re-marking sheets after a key change is phase 4, and Export warns about it.

## Where it stands (handoff, 2026-10-29)

Phases 1 to 3 are built. User docs: `docs/results.md` (the tab's Help page) and `docs/outputs.md`. Next is phase 4 (re-marking sheets, folders from before phase 1), and a button that opens the Re-grader from Results.

Settled: the folder `~/Desktop/2nd_exam/ExamScanner_outputs` (scanned 2026-10-28) would not open because Brandon had moved its results files out of `app_data/` after the scan, not a scanner bug. The tab now says what it looked for. Don't open or list `marked/` (its filenames are student names) or read any results file into the conversation (FERPA); the folder holding the scans also has student-named PDFs at its top level.

Running Tk in the agent's shell: the sandbox sometimes can't find Tcl, so export `TCL_LIBRARY` and `TK_LIBRARY` pointing at `lib/tcl8.6` and `lib/tk8.6` of the uv-managed Python. Screen capture isn't permitted there, so layout checks go through Tk geometry (widget boxes, canvas text bounding boxes) rather than screenshots.

## Phase 5 plan: reading the tables (2026-10-29)

Four things Brandon asked for after the first real grading run, in the order they were raised.

**Resizable columns that stay resized.** `_tree` sets `stretch=i == 0`, so the first column is the only stretchable one: it absorbs every pixel of slack (hence "much wider than needed" on a wide window), and the drag of a column separator is undone by the next `<Configure>`, because ttk redistributes the slack over the stretchable columns again. The fix is to stretch nothing the user can see: every real column gets `stretch=False` and a fixed `minwidth`, and each table gains a trailing empty column that stretches and takes the slack. Drags then stick, and no column grows on its own.

**The question, not just its number.** The Questions table's first column shows `Q012  stem…`, the stem collapsed to one line and cut to a length the column can plausibly show; it is the widest column and now resizable, and the detail pane still carries the whole stem. Sorting is unchanged: the cell still begins with the label, which is what `_sort` compares.

**Answer text instead of letters.** Two separate things were tangled in the question. *Which letters* these are: the Questions view shows the key and the choice counts in the bank's letters (`Graded.bank_letters`, through the key's `choices`), that is the lettering of the exam file the versions were built from, not what any one sheet printed; the Students view shows one student's sheet as printed, their bubbled letter and that version's key. Both are right for what they are, and each view now says which it is. *The text itself* is not recorded anywhere today: a key row carries `source`, `choices` (each shown choice's bank position) and `text` (the stem), but no choice text. So the key CSV gains a fourteenth column, `options`: the shown choices' text, pipe-separated, in bank order, so position *i* is bank letter *i* and the existing `choices` string maps a sheet letter onto it. `csv.DictReader` keys off the header row, so old keys read as before and simply yield nothing for it. It flows the way `texts` already does: `exam_key_writer` → `keyformat` → the grading record (`grade_functions`) → `outputs.Graded.options` → `Item.options` → the tab. Forward-only, by decision: an exam already built and scanned keeps showing letters, and the tab falls back to them wherever it has no text.

**A student who bubbled the wrong version.** A new edit type, `version`: `version` and `row` (the student, as `override` identifies them, with `student_id` checked) and `to`, the version their sheet actually was. `apply` runs it before every other kind, and it moves the row out of the version that read it into the one named, rescoring each bubble column against that key with `score_answer` and the recorded settings; the row keeps a traceable index (`B3` in version A), so overrides made before the move are followed to it and item analysis, points possible, the gradebook's version sheets and the Canvas file all count the student with the version they really took. A written answer carries the grader's judgment rather than what the student wrote, so it moves as it stands. What this cannot fix: if the two versions' sheets group their rows differently, the bubbles were read against the wrong grid, so the answers themselves are suspect and only a rescan of those sheets will do; the tab says so when it changes a version.

## Phase 5 as built (2026-10-29)

All four as planned, with three things worth recording.

The tables' trailing filler column is what makes a dragged width stick, and it has to be a real column (`FILLER`) in `columns=`, not a zero-width trick: ttk will only leave a width alone when nothing else is asking for the slack. Every visible column also gets a `minwidth`, so a drag cannot collapse one to a sliver that then cannot be grabbed again.

`options` is read through `Graded.labeled`, which answers the question the view is actually asking: render these letters, in the bank's lettering or the sheet's, with the choices' own words where they are known. A written question is the trap, since its cell holds the grader's judgment (`CC`, `CX`) rather than a choice, and `CC` is a perfectly good pair of letters; `labeled` therefore looks at the key row and returns a written answer untouched. `Question.labeled`/`labeled_key` do the same for the Questions view, where everything is already in the bank's letters. `labeled` shows the letter it was given and looks up only the text behind it, which is the point of the whole exercise: on the Students view the letter has to be the one the student bubbled, while the words come from the bank's order through `choices`. The bar chart takes an optional third element per row, the choice's text, cut to 45% of the canvas so the bars keep the rest; the highlight set stays letters, so the key is still marked.

The `version` edit moves the student's row between `Graded` objects, rows named `B3` so nothing collides and an override made before the move can be followed to it (`apply` builds that map and `_override` consults it). The tab had a bug this uncovered: `_load` kept the student selection by version and row, both of which a move changes, so changing a version silently deselected the student. It now keeps them by name and ID (`_who`), falling back to the row only for a student whose ID went unread. The layout test also had to learn that a `CTkOptionMenu`'s dropdown is a popup rather than a control that must fit the window.

Still not done from phase 4: re-marking sheets after a key change, and folders scanned before phase 1. A version change cannot fix bubbles read against the wrong row grid, which needs the aligned images and so belongs with that work; the tab says so instead.

## Points possible per student (2026-10-30)

`Graded.points_possible()` summed the whole key, which is right for an exam everyone answers in full and wrong for a lab practical: one key carries every letter at every station, a student answers the two their form holds, so every practical percent was roughly halved and the Canvas `Points Possible` row was double what anyone could earn. It takes an optional `row` now and sums only the questions that student was asked (`asked`, the same test the earned side already used, which is why a dropped question leaves its own sheet's total and no one else's). `student_possibles()` is the set of those sums, and `outputs.all_possible` the set across versions, standing in with the key's total for a version nobody sat.

What a single number still has to mean: the Canvas file and the `Canvas scores` tab take the largest, as they did when versions differed. On the Results tab a summary column's `possible` is `None` whenever the students in it are not all out of the same total, which the tab already renders as "varies" with the percents dropped, so a practical with even forms reads as one total and an uneven one says varies.

The Excel side is formula-driven over per-version constants, so the figures could not simply follow a Python value. A gradebook tab gets a **Possible** column after **Adjusted**, written only when that version's students differ (`varies` in `_version_sheet`), and `TotalRange.poss_col` points at it; the grade distribution's `COUNTIFS` against a constant becomes `SUMPRODUCT` over that column, and `one_possible` decides per group whether a single total exists for the Points possible row and the percent rows. An ordinary exam's workbook is unchanged, column for column.

`asked` now answers False for a column the results file does not carry at all, rather than raising, since `possible` can name a column a later edit added.
