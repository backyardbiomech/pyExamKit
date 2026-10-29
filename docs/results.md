# The Results tab

The **Results** tab is where a scan's grades are checked and corrected before they go to Canvas: the class's statistics, each question's item analysis, each student's answers, and every change you make to them. A scan opens it on its own outputs folder when it finishes. To open an earlier scan, click **Choose…** and pick its `ExamScanner_outputs` folder (the folder holding it works too).

The tab reads the scan's results files in `app_data/`, never the gradebook. It is the source of truth: your changes are kept by the app and written into `gradebook.xlsx` and `canvas_upload.csv` when you export, overwriting both. Changes typed into the gradebook in Excel are never read back, so once you start adjusting in Excel, finish there.

## The four views

**Summary** shows the Exam stats figures ([Outputs](outputs.md#the-results) defines each one): the number of students, points possible, mean, median, standard deviation, highest and lowest score, and Cronbach's alpha, for the whole class and, with several versions, for each version. Once points have been added, each column has an **Adjusted** column beside it. The chart counts students in each letter grade, unadjusted in gray behind adjusted in blue.

**Questions** lists every question with where it sat on each version's sheet (`A3, B17`), its key, its points, the number of students who answered it, its mean score, its discrimination, and Canvas's discrimination index. Questions with a discrimination below 0.2 are shaded. Click a column heading to sort by it. Selecting a question shows its text and how many students chose each answer, with the key's bars in green; a wrong answer that drew more students than the key is the thing to look for. With keys made by Build Exam, the versions are matched by bank question, so each question is listed once, in the bank's letters.

**Students** lists every student with their version, total, and adjusted total. Selecting one shows their answer, the key, and their points on each question, and **Open marked sheet** opens their marked page.

**Edits** lists every change made to these results, in the order they apply, each with its note and when it was made.

## Correcting the grades

Every change is saved to `app_data/edits.json` the moment you make it, and every view is recalculated at once. Each change can carry a note (*"Q12 stem was ambiguous"*), which appears on the Edits view; the note field sits beside the buttons that make the change.

**Points added** (Summary) adds points to every student's total, for a curve or a question thrown out after the fact. Type them in the **Points added** row under **All students** and, with several versions, under any version that came out harder, then click **Apply points added** or press Return. A student gets the class's amount plus their version's. A negative number takes points away, and adjusted scores are not capped at the points possible. Set an amount back to 0 to remove it.

**Question actions** (Questions) act on the selected question. When the versions were matched by bank question, each action reaches every version that printed it, and the key is typed in the bank's letters, as the view shows it.

- **Change key** grades the question against the key you type instead of its own. Type alternatives separated by commas (`C, D`) to accept any of them, and a select-all answer as its letters together (`AC`).
- **Also accept** keeps the question's key and accepts another answer too, for a distractor that turned out to be defensible.
- **Set points** changes what the question is worth. Partial credit is scaled to the new value.
- **Full credit to everyone** gives every student who had the question its full points, and leaves the points possible as they were.
- **Drop question** takes the question out of every total and out of the points possible. It disappears from the Questions view; delete the edit to bring it back.

A written question's acceptable answers are changed on the [Re-grade](open-ended-questions.md#re-grading-afterward) tab, so **Change key** and **Also accept** are off for it; the credit actions work as for any question.

**One student's points** (Students), for a regrade request: select the student, then the question in their answers, type the points, and click **Set**. Points set this way are marked with `*`, and **Clear** returns the question to its graded score. They hold even when the key changes afterward, and the tab points this out when you change a key on a question that has some.

**Undoing a change**: select it on the Edits view and click **Delete edit**. The results are recalculated as if it had never been made. **Save note** changes its note. A change made again replaces the earlier one (a second key change, new points for the same student and question, a new amount added), so the list holds what is in force. A change that no longer matches anything in the results, such as one made for a version that a later scan did not have, is shaded.

The changes apply in a fixed order whatever order they were made in: key changes, then credit (full credit, drop, points), then points set by hand, then points added.

## Exporting

**Export** rewrites `gradebook.xlsx` and `canvas_upload.csv` with every change in. The line under the folder says whether there are changes not yet exported. Changing a note does not count as a change.

In the gradebook, key changes, credit and points set by hand are in each points cell and so in every total; the points added fill the yellow **Points added** row on Exam stats, so the workbook still shows unadjusted beside adjusted. `canvas_upload.csv` carries the final scores, everything included, and uploads as is.

Export fails for a file that is open in Excel on Windows, which locks it. Close the file and export again; the log names the file that could not be saved.

The marked sheets (`marked/` and `marked.pdf`) are not redrawn: after a key change or a dropped question they still show the original key and points, and Export reminds you of this.

A new scan into the same folder starts over: the earlier changes were made to different sheets, so they are set aside as `app_data/edits_replaced_<time>.json` rather than applied. The Re-grade tab keeps them, since it rebuilds the gradebook and Canvas file with every change in.

## When a folder will not open

The tab needs the results files a scan writes into `app_data/`: `results.csv`, or one `results_versionA.csv`, `results_versionB.csv` and so on per version, each with its `_points.csv` and `_grading.json`. When they are missing it says what it looked for and what it found instead. A folder that still has `marked/` and `ALERT.txt` but nothing in `app_data/` except `aligned/` and `scanJPGs/` has lost its results files after the scan, since a scan writes them before it marks a single sheet; scanning the stack again recreates them.

Folders scanned before the app had a Results tab do not record how they were graded (select-all partial credit, strictness, and the default points for a bubble and a written question). They open with a note, and a key change on them rescores with the Scan tab's default settings.

---

Previous: [Outputs](outputs.md) · Next: [Lab practicals](lab-practicals.md)
