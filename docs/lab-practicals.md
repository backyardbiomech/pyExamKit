# Lab practicals

A lab practical here is a set of numbered stations, each with four written questions, A to D. Each student answers two of the four letters, and the pair (their **form**, such as AC) is the same at every station. Students at one table answer different letters, so neighbors cannot copy, and every student still visits every station.

pyExamKit builds a practical from one plain-text source file and grades it with that same file. Every form's sheets are scanned together in one stack, and each question has one list of accepted answers, so an answer you accept for 7C while grading counts for every student who answered 7C, whatever their form.

## The source file

The source file is markdown, readable in any text editor. Each station starts with a heading, each question starts with its letter, and the accepted answers follow the question: `=` lines are full credit and `~` lines are partial credit.

```markdown
---
title: BIOL 207 Lab Practical 3
forms: AB, CD, AC, BD, AD, BC
points: 1
---

# Station 1: kidney model
setup: Kidney model, frontal section. Pins A to D.
image: images/kidney_frontal.png

A. Name the structure at pin A.
= renal pelvis
~ pelvis

B. Name the structure at pin B.
= renal pyramid | medullary pyramid

C. Name the structure at pin C.
= renal cortex
= cortex

D. What passes through the structure at pin D?
= urine
(2 pts)

# Station 2: kidney slide
setup: Microscope, kidney slide, 40x, pointer on a glomerulus.
...
```

