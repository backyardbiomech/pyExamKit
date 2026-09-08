# Question bank format

A question bank is a plain text file — `.txt` or `.md`, UTF-8 — holding one question per block, blocks separated by blank lines. This is the same format [qtiConverter](https://github.com/backyardbiomech/qtiConverter) reads, so one bank file can produce both a paper exam here and a Canvas quiz there. Write it in any editor that saves plain text: VS Code, Notepad++, BBEdit, RStudio. If you use Word, "Save As" plain text with the encoding set to Unicode (UTF-8), and be aware that formatting and embedded images are lost in the process.

Keep the bank file and every image it references in the same folder. The exam builder resolves image paths relative to the bank file.

## The shape of a block

Every question block is a run of consecutive non-blank lines. **There must be no blank line inside a question**, and at least one blank line between questions. A block is up to three optional header lines, in any order, followed by the numbered question stem and its answers.

```
MC
image: skin_layers.png
(2 pts)
1. Which layer of the epidermis is deepest?
*A. stratum basale
B. stratum corneum
C. stratum lucidum
D. stratum granulosum
```

The **type line** is a two-letter code in capitals on a line by itself. Leave it out and the question is treated as multiple choice. The **image line** reads `image: filename.png`, with the path relative to the bank file, so `image: figures/skin.png` works for an images subfolder. The **points line** is a number in parentheses, and any words after the number are ignored, so `(2)`, `(2 pts)`, and `(2.5 points)` all set the same value. A point value written here overrides both the pool's Pts/Q column and the exam-wide default.

The stem begins with a digit followed by a period or a close parenthesis. The numbers do not have to be sequential or unique — the builder renumbers every question when it lays out the exam — so a bank assembled from several sources can leave its original numbering alone. Answer choices begin with a letter followed by a period or a close parenthesis, and a leading `*` marks a choice as correct.

A line beginning with `#` is a comment and is dropped before parsing, so you can annotate a bank freely.

## Which types pyExamKit builds

| Code | Question type | Bubbles used |
|---|---|---|
| `MC` | Multiple choice | 1 |
| `MA` | Multiple answer (select all that apply) | 1 |
| `TF` | True/false | 1 |
| `SA` | Short answer / fill in the blank | not bubbled — see below |
| `MD` | Multiple dropdown | 1 per dropdown |
| `OR` | Ordering | 1 per item |
| `MT` | Matching | 1 per left-hand item |

`ES`, `MB`, `NU`, `CT`, and `HS` — essay, fill-in-multiple-blanks, numerical, categorization, and hot spot — are Canvas-only. pyExamKit names each one in the log and skips it rather than failing the whole bank, so a file written for Canvas can be pointed at the exam builder without editing. Anything else in the type position is not recognized as a header at all and ends up read as part of the stem, which usually shows up as a "could not parse" warning.

## The six-bubble ceiling

The printed answer sheet gives every question **six choices, A through F**, and **150 question slots** in total. That is a property of the paper, not a setting, and it constrains what a bank can express.

A multiple choice or multiple answer question with more than six choices is **trimmed at load time**: every correct answer is kept, and wrong answers are randomly sampled to fill what is left. The trim happens once per build, so all versions of one exam see the same subset of choices even when the answer order differs between them.

Ordering, matching, and multiple dropdown questions each consume one slot per item, so the slot count runs ahead of the question count. Five of these questions with four items each fill twenty slots. The builder warns when an exam needs more than 150 slots; questions past that point still print, but there is nowhere on the sheet to bubble them, so they cannot be graded.

## Multiple choice and multiple answer

`MA` has the same shape as `MC` with more than one starred answer. You rarely need to write the `MA` line by hand — a block declared `MC` is promoted to `MA` automatically as soon as a second star appears.

```
MA
1. Which of these are functions of the skin?
*A. thermoregulation
*B. vitamin D synthesis
C. gas exchange
*D. protection from abrasion
```

If the stem opens with "select all that apply," in any capitalization and with any trailing punctuation, that phrase is stripped — the printed exam labels the question type itself, so the phrase would be printed twice.

An answer choice can be an image instead of text, written as `A. image: filename.png`.

## True/false

`TF` takes the truth value on an `A:` line instead of lettered choices, and the exam prints True and False as the two options.

```
TF
1. The dermis is deep to the epidermis.
A: True
```

The value is not case sensitive. `TF` exists as its own type, rather than as an `MC` with two choices, so the file stays meaningful if it is ever read back into Canvas.

## Short answer

`SA` is a written-answer question, not a bubbled one. The answer lines list the strings that count as correct, and grading compares a student's handwriting against them — see [Open-ended questions](open-ended-questions.md) for how that comparison works. A run of three or more underscores in the stem prints as a fill-in blank.

```
SA
(2 pts)
1. The ___ is the deepest layer of the epidermis.
*A. stratum basale
*B. basal layer
C. stratum basil
```

Starring is what separates full credit from partial: **starred answers earn full credit, unstarred answers earn half**. If no answer is starred, every listed answer earns full credit, which is the sensible reading of a bank that predates the distinction. Unlike every other type, `SA` answer text is stored exactly as written, with no formatting or HTML processing, because those strings are compared character by character against what a student wrote.

Because an `SA` question is answered on the page rather than in a bubble, its bubble row has to be excluded from bubble grading. [Answer sheets](answer-sheets.md) covers how to lay one out, and [Scanning and grading](scanning-and-grading.md) covers telling the scanner to ignore that row.

## Multiple dropdown

`MD` places a `[label]` placeholder inline in the stem for each dropdown, then lists that dropdown's options as `label: text`, with `*` on the correct one. Labels must be single words with no spaces.

```
MD
1. The [bone] articulates with the humerus, forming the [joint].
*bone: scapula
bone: clavicle
bone: femur
joint: elbow
*joint: shoulder
```

Each dropdown takes its own bubble row on the answer sheet, and the question's points are split evenly across them: a two-dropdown question worth two points is worth one point per dropdown, so a student who gets one right earns one point.

## Ordering

`OR` lists its items **already in the correct order**, numbered `1:` through `N:`, bracketed by a `toplabel` and `bottomlabel` pair that tell the student which end of the sequence is which.

```
OR
1. Order these skin layers from most to least superficial.
toplabel: most superficial
1: stratum corneum
2: stratum granulosum
3: stratum spinosum
4: stratum basale
bottomlabel: least superficial
```

pyExamKit **always scrambles the printed order** of an ordering question, regardless of the shuffle-answers setting, because printing the items in source order would print the answer key as the question.

Three rules are enforced, each with its own warning in the log. An ordering needs **at least two and at most six items**, since it takes one bubble per item and cannot be trimmed the way a multiple choice question can — dropping an item changes the question. And the numbers must be exactly 1 through N with no gaps and no repeats, so a bank numbered from zero or missing a step is skipped rather than half-built.

An ordering longer than six items has to be rewritten to fit: split it at a natural seam into two shorter orderings, or convert it into a multiple choice question whose options are whole candidate sequences. It can also be left in the bank as a Canvas-only question, since pyExamKit skips it with a warning and qtiConverter still converts it.

## Matching

`MT` gives each left-hand item the label of its correct right-hand option in brackets, then lists every right-hand option, distractors included.

```
MT
1. Match each epithelium to its function.
[right1]left1: simple squamous epithelium
[right2]left2: simple columnar epithelium
[right1]left3: endothelium
right1: diffusion
right2: absorption
right3: protection
right4: secretion
```

Several left items may share one right, as `left1` and `left3` do here. Labels on both sides must be single words made of letters, digits, and underscores. Every bracketed reference must name a right-hand option that exists, or the question is skipped with a warning naming the missing label.

Each left item takes one bubble row, and the points are split evenly across them. The right-hand options are **always scrambled** on the printed exam regardless of the shuffle-answers setting, for the same reason ordering items are: banks are usually written with the lefts in the same order as the rights they point at, so source order would run the answer key straight down the page.

If a matching question has more than six right-hand options, they are trimmed to six the same way multiple choice answers are — every right that is somebody's correct answer is kept, and distractors are randomly sampled to fill the rest. A question whose correct answers alone number more than six cannot be trimmed and is skipped with a warning.

## Formatting inside questions and answers

Markdown-style marks work in stems and in answer choices. Surround text with `**` for **bold**, a single `*` for *italic*, `^` for superscript, and `~` for subscript, with no spaces between the marks and the text they wrap: `E = mc^2^`, `H~2~O`, `**not**`. The HTML equivalents — `<strong>`, `<em>`, `<sup>`, `<sub>` — work too, and the two styles can be mixed in one file.

`<br>` forces a line break inside a question. This is the only way to get one, because a real blank line would end the block and start a new question.

Text between `$…$` or `$$…$$` is passed through untouched for MathJax to render, so equations survive intact. Everything outside a math block has its HTML special characters escaped, which means a stray `<` or `&` in a stem prints as itself rather than breaking the page.

---

Previous: [Installation](installation.md) · Next: [Building an exam](building-exams.md)
