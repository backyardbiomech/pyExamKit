# Importing Canvas quizzes as question banks

*Written 2026-09-08, alongside `qti_import.py`.*

The **Build Exam** tab can read a Canvas QTI export directly, so a quiz that already exists in Canvas becomes a paper exam pool without being retyped. This document records what the export actually contains and why the reader is built the way it is; the user-facing description is the "Importing a Canvas quiz" section of `README.md`.

## Canvas exports New Quizzes in the classic QTI 1.2 wrapper

The assumption going in was that New Quizzes, being the newer engine, would export QTI 2.1, and that classic quizzes and New Quizzes would therefore need separate readers. A real export from a live New Quiz says otherwise: `imsmanifest.xml` declares the assessment resource as `type="imsqti_xmlv1p2"`, and the assessment file's root element is `questestinterop` in the `ims_qtiasiv1p2` namespace, which is the same QTI 1.2 that classic quizzes have always used and that `qtiConverter` writes. One reader covers both engines. Anything written here about "the export" holds for either.

A zip holds `imsmanifest.xml`, one folder per assessment containing the assessment XML and an `assessment_meta.xml` of Canvas-specific settings (due dates, attempt limits, shuffle flags — none of which matter to a printed exam), and an `Uploaded Media/` folder of any images the questions use. An item bank export can hold several assessments; the converter folds them all into one bank file, because pyExamKit draws a pool per file and splitting them would just make the user re-add each one.

## The reader keys on structure, not on Canvas's identifiers

Every branch in `qti_import.py` is driven by the shape of the XML: how many `response_lid` blocks an item has, whether `rcardinality` is `Single`, `Multiple` or `Ordered`, and which answer identifiers a scoring `respcondition` names. It never matches on the identifiers themselves. That is deliberate. Classic quizzes number their answers `1, 2, 3`; New Quizzes uses UUIDs; `qtiConverter`'s own output uses `resp0, resp1`. Matching on any of those would have produced a reader that worked on exactly one of the three.

The one thing read by name is the `question_type` metadata field, which routes each item to a writer. Canvas puts it on every item in both engines, and there is no reliable way to tell a `multiple_answers_question` from a `multiple_choice_question` that happens to have two correct answers without it.

**Correctness comes from the scoring conditions, not from an attribute on the answer.** QTI 1.2 does not mark a choice as correct where the choice is defined. It states, separately, which combinations of responses earn points. `_correct_map` therefore walks every `respcondition`, keeps the ones whose `setvar` assigns a positive value, and collects the answer identifiers their `varequal` nodes name, keyed by `respident` so per-blank questions stay separated. Two details matter. A condition may use `action="Set"` (the whole question is right or wrong: MC, MA, SA) or `action="Add"` (partial credit per blank: MD, MT), and both must count, which is why the test is on the value rather than the action. And a multiple-answer condition names its distractors explicitly inside a `<not>` element, so those `varequal` nodes have to be excluded or every choice comes back marked correct.

## Where the bank format forced a translation

**Matching labels are renumbered.** `parser.py` matches right-hand option labels against `\w+`, and Canvas identifies them with hyphenated UUIDs, which fail that pattern. The converter assigns `right1..rightN` in the order the first left-hand item lists them and rewrites the correct-answer references to suit.

**Ordering is read from the scoring condition.** The response labels inside an ordering question appear in whatever order Canvas stored them; the correct sequence is the order the `varequal` nodes appear in the condition. That sequence becomes the `1:`, `2:`, `3:` ranks the bank format wants. `parser.py` rejects ranks that are not exactly 1..N, so a partial or repeated sequence is a skipped question rather than a `KeyError` at build time.

**True/false becomes its own bank type, not two lettered choices.** The bank's `TF` block carries the truth value on an `A:` line and `parser.py` expands it into a two-choice question. Emitting `*A. True / B. False` would have worked too, but it would have lost the fact that the item is a true/false question if the file were ever read back into Canvas.

**Everything collapses to a single line.** Canvas stores question text as HTML. The bank format splits questions on blank lines and reads a line beginning with a letter and a period as an answer choice, so a preserved line break inside a stem either ends the question early or invents an answer. Inline emphasis survives as the bank's `**`, `*`, `^` and `~` markers; block structure does not. This is the conversion's real lossy edge, which is why both the log and the header comment in every converted file tell the user to read the result before building.

## What is skipped, and why it is named

Essay, numerical, fill-in-multiple-blanks, calculated, file-upload, text-only, categorization, and hot spot questions cannot be answered in six bubbles. They are skipped, but each one is reported by its plain-English name, so the pool count on screen can be reconciled against the quiz it came from. A silent drop would look identical to a parser bug.

## Fixtures

`tests/fixtures/qti_import/newquiz_export.zip` is a real Canvas New Quizzes export with every question and answer string replaced by "Fabricated text N" and every image replaced by a 1×1 PNG. The XML structure — identifiers, metadata, scoring conditions, `$IMS-CC-FILEBASE$` image references, the literal `+` characters and the `.jfif` extension Canvas leaves in uploaded filenames — is untouched. This repo is public and the source quiz is in use, so the structure is the part worth keeping and the content is not, the same convention as `tests/fixtures/or_mt/`.

`tests/fixtures/qti_import/all_types_export.zip` is a copy of `qtiConverter`'s `testFiles/simple Test For Import/bank1_export.zip`, which carries one question of every type it writes. The available New Quizzes export happens to contain only multiple choice, multiple answer, and true/false, so this is the only sample of the QTI encodings for short answer, multiple dropdown, matching, and ordering. Canvas accepts what `qtiConverter` produces, so a bank → QTI → bank round trip through it is what verifies those four readers. If a real Canvas export of those types ever comes to hand, add it as a third fixture rather than replacing this one; the two check different things.

Every test also runs its converted file back through `parser.py`. The point of the converter is a file pyExamKit can build an exam from, so output the parser rejects is a failure even when the XML was read correctly.
