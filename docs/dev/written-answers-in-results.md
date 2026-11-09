# Written answers in the Results tab

Planned 2026-11-09. The Re-grade tab predates Results and overwrites the results files, so its changes could not be undone, reached one version at a time, and rewrote the gradebook on the spot. This moves it into Results as a kind of edit.

## Decisions (Brandon, 2026-11-09)

- Accepting a written answer is an edit in `edits.json`, like every other change on the tab.
- Undo is allowed: deleting the edit reverses it, which ends the old promise that re-grading never lowers a grade.
- Removing an answer that came with the key lowers grades (revised after trying it the same day): it was a key error, so a student who wrote exactly that answer earns nothing for it, instead of keeping the credit beside a classmate graded wrong for the same words. Moving a full-credit answer to partial gives those students half, by the same reasoning. Removing an answer added on the tab is an undo, and returns its students to the grades they had.
- A question is shown once across the versions that printed it, with one combined answer list; a change reaches every one of those versions.
- The Re-grade tab, `RegradeDialog`, and support for folders from before `app_data/` are removed.

## The edit

A new type, `written`: the usual question target (`source`, or `version` and `question`), `answer`, and `grade`, one of `full`, `partial` or `remove`. One edit per answer, so the Edits view reads as a list of accepted answers and each can be undone alone. A new edit for the same answer on the same question replaces the earlier one.

`written` applies first, before `version`: transcriptions are keyed by the row the scanner read, and a version edit renames that row. For each target, `edits._written` updates the answer lists held on `Graded` and then upgrades every student whose saved transcription is exactly that answer (capitals and spacing aside). A `remove` sets those students to no credit, and `partial` on an answer the key gave full credit sets them to half. Only an exact reading is touched: a misspelling the grader credited by eye may have been judged on its own merits, and nothing records which answer it was compared with.

An edit judges students only against its own answer, not the whole list as `RegradeDialog` did. That list can include answers the grader saw and marked wrong, for instance where the AI's reading was right for the key but wrong for the handwriting, and rerunning it overrode that judgment.

Upgrades land in the `g.df` cell as `CC: text` and are scored by the existing `_rescore`. Key changes do not touch written questions; credit and overrides apply afterward as they do for any question, so a point set by hand still stands.

## Changes by file

- `grade_functions.py`: `upgraded_cell`, the upgrade-only rule on its own. `regrade_open_questions` goes.
- `outputs.py`: `Graded` carries `open_partial` and `transcriptions`, read in `load`. The `csvs` argument of `write`, used only for old folders, goes.
- `edits.py`: the `written` type and `_written`.
- `results_model.py`: `written_edit`, `written_keys`, `remove_written`, `written_rows`, `upgrades`, the `written` line in `describe`. `add` and `delete` write the answer lists through to a lab practical's source file, as Re-grade did (the `key_file` in the grade config).
- `results_tab.py`: a **Written** view, listed only when the exam has written questions: the questions and each student's reading on the left; the full and partial lists, an entry, Add and Remove on the right. Selecting a reading fills the entry. A button on Questions jumps to the view for the selected written question. Export's reminder about marked sheets covers written edits.
- `gui.py`, `help_links.py`, `openQ.py`: the tab, its callbacks, its help entry, and `RegradeDialog` go.
- Tests: `tests/test_written_edits.py` for the edit and the model; the tab's layout test covers the view with written questions present; the old `regrade_open_questions` test and the config test go.
- Docs: `results.md`, `outputs.md`, `open-ended-questions.md`, `scanning-and-grading.md`, `lab-practicals.md`, `faq.md`, `README.md`, `demo/video-outline.md`.

## Not done

Marked sheets are not redrawn after a written upgrade (as with Re-grade, and as with key changes on Results; Export reminds the instructor). The Loom video for written answers shows the old tab and has to be recorded again.

## As built (2026-11-09)

As planned. Writing through to a practical's source file rebuilds its answer lists from the scan's plus the edits, which is what `RegradeDialog` did, so answers typed into the file by hand since the scan are overwritten when a written edit is made or deleted.

Going through `edits.apply` rather than `gradeResults` also ended three faults of the old path: `gradeResults` was called without the scan's strictness, so a re-grade rescored select-all questions at 0.5 and saved 0.5 as the setting; a gradebook locked by Excel was reported as done; and each re-grade appended the no-answer lines to `ALERT.txt` again.

Left alone: `_openq_gradeconfig.json` still records `bubbleVal`, `openVal`, `selectAll` and `point_values`, which only `RegradeDialog` read; `key_file` is the one entry still used. A `version` edit carries a column only when both versions have it, and shuffled versions number their written questions differently, so a student moved between such versions loses their written answer from the totals. That limit predates this work and belongs with `_version` in `edits.py`.
