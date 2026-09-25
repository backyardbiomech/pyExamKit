# Class rosters

A class roster lets the scanner put each student's name on their results by looking up the ID they bubbled. The new answer sheets have no name bubbles, so this is how names reach the results for them; on the older sheets, a roster also corrects names that were bubbled wrong. It is optional. Without one, results from the new sheets carry the ID alone.

The roster is a CSV file (a spreadsheet saved as comma-separated text). The app reads it on your computer and nowhere else; it is never sent to the handwriting transcription service. Keep it wherever you keep other files with student names, not in a shared folder.

## Option 1: export the gradebook from Canvas

This needs no editing. In your Canvas course, open **Grades**, click **Export**, and choose **Export Entire Gradebook**. Canvas downloads a CSV file. Load that file as it is.

The app takes names from the **Student** column (Canvas writes it "Last, First") and IDs from the **SIS User ID** column. The first row below the header in a Canvas export holds points possible rather than a student, and Canvas adds a "Student, Test" row; both are skipped automatically because they have no ID.

Before you rely on it, open the file once and check that the **SIS User ID** column holds Longwood L numbers. If it holds something else, make your own file as in option 2.

## Option 2: make your own in Excel

Make a sheet with a header row and three columns:

| LastName | FirstName | ID |
|---|---|---|
| Doe | Jon | L12345678 |
| Roe | Ann | L87654321 |

Then choose **File → Save As**, and pick **CSV UTF-8 (Comma delimited)** as the format.

The column names can vary: "Last Name", "last", or "Surname" all work, as do "Student ID", "L Number", or "ID". The order of the columns does not matter. IDs can be written with or without the L. If Excel strips an ID's leading zeros (showing `123456` for `00123456`), that is fine; the app puts them back.

One name column also works in place of two, as long as it is headed **Student** or **Name** and written "Last, First".

## Loading it

On the **Scan Exams** tab, click **Load Class Roster…** and choose the file. When the scan starts, the log reports how many students it read and which columns it used, for example:

```
[Roster] 32 students; IDs from the "SIS User ID" column, names from "Student"; 2 row(s) without an ID skipped
```

If the file cannot be used, the log says why in the same place, and the scan carries on without names.

## What gets reported

Every sheet whose ID matches the roster exactly gets that student's name. The rest are listed in `ALERT.txt` with a line beginning `ROSTER`:

- **One digit off.** If the bubbled ID differs from exactly one roster ID by a single digit, or has one column left blank, the scanner uses that student and reports the correction so you can confirm it.
- **Not on the roster.** The results keep the bubbled ID with no name. Look at the handwritten name at the top of that student's marked sheet.
- **Two sheets, one ID.** Usually one student bubbled another's ID by one digit. Check both marked sheets.

The scan number in each line is the sheet's position in the stack.

---

Previous: [Scanning and grading](scanning-and-grading.md) · Next: [Open-ended questions](open-ended-questions.md)
