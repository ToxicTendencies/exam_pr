#!/usr/bin/env python3
"""Verify that the biology manifest imports both source banks without data loss."""
from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "subjects" / "biology.json"
TICKETS = ROOT / "data" / "imports" / "biology" / "biology_tickets.json"
TESTS = ROOT / "data" / "imports" / "biology" / "biology_tests.json"
BUILDER = ROOT / "tools" / "build_data_bundles.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_data_bundles", BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load build_data_bundles.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    builder = load_builder()
    sid, meta, runtime, explanations, source_files = builder.load_subject(MANIFEST)
    source_tickets = read(TICKETS)
    source_tests = read(TESTS)
    questions = runtime["questions"]

    assert sid == "biology"
    assert [p.resolve() for p in source_files] == [MANIFEST.resolve(), TICKETS.resolve(), TESTS.resolve()]
    assert meta["item_count"] == 1340
    assert meta["ticket_count"] == 59
    assert meta["test_question_count"] == 1281
    assert meta["explanation_count"] == 1340
    assert meta["ticket_group_count"] == 59
    assert Counter(q["type"] for q in questions) == {
        "ticket": 59,
        "single_choice": 911,
        "multiple_choice": 370,
    }

    runtime_by_id = {q["id"]: q for q in questions}

    for src in source_tickets["questions"]:
        rid = int(src["id"])
        out = runtime_by_id[rid]
        answer = src.get("answer") or {}
        assert out["type"] == "ticket"
        assert out["source_id"] == rid
        assert out["ticket_number"] == rid
        assert out["question"] == src["question"].strip()
        ex = explanations[str(rid)]
        assert ex.get("ticket_answer_markdown") == answer.get("answer_markdown", "").strip()
        assert ex.get("ticket_answer_text") == answer.get("answer_text", "").strip()

    ticket_counts = Counter()
    for src in source_tests["questions"]:
        source_id = int(src["id"])
        rid = source_id + 10000
        out = runtime_by_id[rid]
        assert out["source_id"] == source_id
        assert out["type"] == src["type"]
        assert out["question"] == src["question"].strip()
        assert out["ticket_number"] == int(src["ticket_number"])
        assert out["ticket_question_number"] == int(src["ticket_question_number"])
        assert out["topic"] == src["topic"].strip()
        assert out["subtopic"] == src["subtopic"].strip()
        assert out["difficulty"] == src["difficulty"].strip()
        assert out["skill"] == src["skill"].strip()
        assert out["options"] == [
            {"id": int(o["id"]), "text": o["text"].strip(), "correct": bool(o.get("correct"))}
            for o in src["options"]
        ]
        assert out["correct_option_ids"] == [int(x) for x in src["correct_option_ids"]]
        assert explanations[str(rid)] == src["explanation"]
        ticket_counts[int(src["ticket_number"])] += 1

    expected_counts = {
        int(k): int(v)
        for k, v in source_tests["dataset"]["question_counts_by_ticket"].items()
    }
    assert dict(sorted(ticket_counts.items())) == dict(sorted(expected_counts.items()))
    assert min(runtime_by_id) == 1
    assert max(runtime_by_id) == 11281
    assert set(range(1, 60)).issubset(runtime_by_id)
    assert set(range(10001, 11282)).issubset(runtime_by_id)

    print(
        "PASS: biology import preserved 59 tickets, 1281 tests, all answers, "
        "all explanations, and ticket grouping 1-59"
    )


if __name__ == "__main__":
    main()
