"""
exam_config.py

Save and load the full GUI configuration (BuildConfig + output folder) to/from JSON
so that an exam can be easily re-run or reshuffled without re-entering all settings,
and optionally the built exam itself, so it can be reprinted exactly.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from exam_builder import FONT_SIZES, BuildConfig, PoolConfig
from models import Answer, Dropdown, ExamVersion, MatchLeft, MatchRight, OrderItem, Question

_SCHEMA_VERSION = 1


def save_config(config: BuildConfig, output_folder: Path, dest: Path,
                versions: list[ExamVersion] | None = None) -> None:
    """Serialize config + output_folder to a JSON file at dest.

    With versions, the file also records the exam exactly as printed: every
    question's full text, in order, with its answers in order. The content is
    stored rather than a random seed because a seed only reproduces an exam
    until a bank file is edited. load_versions reads it back.
    """
    pools_data = [
        {
            "filepath": str(p.filepath),
            "count": p.count,
            "points": p.points,
        }
        for p in config.pools
    ]
    data = {
        "schema_version": _SCHEMA_VERSION,
        "title": config.title,
        "course": config.course,
        "num_versions": config.num_versions,
        "shuffle_questions": config.shuffle_questions,
        "shuffle_answers": config.shuffle_answers,
        "same_questions": config.same_questions,
        "version_question": config.version_question,
        "version_question_position": config.version_question_position,
        "default_points": config.default_points,
        "font_size": config.font_size,
        "source_mode": "pools" if config.pools else "exact",
        "exact_file": str(config.exact_file) if config.exact_file else None,
        "pools": pools_data,
        "output_folder": str(output_folder),
    }
    if versions:
        data["versions"] = [_version_to_dict(v) for v in versions]
    dest.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_config(path: Path) -> tuple[BuildConfig, Path]:
    """Load a previously saved config file. Returns (BuildConfig, output_folder)."""
    data = json.loads(path.read_text(encoding="utf-8"))

    pools = [
        PoolConfig(
            filepath=Path(p["filepath"]),
            count=p["count"],
            points=p.get("points"),
        )
        for p in data.get("pools", [])
    ]

    exact_file_str = data.get("exact_file")
    exact_file = Path(exact_file_str) if exact_file_str else None

    # A config saved before the font size setting existed has no font_size key.
    font_size = data.get("font_size", "medium")
    if font_size not in FONT_SIZES:
        font_size = "medium"

    config = BuildConfig(
        title=data.get("title", ""),
        course=data.get("course", ""),
        num_versions=data.get("num_versions", 1),
        shuffle_questions=data.get("shuffle_questions", False),
        shuffle_answers=data.get("shuffle_answers", False),
        exact_file=exact_file,
        pools=pools,
        version_question=data.get("version_question", False),
        version_question_position=data.get("version_question_position", "last"),
        default_points=data.get("default_points", 1.0),
        same_questions=data.get("same_questions", False),
        font_size=font_size,
    )

    output_folder = Path(data.get("output_folder", ""))
    return config, output_folder


def load_versions(path: Path) -> list[ExamVersion]:
    """The exam recorded by save_config, or [] if the file holds settings only."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [_version_from_dict(v) for v in data.get("versions", [])]


def _version_to_dict(version: ExamVersion) -> dict:
    questions = []
    for q in version.questions:
        q_data = asdict(q)
        q_data["source_folder"] = str(q.source_folder) if q.source_folder else None
        questions.append(q_data)
    return {
        "title": version.title,
        "course": version.course,
        "version_num": version.version_num,
        "source_folder": str(version.source_folder),
        "questions": questions,
    }


def _version_from_dict(data: dict) -> ExamVersion:
    return ExamVersion(
        title=data["title"],
        course=data["course"],
        version_num=data["version_num"],
        questions=[_question_from_dict(q) for q in data["questions"]],
        source_folder=Path(data["source_folder"]),
    )


def _question_from_dict(data: dict) -> Question:
    return Question(
        q_type=data["q_type"],
        text=data["text"],
        answers=[Answer(**a) for a in data["answers"]],
        dropdowns=[Dropdown(name=d["name"], answers=[Answer(**a) for a in d["answers"]])
                   for d in data["dropdowns"]],
        order_items=[OrderItem(**item) for item in data["order_items"]],
        order_top_label=data["order_top_label"],
        order_bottom_label=data["order_bottom_label"],
        match_lefts=[MatchLeft(**left) for left in data["match_lefts"]],
        match_rights=[MatchRight(**right) for right in data["match_rights"]],
        image_paths=data["image_paths"],
        points=data["points"],
        source_text=data["source_text"],
        source_folder=Path(data["source_folder"]) if data["source_folder"] else None,
        # An exam saved before questions recorded their place in the bank has none
        source_id=data.get("source_id", ""),
    )
