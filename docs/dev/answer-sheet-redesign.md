# Answer sheet redesign and adaptive bubble reading

*Plan written 2026-09-24, after the first week of heavy use in Fall 2026.*

Faculty feedback from that week raised three problems. Students did not know how to fill a bubble. The Honor Pledge header gave no clean record of whose sheet it was when the name bubbles went wrong. And students who shade lightly lost marks, because a single darkness threshold cannot separate a faint real mark from a heavy erasure. This plan covers all three, in the order they are built.

## Decisions already made

The name bubbles are dropped from the new sheet. The student ID is what joins a sheet to Canvas, so names come from a class roster CSV looked up by ID, and a printed "Name" line gives a human-readable fallback on the marked sheet. The roster is optional, and it has to be loadable by faculty who do not use Python, so its format and the steps to export it from Canvas are documented for them rather than for developers.

The Honor Pledge is cut. The header carries a logo (a file the user supplies), the name line, and a picture of how to fill a bubble correctly and five ways not to.

Printed stock of the current ("classic") sheet stays usable, and past scans can still be regraded. The three registration circles keep their exact positions on the new sheet, so alignment is shared, and a small printed code tells the scanner which layout it is reading.

## Phase 1: measure before tuning

The test scans in `tests/` are filled with marker, so they cannot tell us where a faint pencil mark or an erasure falls. `tools/bubble_stats.py` reads a stack of real scans and writes one row per question bubble: scan number, question, letter, and measured darkness. It writes nothing from the ID or name grids, since their darkness pattern *is* the ID or name, and it writes no images. The user runs it on this week's stacks; the cutoffs in phase 2 are then set from the measured distributions rather than guessed.

## Phase 2: adaptive reading (works on classic sheets)

Today `autothresh` binarizes the whole page at 75% of the paper brightness measured from four calibration bubbles, and `scanDots` then looks for connected blobs. The replacement, in `bubbles.py`, measures each bubble directly.

1. **Fill score per bubble.** The mean gray level inside a disk slightly smaller than the printed ring, converted to darkness relative to the page's paper level. The printed letter inside each bubble adds a little ink, so the score subtracts a per-letter baseline: a low percentile of that letter's darkness down the sheet, where almost every bubble is empty.
2. **The student's own fill level.** The median, over answered rows, of the darkest bubble in the row. A light shader gets a low reference and a heavy shader a high one.
3. **Decision.** A bubble counts as filled when it reaches a fraction (default 0.5) of the student's fill level, clears an absolute floor so smudges on a mostly blank sheet do not count, and is at least half as dark as the darkest bubble in its own row. The row rule is what removes a heavy erasure beside a fresh mark.
4. **Review flags instead of silent guesses.** A bubble close to the cutoff, or one dropped by the row rule while above the cutoff, is written to `ALERT.txt` and drawn as a blue `?` on the marked sheet.

The ID and version grids use the same scores with a one-per-column rule: the darkest bubble wins if it passes the cutoff, and a close second is flagged.

The GUI's "Fill threshold" slider becomes the fraction in step 3. Its old meaning (a fraction of paper brightness) no longer exists, so the label and the docs change with it.

## Phase 3: the generated sheet

The layout moves out of Illustrator and into `sheet_layout.py`, which defines every bubble center once. The scanner reads coordinates from it and `answer_sheet.py` draws the PDF from it with PyMuPDF, so the two cannot drift apart. The classic sheet is described in the same module with its existing coordinates.

The new sheet, top to bottom: logo and "Name (print)" line; a bubbling guide (one correct example, five incorrect); a version row (A to D) so the version no longer consumes a question; the ID block with one write-in box per digit directly above its bubble column; then five columns of 30 questions with a gap every five rows to prevent row-shift errors. Bubble outlines and letters print in lighter gray so a faint fill stands out. Sheets with fewer than 150 questions keep the same bubble positions and turn the unused columns into a written-answer box, so a single layout code covers every size.

The layout code is four small squares on the bottom margin between the lower registration circles, a spot that is blank on the classic sheet. All white reads as classic.

## Roster matching