**The settings at the top**, between the `---` lines, are all optional. `title` names the practical on every printed page and in every file name; without it, the file name is used. `forms` lists the letter pairs in use, in the order they are handed out (see [Printing and handing out](#printing-and-handing-out)); without it, all six pairs are used in the order shown above, in which each pair is followed by its complement, so two neighbors never share a question. `points` is what each question is worth, 1 by default.

**Stations** are numbered from 1 with no gaps, as `# Station 1`. Anything after the number (`: kidney model`) is the station's name. The name appears only in the setup guide and the instructor key, never on anything students see, since a name like "kidney model" can give answers away.

**Setup lines**, `setup:` under the station heading and before question A, are notes for whoever sets up the room: which model, which slide, where the pins go. They also appear only in the setup guide.

**Images**: an `image:` line under a station heading prints on that station's placard; an `image:` line under a question prints under that question. The path is relative to the source file, so keep the images in a folder beside it. A station or question can have several `image:` lines.

**Questions** start with the letter and a period or parenthesis, `A.` or `A)`. The question text can run onto following lines. Every station needs every letter the forms use.

**Answers** go on `=` (full credit) and `~` (partial credit) lines after the question. Several answers can share a line, separated by `|`, or each can have its own line. Capitalization does not matter in grading.

**Points**: a `(2 pts)` line under a question overrides the default for that question alone. Be careful with this on a practical. Each letter appears in half the forms, so making 7A worth 2 points gives the students whose form includes A one more point possible than everyone else. To keep every form out of the same total, give the extra points to all four questions at a station, or none.

**Comments** in `<!-- -->` are ignored, and so is any other heading. If the file has a problem the build stops and lists every problem it found, with line numbers; problems that do not stop a build (a question with no full-credit answer, say) are listed as warnings.

### Starting from an older practical

A practical graded with a separate key CSV for each form (one for AB, one for AC, and so on) can be folded into one source file with a command-line tool, run from the pyExamKit folder:

```bash
uv run python tools/practical_from_keys.py Practical_3_key_*.csv -o practical3.md
```

It collects every station's accepted answers from all the keys into one file. The old keys hold no question text, so each question is written with a blank for you to fill in. An answer that was full credit on one key and partial on another is kept as full credit, and the tool lists those so you can check them.

## Building

The **Build Practical** tab needs a source file, an output folder, and optionally a class size. Choosing the source file shows a one-line summary of what it found (stations, questions, forms) or, if the file cannot be used, why. The output folder defaults to a folder named after the practical beside the source file. **Build Practical** writes:

- **A form sheet for each form**, such as `Practical_3_form_AC.pdf`: the answer sheet for students with that form. A sheet with an odd number of pages ends with a page marked "intentionally blank", so that printed double-sided, every student's sheet starts on a fresh piece of paper.
- **One combined sheet PDF**, when a class size is given: that many sheets with the forms dealt out in order, ready to print as one job. Leave the class size blank to skip it.
- **Placards**, one page per station: the station number in large type, all four questions, and the station's images, filling the page. All four letters print, since students at one table answer different letters. When a station's images would print less than 2.5 inches tall under its questions, they move to a second page headed "Station N (continued)" and the log says so.
- **The setup guide**, for whoever sets up the room: for each station, its name, its setup lines, its images with their file names, and every question with its accepted answers, each with a box to tick. Walk the room with it and check each pin against the answer the key expects.
- **The instructor key**: every question and its answers, compactly, for reading without the app.

The log lists every file written and every warning. A missing image is a warning rather than a stop, and it prints on the placard as a red box naming the missing file, so it cannot be overlooked on paper.

The same build runs from the command line:

```bash
uv run python practical_build.py practical3.md --students 48
```

## The form sheet

A form sheet has the usual name line and ID bubbles on page 1, and below them a row for each station with two writing boxes, labeled with the station number and the form's two letters. Page 1 holds 11 stations and each later page 15, so a 25-station practical takes two pages, one piece of paper printed on both sides. Up to 11 stations fit on the front of one piece of paper, 12 to 26 take both sides of one, and 27 to 41 (the most a sheet holds) take two.

The form is printed on every page as small black squares in the bottom margin, next to the code that tells the scanner which page it is. **The scanner never relies on anything the student writes to know their form**, so a student cannot answer the wrong letters by mistake. "Form AC, page 1 of 2" is printed small on each page for whoever hands out the sheets.

## Printing and handing out

Print the combined sheet PDF **double-sided, and do not staple it**: the stack has to go through the scanner's document feeder afterward, and a staple stops it. With 26 stations or fewer, each student's sheet is a single piece of paper, so there is nothing to hold together. With more, each student has two pieces; hand them out together, and if you clip them, take the clips off before scanning. Printing at a reduced scale to fit a printer's margins is fine; the sheets scan correctly down to at least 80%.

Hand the stack down each row in order. Because the forms are dealt in the order the source file lists them, neighbors get different forms, and with the default order, a student's neighbors share no question with them.

Print the placards and the setup guide separately. Nothing on a placard gives away an answer, but the setup guide and the instructor key hold every answer and should stay with the instructors.

## Scanning and grading

Scan the whole stack at once through the document feeder, **double-sided**, every form mixed, at 200 dpi or better in color, as for any exam ([Scanning and grading](scanning-and-grading.md) covers the scanning itself). Order does not matter between students, but each student's pages must stay together with page 1 first, which double-sided scanning of an unshuffled stack gives you. Blank backs are skipped, so there is no need to turn on the scanner's own blank-page removal, and no harm in it.

On the **Scan Exams** tab, choose the practical's source `.md` file as the key. It is the key; there is no CSV. The line under the button confirms it as a lab practical with its stations, forms, and pages per student, and **Grade written answers on screen** is checked for you. Load a [class roster](roster.md) to have names on the results, since the sheet's ID bubbles are all it has to go on.

The scanner groups the pages into students by what is printed on each page, reads each student's form from the squares and their ID from page 1, and then grades the written answers. A page that does not fit is reported in `ALERT.txt` rather than guessed at: a page 2 with no page 1 before it, a page 2 of form BD behind a page 1 of form AC, a missing page (whose answers are left blank), or a sheet whose form squares cannot be read.

The grading window works as described in [Open-ended questions](open-ended-questions.md), with two differences. It goes station by station and letter by letter (all of 1A, then 1B, through 25D), and each question is shown only for the students whose form includes it, so "3 of 24" means the third of the 24 students who answered it. The top line gives the question text, and the line below names the student, with a picture of the name they wrote on page 1, so you can recognize a student with a spelling accommodation before grading their answer. That picture is shown only on your screen; only the answer boxes are ever sent for AI transcription.

**Edit…**, next to the key on Scan Exams, is unavailable for a practical: its key is the source file, so open that in a text editor to change it. **Answers you add to the key while grading are written into the source file**, as new `=` or `~` lines under that question. Nothing else in the file changes, so next year's practical starts with every answer you accepted this year. The same happens for answers added later on the **Re-grade** tab.

## What the results hold

The outputs are the ones described in [Outputs](outputs.md), with a few differences. The gradebook has a `form` column, and a column for each question, `openQ_1A` through the last station's D. A question not on a student's form is left blank, not zero. Scores and the Canvas upload file come from the questions each student answered.

Each student's marked pages are saved as `Last_First_ID_p1.jpg`, `_p2.jpg`, and so on, with a green C, orange P, or red X just right of each graded box, clear of the writing, and the form and score (such as "Score 44 / 50") on page 1.

---

Previous: [Outputs](outputs.md) · Next: [FAQ and troubleshooting](faq.md)
