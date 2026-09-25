# Outputs cleanup

Started and shipped 2026-09-25. A scan used to leave four gradebook-like files at the top of `ExamScanner_outputs/` (`results.csv`, `resultsperquestions.csv`, `resultsforCanvas.csv`, `results_gradebook.xlsx`), multiplied per version on a multi-version exam, plus `results_all_versions_forCanvas.csv`. The top level now holds what a person uses; the app's working files move to `app_data/`.

## Decisions (Brandon, 2026-09-25)

- Top level: `gradebook.xlsx`, `canvas_upload.csv`, `ALERT.txt`, `marked/`, `marked.pdf` (and `exam_key.csv` in scan-a-key mode, which is reusable). One of each regardless of the number of versions.
- `results*.csv` and the points-per-question CSVs move to `app_data/`. Re-grade takes the outputs folder and finds them there; it still accepts an old-layout `results.csv`.
- `gradebook.xlsx` on a multi-version exam: one tab per version, numbered as that version's sheet (so a regrade dispute matches the marked sheet), then a **By question** tab and an **Item analysis** tab.
- Canvas file: header `Student, SIS User ID, <exam name>`, a second row `Points Possible, , <total>`, then `Last, First`, prefixed ID, score. No index column. The ID prefix is a setting on the Scan tab, default `L`.
- Exam name: the title Build Exam writes into the key; older keys fall back to the name of the folder holding the scans.

## Question identity across versions

Keys did not record which bank question sat at each position, so versions could not be combined per question. Build Exam now writes two more key columns:

- `source`: the bank file and block number, `bank.md#12`; a question spread over several rows (MD, OR, MT) adds the part, `bank.md#12.3`. For MT the part is the left item's position in the bank, since lefts are shuffled.
- `choices`: the bank position of each displayed choice, as letters: `CADB` means the sheet's A is the bank's C. Answers are mapped back through this, so choice counts add up across versions.

Keys without these columns still grade. A multi-version stack graded with them gets no By question tab, and its item analysis is per version.

## Item analysis

Per question: key, points, number of students, mean fraction of points earned (difficulty), discrimination, and a count per choice in bank letters. Discrimination is the corrected item-total correlation: Pearson r between the item's score and the student's total minus that item. Questions a student was not given (a practical form, a different random sample) are left out of that question's statistics.

## Code

- `outputs.py` owns the output layout and writes `gradebook.xlsx` and `canvas_upload.csv` from every graded results file listed in `app_data/outputs.json`.
- `gradeResults` grades one results file and writes its points file and `{stem}_grading.json` (points possible per question, plus the key's title, sources and choices, kept across re-grades). It no longer writes the xlsx or Canvas file.
- Scanner flows and Re-grade call `outputs.write(outdir)` after grading.
