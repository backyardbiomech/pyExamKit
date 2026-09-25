# Answer sheets

Students bubble their answers on a printed answer sheet, not on the exam pages. There are three ways to get one.

**Build the exam here.** [Build Exam](building-exams.md) writes an answer sheet with every exam, sized to it, with a writing box for each short-answer question and the rows of each ordering, matching, and dropdown question kept together (see below). This is the easiest route.

**Print a standard sheet.** The `images/` folder holds blank sheets in 30, 60, 90, 120, and 150 question sizes, named `AnswerSheet 60 questions.pdf` and so on. It will only scan what the key tells it to scan, so a 50-question exam can use the 60 sheet or the 150 sheet.

**Make one to order.** On the **Standard Sheet** tab, **Make Answer Sheet…** asks for the number of questions, which questions are answered in writing, and an optional heading such as "BIOL 206 Exam 2", then saves the PDF.

Every sheet gives six choices per question, **A through F**, and holds at most 150 questions. Those two numbers are properties of the paper and they set the hard limits described in [Question bank format](question-bank-format.md).

## What is on the sheet

From the top: the logo and a line for the student's printed name; a picture of how to fill a bubble, with one right way and six wrong ones; the student ID, written in boxes and bubbled one digit per column; the exam version, bubbled A to F; then the answers, in columns of 30 with a gap every five rows so students keep their place. A sheet built with an exam that has ordering, matching, or dropdown questions moves the gaps to fit the exam (see below).

There are no name bubbles. Names come from a [class roster](roster.md) matched to the bubbled ID, and the printed name is there for a person to read when the ID does not match.

## Written answers on the sheet

A question answered in writing (a short-answer `SA` question, or any row you choose in **Make Answer Sheet…**) keeps its number in the grid, but its bubbles are replaced by an arrow pointing to a numbered writing box in the space to the right. The boxes use the columns the exam does not need, so a sheet with written questions holds at most 90 answer rows. It fits 7 boxes, or 14 when the exam has 30 or fewer answer rows.

When the exam is built here, the key records where each box is, so at scan time the handwriting is cropped from the right place without drawing anything. With a sheet from **Make Answer Sheet…**, list the written questions under **Question numbers to ignore** when you scan, and draw each box when the scanner asks.

When every version uses the same questions, the builder keeps each short-answer question on the same row in every version, so one sheet serves them all. When versions draw different questions, that cannot be arranged, and each version gets its own sheet, since the box has to be where that version's key expects it. Each is marked "Form A" and so on in small print in the bottom margin, where a neighbor will not notice it; hand each version out with its matching sheet.

## Rows grouped by question

An ordering, matching, or multiple dropdown question takes one row per item, and on a standard sheet those rows can be split by a gap or even run into the next column. On a sheet built with the exam, each such question's rows sit together with a gap before and after, however many items it has; the other questions fall in groups of up to five between them. With many short grouped questions a column holds fewer than 30 rows, since each gap takes the room of half a row.

Such a sheet can only be read with **the key file built with it**, because the key is what tells the scanner where the rows are. A scan loaded without a key file, or with a key sheet as its first page, stops with a message saying so. The question numbers are the same as on a standard sheet, so if you run short of printed copies, a standard sheet of the right size can stand in, graded with the same key.

When every version uses the same questions, the builder keeps each grouped question on the same rows in every version, as it does for short-answer questions, so one sheet serves them all.

## What the scanner depends on

The scanner locates everything on the page by geometry. It finds the **three large black circles** in the corners, uses them to correct for skew and scale, and then reads bubbles at fixed positions relative to them. The **small black squares** at the bottom left tell it which sheet design it is reading, including whether its rows are grouped by question, in which case the positions come from the key. Students must not write on the circles or the squares.

So the rule for modifying a printed sheet is: **you may cover things up, but you may not move anything, and you cannot add bubbles where none exist.** Anything else on the page is fair game, as long as the marks do not touch the circles, the squares, or the bubbles for questions that are actually being graded.

## Older sheets

The earlier sheets, with the Honor Pledge header and name bubbles, are still in `images/` as `pyExamScan AnswerSheet 60questions.pdf` and so on, and still scan. The scanner tells the two designs apart on each page, so a stack can mix them. On an older sheet, the bubbled name is used when no roster is loaded or the ID is not on it. An older sheet has no version bubbles, so for a multi-version exam on older sheets, give the version question number when you scan.

## Common modifications

**Reusing bubble rows for hand-graded work.** Say you have 20 multiple choice questions and a drawing worth up to 10 points. Leave questions 21 through 30 on the sheet and make them all 'A' on your key. Grade the drawings by hand, then fill in one 'A' per point earned; a dry erase marker or a wide Sharpie makes this fast, and you are allowed to color outside the bubble. Six points means six A's; leave the rest blank. Scan the stack and let the software do the arithmetic. A rubric can make each row mean something specific: 21 for labeling the x-axis, 22 for the y-axis, 23 for the first curve, and so on.

**Making room for a longer written answer.** The open box on a standard sheet with fewer than 150 questions can hold a question and a blank pasted in by hand. For the scanner to grade it, **every student's answer for a given question must be in the same place on the page**, since the crop region is defined once and applied to every sheet.

## Designing an answer blank for good transcription

Handwriting is transcribed by a cloud model (see [Open-ended questions](open-ended-questions.md)), and the crop it is handed is only as clean as the page. The generated writing boxes follow these rules already; they matter when you lay out a blank by hand.

Use a **single horizontal underline** rather than a full rectangle, since vertical box borders may get read as parentheses, or use a box to make sure students keep their answer inside it. Print the line in **light gray** rather than black. Make the blank **at least 6 to 8 cm wide**, so students write legibly and the whole word lands inside the crop. Put any printed label such as "Final Answer:" **above** the line rather than beside it, which leaves a crop region containing nothing but handwriting. And when you draw that crop during grading setup, **crop tightly**: exclude the printed line and the label. Less extraneous ink is a better transcription.

---

Previous: [Importing a Canvas quiz](importing-canvas-quizzes.md) · Next: [Building a key](building-keys.md)
