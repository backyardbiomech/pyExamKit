# Answer sheets

Students bubble their answers on a printed answer sheet, not on the exam pages. The `images/` folder in the repository holds ready-made PDFs in 30, 60, 90, 120, and 150 question sizes, plus the Adobe Illustrator source file if you want to make a new one from scratch.

Every sheet gives six choices per question, **A through F**, and the largest holds 150 questions. Those two numbers are properties of the paper and they set the hard limits described in [Question bank format](question-bank-format.md).

## What the scanner depends on

The scanner locates everything on the page by geometry. It finds the **three large black registration circles**, uses them to correct for skew and scale, and then reads bubbles at fixed coordinates relative to those marks. It also reads **four 'B' bubbles around the outside** to calibrate how dark a filled bubble is on this particular scan.

So the rule for modifying a sheet is: **you may cover things up, but you may not move anything, and you cannot add bubbles where none exist.** All of the modifications below can be done in an ordinary PDF editor; Illustrator is only needed for a redesign.

Anything else on the page is fair game. You or the students can write anywhere, as long as the marks do not touch the three registration circles, the four outer 'B' bubbles, or the bubbles for questions that are actually being graded.

## Common modifications

**Using a shorter exam than the sheet.** For a 50-question exam, print the 60-question sheet and cover questions 51 through 60 with a white box. Leave the outlined box on the right alone.

**Reusing bubble rows for hand-graded work.** Say you have 20 multiple choice questions and a drawing worth up to 10 points. Leave questions 21 through 30 on the sheet and make them all 'A' on your key. Grade the drawings by hand, then fill in one 'A' per point earned — a dry erase marker or a wide Sharpie makes this fast, and you are allowed to color outside the bubble. Six points means six A's; leave the rest blank. Scan the stack and let the software do the arithmetic. A rubric can make each row mean something specific: 21 for labeling the x-axis, 22 for the y-axis, 23 for the first curve, and so on.

**Replacing the header.** Cover the Honor Pledge with a white box and put your own text there. Cover all but the first four ID columns and use assigned four-digit IDs, or cover the ID block entirely.

**Making room for a written answer.** Put the question number and a blank line in the answer box on the right. For the scanner to grade it, **every student's answer for a given question must be in the same place on the page**, since the crop region is defined once and applied to every sheet.

**A written question in the middle of the exam.** If question 14 is a fill-in-the-blank, put its answer blank in the space on the right, then cover the bubbles for question 14 and add a black arrow pointing right. Tell the scanner to ignore question 14 when you run the scan, or it will grade an empty bubble row as a wrong answer.

## Designing an answer blank for good transcription

Handwriting is transcribed by a cloud model (see [Open-ended questions](open-ended-questions.md)), and the crop it is handed is only as clean as the page. Five things measurably help:

Use a **single horizontal underline** rather than a full rectangle. Vertical box borders get read as parentheses. Print the line in **light gray** rather than black, so that under auto-contrast the line fades while pencil and ink stay dark. Make the blank **at least 6 to 8 cm wide**, so students write legibly and the whole word lands inside the crop. Put any printed label such as "Final Answer:" **above** the line rather than beside it, which leaves you a crop region containing nothing but handwriting. And when you draw that crop during grading setup, **crop tightly** — exclude the printed line and the label. Less extraneous ink is a better transcription.

---

Previous: [Importing a Canvas quiz](importing-canvas-quizzes.md) · Next: [Building a key](building-keys.md)
