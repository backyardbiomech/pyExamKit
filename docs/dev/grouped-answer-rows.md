# Grouped answer rows: gaps that follow the exam

*Plan written 2026-09-25.*

The v2 sheet puts a gap after every fifth row so students keep their place. An ordering, matching, or multiple-dropdown question takes one row per item (two to six, more for a long dropdown question), and those rows belong together; a fixed gap can split one question across two groups, or even across two columns (a 4-item question starting at row 29). The instructor asked for such a question's rows to stay together and be set off from their neighbors, with one answer sheet still serving every version.

## Decision

Built exams get gaps where the exam needs them, and the scanner learns their positions from the key file. Padding the fixed grid with blank rows was the alternative; it needed no scanner change but wasted up to four rows per question and made the exam skip numbers. The instructor chose movable gaps because key files are becoming the default way to grade. The costs accepted with it: a sheet with moved gaps works only with its own key file (no scanning a key sheet, no generic stock), and a wrong key on such a sheet misreads bubbles rather than only misgrading them.

The standard sheet does not change. Plain sheets from **Make Answer Sheet…**, the stock PDFs, the classic sheets, and building a key by scanning all keep working exactly as now, and a built exam with no grouped questions still prints the standard sheet (layout code 1), so nothing in that path learns anything new.

## Row runs

A sheet column becomes a stack of *runs*: consecutive rows with a gap before and after. The builder derives them from the question list. Each OR, MT, or MD question with two or more rows is its own run of one row per item, however many items it has, so a 6-item ordering question is one unbroken run of six. Other questions (MC, MA, SA, the version question) between two grouped ones split into runs of at most five, as even as possible: seven become 4 and 3, not 5 and 2. The first build used plain fives, and the rendered sheet showed why not; a single leftover row between gaps looked like a grouped question of its own. After the last grouped question the others fall in fives. With no grouped questions this reproduces the standard grid exactly, which is how the builder knows to print the standard sheet.

Runs are packed into the five columns in order, never split across a column. The page height fixes a column's budget: the standard column is 30 rows and 5 gaps, and a gap is half a row, so a column holds any mix with 2 × rows + gaps ≤ 65. An exam with many short grouped questions therefore fits fewer than 30 rows in some columns. If the runs need more than five columns, the build warns as it does today for more than 150 rows. A single run longer than 32 rows (the most a column holds with no gaps) cannot be printed and is an error.

The geometry is defined once, in `sheet_layout.py`: a function takes the column-by-column run sizes and returns a `Layout`. The sheet generator draws from it and the scanner reads from it, as with every other layout. The key stores the run sizes column by column (a metadata row such as `5,5,3,5,5,5/4,5,5`) rather than coordinates, and stores the packing explicitly rather than recomputing it, so a later change to the packing rule cannot misread an old key.

## Layout code

Code 2 means "v2 sheet, rows from the key." The header (ID, version row, guide) is identical to code 1; only the question grid differs. The scanner, on finding code 2, takes the grid from the loaded key. With no key file, or a key without run sizes, it stops with a message saying the sheet was printed for a specific exam and needs its key file. A code-1 sheet graded against a key with run sizes reads correctly, since row numbers are the same; only the positions differ, and a code-1 sheet uses its own.

## One sheet for every version

Where the gaps fall depends on where the grouped questions land, so with shared questions they are pinned the way short-answer questions already are: version A shuffles freely, and every other version keeps each SA, OR, MT, and MD question at A's position and shuffles only the questions between them. Each stretch then holds the same questions in every version, so the runs are identical and one sheet serves all versions. Within a grouped question the items still shuffle per version, so a neighbor's bubbles for it do not match.

When versions draw different questions, each gets its own sheet and key ("Form A" in the margin), as now. The scanner then needs each student's version before it can read the grid; the version row sits in the header at the same place on every sheet, so it reads the version first and then the grid from that version's key. A student whose version cannot be read is asked about as now, and the sheet is read again once a version is chosen.

## Where the standard sheet lives in the app

The instructor asked that the standard-sheet path (a generic sheet, and a key built by scanning a filled sheet) stay available, perhaps on its own tab. The Build Key tab already holds key-by-scanning, so **Make Answer Sheet…** moves there from Build Exam, and the tab is renamed **Standard Sheet** with a line explaining when to use it rather than Build Exam. The Scan Exams tab still accepts a scanned key as the first page when no key file is loaded.

## Order of work

1. `sheet_layout`: run packing, the keyed layout, code 2, and detection.
2. Builder: pin grouped questions; derive runs; carry them through `answer_rows`, the key writer, and `keyformat` (CSV and JSON).
3. Sheet generator: draw from runs; place writing boxes after the columns the runs use; print code 2 only when the runs differ from standard.
4. Scanner: substitute the key's grid on code-2 sheets, single and multi-version, with the error for a missing key.
5. GUI: move **Make Answer Sheet…** and rename the tab.
6. Tests (runs, packing, key round trip, a generated code-2 sheet read back through the reader, pinning across versions) and the user docs (`answer-sheets.md`, `building-exams.md`, `scanning-and-grading.md`).

## Status (2026-09-25)

Built as planned. Checked end to end on synthetic sheets: a built exam with a 6-item ordering question, a matching question, and three short-answer questions printed one grouped sheet for two versions; two filled copies scanned through `Scanner` against the built key scored 26 of 26 and 0, and the scan stopped with the missing-key message when run without the key file. Tk now starts in this environment, and the Standard Sheet tab and the **Make Answer Sheet…** dialog build without errors, but neither has been looked at on screen.

## Open

Look at the Standard Sheet tab in the running app, and print one grouped sheet and scan it on the real scanner before an exam depends on it. A code-2 sheet scanned with another exam's key is not detected; the layout code has no room to identify the exam.
