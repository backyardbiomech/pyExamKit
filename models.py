from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Answer:
    text: str
    is_correct: bool
    image_path: str | None = None  # relative path from source folder, for image answer choices


@dataclass
class Dropdown:
    name: str
    answers: list[Answer] = field(default_factory=list)


@dataclass
class Question:
    q_type: str               # 'MC', 'MA', 'MD', 'MD_EXPANDED'
    text: str                 # question stem (may contain inline HTML/MathJax)
    answers: list[Answer] = field(default_factory=list)      # MC and MA
    dropdowns: list[Dropdown] = field(default_factory=list)  # MD only
    image_paths: list[str] = field(default_factory=list)     # relative paths from source folder
    points: str | None = None   # e.g. "2" or None
    source_text: str = ''       # original raw block text, used for markdown re-export
    source_folder: Path | None = None  # absolute path to the folder this question came from


@dataclass
class ExamVersion:
    title: str
    course: str
    version_num: int            # 1-indexed; maps to letter A, B, C...
    questions: list[Question] = field(default_factory=list)
    source_folder: Path = field(default_factory=Path)

    @property
    def version_letter(self) -> str:
        return chr(ord('A') + self.version_num - 1)
