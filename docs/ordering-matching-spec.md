# Ordering (OR) and matching (MT) questions on paper exams

*Written 2026-09-04. A feature for the merged app, to be built after the phase 0 packaging experiment and alongside or before the full merge. Depends on `keyformat.py` from phase 1 of `merge-and-package-plan.md`.*

## Verdict

Buildable, and the design mostly falls out of a pattern the codebase already has. MD questions already do the hard part: one question object that occupies several sequential slots on the bubble sheet. OR and MT are the same shape with different contents. Following that pattern gives the "cannot be split during shuffling" requirement for free, because shuffling operates on whole `Question` objects and never reaches inside one.

## What is actually in the pools

Surveyed every question bank under `~/Library/CloudStorage/Box-Box/__My_Folders/_Teaching/`, not just BIOL 206.

**BIOL 206**, six OR items and two MT items. OR item counts are 3, 3, 3, 3, 4, and 5, in `c9_muscles_level1` (three), `c15_specialSenses_level1`, `c1_lab_language_and_cavities`, and `c7_skeleton_level2`. Both MT items, in `c15_specialSenses_level2` and `c4_level1`, have four lefts, with six and four rights. All eight fit.

**BIOL 207**, three OR items and one MT item. The MT in `c17_level1_heart` has five lefts and four rights, and two of its lefts share one right, so the shared-answer case is real content rather than a hypothetical. The two OR items in the same file have six items and four items. **The six-item one sits exactly at the limit with no headroom.**

**BIOL 306**, one MT item in `VP18_muscleEnergetics2`, three lefts and five rights. Fits.

**BIOL 120** carries MT items across F19, S19, and F22 folders. Those are archived semesters and were not surveyed in detail; check them if that course is ever revived.

### The one item that cannot work

`BIOL207/QuestionBanks/exam3Banks/ch24urin_level1.txt` has an eleven-step ordering, tracing fluid from the glomerulus through to the ureter. **Eleven items cannot fit a six-bubble sheet, and an ordering cannot be trimmed without changing the question.** The builder will reject it with a warning, which is the correct behavior, but it means real content is unavailable on paper.

Three ways out, in the order I would try them. Split it into two OR questions with a natural seam, for instance glomerulus through distal convoluted tubule as one and collecting duct through ureter as the other, which preserves the content at the cost of two question groups. Or rewrite it as an MC question whose options are whole candidate orderings, which is the workaround already used elsewhere in these pools for dead OR items. Or leave it as a Canvas-only question, since the source format is unchanged and it still converts.

This is a content decision, not a code one, and it should be made before the feature is used in BIOL 207 rather than discovered at exam-building time.

## The hard constraint: six bubbles

`init_functions.py:180` builds the answer-letter map as `for i in range(0, 6)`, so **the answer sheet has exactly six choices per question, A through F**, and 150 question slots in total. This is why `exam_builder._trim_mc_answers` has `max_choices=6`.

The six is a property of the printed answer sheet, whose bubble coordinates are fixed in `dicts.py` at `Qwidth = 160` with 26-pixel spacing. The `range(0, 6)` in `init_functions.py` mirrors the paper. Raising it would mean redesigning the sheet template, rewriting the coordinate tables, and reprinting, which is not worth doing for the single question named above.

That sets the limits:

- **OR: at most 6 items to order.** An ordering cannot be trimmed the way a multiple-choice question can, because dropping an item changes the question. Anything longer has to be rejected with a warning rather than silently mangled.
- **MT: at most 6 right-side options**, distractors included. This one *can* be trimmed, exactly the way MC answers are: keep every right that is some left's correct answer, then randomly sample distractors to fill the remaining slots. The left-side count is limited only by the 150 slots.

There is a real cost worth stating plainly. A five-item OR consumes five of the 150 question slots and one question's worth of points. These are expensive in sheet space, which is an argument for using them deliberately rather than sprinkling them through a pool.

## A bug this work should fix

`key_generator.py` writes the full per-question point value onto **every** row of an MD question:

```python
if q.q_type == 'MD':
    pts = _effective_points(q, default_points)
    for dropdown in q.dropdowns:
        bubble_rows.append((q_label, _dropdown_answer(dropdown), pts))
```

`grade_functions.gradeResults` then reads points per column and sums them, so a three-dropdown MD tagged `(1 pt)` is currently worth three points, not one. That is the same defect the OR and MT feature is being written to avoid, and it exists today in MD.

Fix it in the same change, using the same distribution rule below. Check your recent MD-containing exams before deciding whether any grades need revisiting.

## Points: split evenly across the group

A group of N slots worth P points total gets P/N per slot. A student who gets two of three right earns two thirds of the points, which matches how Canvas scores matching questions and is the friendliest behavior on paper.

Distribute by largest remainder at two decimal places so the printed key is readable and the parts sum exactly to the whole. One point over three slots becomes 0.34, 0.33, 0.33 rather than three values of 0.3333 that sum to 0.9999.

This needs no scanner change at all. The key CSV already carries a per-row `points` column and the grader already sums it.