`roster.py` loads either a plain three-column CSV (last name, first name, ID) or a Canvas gradebook export as downloaded, finding the ID column by header name or, failing that, by which column's values look like IDs. After scanning, each sheet's ID is matched exactly; failing that, a roster ID one digit away (unique) is accepted and flagged. Unmatched IDs and IDs appearing on two sheets are flagged. On a classic sheet, the bubbled name is used when no roster match exists. The roster is read only by the local app and never sent to a model.

## Order of work

1. Phase 1 diagnostic script, committed, so the user can run it on real stacks.
2. Phase 2 reader, replacing `autothresh`/`scanDots`, with provisional cutoffs.
3. Layout module and classic definition; scanner reads geometry from it.
4. Sheet generator and the new layout, with layout-code detection.
5. Roster loading, matching, GUI field, and the user-facing roster guide.
6. Tune cutoffs once the user has run phase 1 on real scans.

## Additions made during the build

**Written-answer boxes from the exam.** Build Exam knows which answer rows are short-answer (`SA`) questions, so it now writes the answer sheet itself. Those rows show a dashed arrow in place of bubbles, pointing to a numbered writing box in the columns the exam does not use, and the key records each box as that question's crop region, which removes the hand-drawing step at scan time. The arrow's shaft is broken at every bubble position so that nothing prints inside a measured disk; an earlier solid arrow read as bubble F. Boxes need free columns, so they fit only on exams of 90 or fewer rows (7 boxes, or 14 at 30 rows or fewer). A row cannot hold a box inline, because every bubble must stay where the layout says it is, with no per-exam geometry for the scanner to learn. Per-version sheets would have to reach the right students, so with shared questions the builder avoids them: version A shuffles freely, and every other version pins each short-answer question at version A's position and shuffles only within the stretches between them. Each stretch holds the same questions in every version, so it spans the same number of rows even with multi-row ordering, matching, and dropdown questions, and the short-answer rows agree. Pre-filling the version bubble on per-version sheets was rejected: a student holding packet B and sheet A would be graded against key A without any warning. Versions that draw different questions still get per-version sheets, marked "Form A" in small print in the bottom margin.

**The version letter is hidden.** Students could read a neighbor's version off the exam header or the page footer. The letter now appears only at the end of the exam, with a line telling the student which header bubble to fill, and it is gone from the page title too, which browsers print when headers are left on.

**The version row runs A to F**, matching the six versions the builder can make.

## Tuning from a real stack (2026-09-25)

`tools/bubble_stats.py` was run on 69 pencil sheets of a 48-question exam, 19,872 bubbles. Scored against each student's own fill level, the bubbles are cleanly bimodal: 16,545 fall under 0.35 of it, 3,321 at 0.55 or above (up to 1.87), and only 6 between. At the final settings the reader takes 3,325 answers from the stack. Sheet fill levels ranged from 0.17 to 0.48 (median 0.40).

Erasures sit beside a fresh mark at 18 to 46% of its darkness; the 17 rows with two genuine marks, all on five select-all questions, run 67% and up. So the row rule at 50% separates them with room on both sides, and it is what protects heavy erasures at every cutoff tried. The erasure-heavy sheet in the stack (scan 36, a student who changed many answers) had five erasures within 25% of the cutoff, every one beside a darker mark.

The first run (cutoff 0.50, floor 0.08) missed two lone light marks, on the two lightest sheets. Any cutoff from 0.30 to 0.45 with a floor of 0.05 to 0.06 recovered exactly those two and changed nothing else. 0.35 was chosen because it centers the line on the lightest sheet (scan 23, fill level 0.17), whose darkest empty bubble was 0.050 and lightest answer 0.072; the instructor independently reported that sheet as very light, with ID and name marks the old reader could not see. The floor of 0.06 sits above that sheet's darkest empty.

The first run also flagged 22 bubbles, 20 of them lone marks correctly read as filled. Flags now go only to calls that could go either way: a lone light mark just under the cutoff, read as blank, and a mark near half the darkness of its row's darkest. Replayed on the stack, that is 2 flags, both erasures at 40 to 46% of the mark beside them. Sheets with a fill level under 0.25 (3 of 69) are reported for a look by eye.

The stack held no ID or name data (the tool writes neither), so ID reading at these settings was not measured; it uses the same cutoff, per student.

## Status

All phases are built and the cutoffs are set from the stack above.
