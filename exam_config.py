"""
exam_config.py

Save and load the full GUI configuration (BuildConfig + output folder) to/from JSON
so that an exam can be easily re-run or reshuffled without re-entering all settings.
"""
from __future__ import annotations

import json
from pathlib import Path

from exam_builder import BuildConfig, PoolConfig

_SCHEMA_VERSION = 1


def save_config(config: BuildConfig, output_folder: Path, dest: Path) -> None:
    """Serialize config + output_folder to a JSON file at dest."""
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
        "source_mode": "pools" if config.pools else "exact",
        "exact_file": str(config.exact_file) if config.exact_file else None,
        "pools": pools_data,
        "output_folder": str(output_folder),
    }
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
    )

    output_folder = Path(data.get("output_folder", ""))
    return config, output_folder
