# History

pyExamKit is the third life of software that started as a stopgap.

## A scanner to replace Scantron (2015)

In 2015 the university planned to retire its Scantron hardware. I had been using computer vision in Python to build research software for studying animal locomotion, and reading filled bubbles off a scanned page is a much simpler version of the same problem, so I wrote my own scanner to take Scantron's place. That program, pyExamScan, graded my exams for the next several years and became the backbone of pyExamKit.

## Canvas quizzes and qtiConverter (2019)

The university then began encouraging faculty to give quizzes in Canvas during class instead of on paper, and around 2019 I made that move. Respondus, the usual tool for turning a document of questions into a Canvas quiz, was not available for Macs. So I wrote [qtiConverter](https://github.com/backyardbiomech/qtiConverter), which converts questions written in a local plain-text file into a QTI package that Canvas imports as a quiz. Over the following years that text format grew to cover the question types Canvas supports beyond multiple choice: multiple answer, short answer, multiple dropdown, matching, and ordering.

## The pandemic and the lockdown browser

When the pandemic moved teaching online, staying in Canvas was the natural choice, and I gave exams there under the various lockdown browsers the university supplied. That held until I found several instances of AI-based and old-fashioned cheating on locked-down quizzes in my own classes, both in class and at home, despite screen recording and second cameras.

## Back to paper (2026)

So, I decided to move exams back to paper, in class. What I did not want to give up was the question banks themselves: years of questions written in qtiConverter's format, many of them in the newer types that a bubble sheet had never handled. pyExamKit is the result. Working with Claude Code, I updated and resurrected the old scanner, changed the backbone scanner to make the package smaller and more efficient, added the features those question types need on paper (ordering, matching, dropdowns, handwritten short answers), added handwriting recognition, and packaged it together with several earlier repositories into one desktop app. The question bank format is still the one qtiConverter reads, so one bank file can produce both a paper exam here and a Canvas quiz there.

## How I use it now

I now use my large question pools to give online practice quizzes before an exam. When students sit for the exam in person and on paper, they've seen some of the questions before. With the easy ability to create multiple versions, I don't have to worry about students looking at each other's answers, and I can focus my proctoring energy on other things. There's still a risk of phones in laps, cheat sheets on water bottles, etc., but not having laptop screens to hide behind makes that a bit easier. The ability to scan all versions at once saves me a lot of time shuffling things around, too.