## Source formats

Both come from qtiConverter and stay unchanged, so the same pool files keep working for Canvas.

**OR** lists items in their correct order, bracketed by two labels:

```
OR
32. Order the following erector spinae muscles from medially to laterally.
toplabel: medial
1: spinalis
2: longissimus
3: iliocostalis
bottomlabel: lateral
```

**MT** puts each left item's correct right label in brackets, then lists all rights, distractors included:

```
MT
69. Match each type of epithelia with its function.
[right1]left1: simple squamous epithelium
[right2]left2: columnar epithelium
right1: diffusion
right2: secretion
right3: protection
```

Multiple lefts may share one right. Labels are arbitrary tokens, not necessarily `right1`, `right2`, and so on, so match them as `\[(\w+)\](\w+):\s*(.+)` and `(\w+):\s*(.+)` rather than assuming the naming.

## Model

Extend `models.py` with two shapes, kept parallel to `Dropdown`:

```python
@dataclass
class OrderItem:
    text: str
    rank: int          # true position, 1-based, from the source file

@dataclass
class MatchLeft:
    text: str
    correct_label: str

@dataclass
class MatchRight:
    label: str
    text: str
```

`Question` gains `order_items`, `order_top_label`, `order_bottom_label`, `match_lefts`, and `match_rights`, all defaulting empty, and `q_type` accepts `'OR'` and `'MT'`. Add both to `parser._TYPE_LIST`.

Because a group is one `Question`, `random.shuffle(selected)` in `exam_builder` moves it as a unit and the group can never be split. Nothing extra is needed for that requirement.

## Display and lettering

**OR.** Scramble the items, assign letters A onward in the scrambled display order, then present N answer slots, one per rank position. Slot i's correct letter is the display letter of the item whose `rank` is i.

Brandon's example: items `tall, average, short` are the true order shortest-to-tallest reversed, so with display order `A: tall, B: average, C: short` and the question starting at slot 5, the key is `5: C, 6: B, 7: A`.

**Scramble OR items unconditionally, whether or not `shuffle_answers` is set.** The source file lists them in correct order, so an unscrambled OR has the answer A, B, C, which is not a question. This is a deliberate departure from how the other types treat that setting, and it should be commented as such in the code.

**MT.** Scramble the rights and letter them A onward. The lefts become the slots, in source order unless `shuffle_questions` is set, in which case scramble those too. Each left's correct letter is the display letter of its bracketed right.

Render both to mirror the existing MD convention, where the stem carries `<strong>(Question N)</strong>` markers:

```
5–7.  Order the following erector spinae muscles from medially to laterally.
      A. iliocostalis    B. spinalis    C. longissimus

      (Question 5)  medial
      (Question 6)
      (Question 7)  lateral
```

```
8–11. Match each type of epithelia with its function.
      A. protection   B. diffusion   C. distensibility   D. secretion

      (Question 8)   simple squamous epithelium
      (Question 9)   columnar epithelium
      (Question 10)  stratified squamous epithelium
      (Question 11)  transitional epithelium
```

The OR `toplabel` and `bottomlabel` go against the first and last slots, which is what makes the direction of the ordering unambiguous on paper.

## Key output

Both types emit ordinary `bubble` rows carrying a single letter, indistinguishable from MC rows to anything downstream. The slot counter advances once per row, exactly as it does for MD dropdowns.

**The scanner needs no changes whatsoever.** That is the strongest argument for this design, and it should stay true; if a proposal starts requiring a `group` column in the key CSV, reconsider it.

## Guards

`_trim_mc_answers` must skip OR and MT, since it assumes `q.answers`. `_align_diagram_letters` must skip them too, since sorting an ordering's display letters would undo the scramble.

Reject with a warning, in the existing `warnings` list rather than an exception: an OR with more than six items, an OR with fewer than two, an MT whose right count still exceeds six after distractor trimming, an MT with a bracketed label that matches no right, and an MT with no lefts. The warning text should name the file and the block number, matching the style of the messages `parser.parse_file` already produces.

## Markdown round-trip

`renderer.to_markdown` must write OR and MT blocks back in the source format above, and it must write OR items in **true rank order, not display order**, or the regenerated file is wrong. Keep `source_text` populated for both so the raw block survives regardless.

## Where this lands

Build it in the merged repository, after `keyformat.py` exists and after pyExamPaper's modules have moved into `pyexamkit/build/`. Doing it earlier means writing it twice.

Order of work: parser support with unit tests against the eight real pool items first, then the model and builder changes with the guards, then the points distribution including the MD fix, then the HTML template blocks, then the markdown round-trip. Generate a real exam containing all eight items, print it, fill an answer sheet by hand, and scan it, before trusting the feature with a class.

One last note: the `c15_specialSenses_level2` MT item is an ordering question written as a matching question, with lefts labeled Step 1 through Step 4. It will work correctly as MT and there is no need to change it. It is worth knowing it is there when the OR rendering is tested, so it is not mistaken for a bug.
