#!/usr/bin/env python3
"""Verify the generated runtime bundle the way the app actually reads it.

`build_data_bundles.py` validates the *sources*; this script validates the
*output* in ``app/src/main/assets``, which is what the WebView loads. It needs no
third-party packages, so it can be run right after a build on any machine:

    python tools/build_data_bundles.py
    python tools/verify_runtime_bundle.py

Checks performed for every subject
==================================

- ``subjects_core.js`` parses and every id is unique.
- ``by_id`` entries agree with ``subjects`` metadata (counts, order).
- question ids are unique and stable-looking (integers).
- every canonical question type is one the app can render, and every option id
  referenced by ``correct_option_ids`` really exists.
- ``matching`` items are consistent (every left item used once, right ids known).
- ``explanations_index.by_id`` maps only real question ids, and every chunk file
  referenced by the index exists in ``subject_data``.
- every id listed in the index appears in exactly one chunk file, and no chunk
  file contains an id the index does not list (this catches renumbered banks and
  leftover files from an older build).
- orphan ``subject_data/*.js`` files that no index references are reported.

Progress safety is checked too: a shrinking bank is safe because the app drops
unknown ids, but a *changed* id silently loses that item's history.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "src" / "main" / "assets"
DATA = ASSETS / "subject_data"

CANONICAL_TYPES = {"single_choice", "multiple_choice", "open_text", "matching", "ticket"}

problems: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def load_json_assignment(path: Path, var: str) -> Any:
    text = path.read_text(encoding="utf-8")
    prefix = f"window.{var}="
    if not text.startswith(prefix):
        fail(f"{path.name}: не начинается с {prefix}")
        return None
    body = text[len(prefix):].strip()
    if body.endswith(";"):
        body = body[:-1]
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        fail(f"{path.name}: не разбирается как JSON ({exc})")
        return None


def load_chunk(path: Path, sid: str, key: str) -> dict[str, Any]:
    """Extract the payload of ``window.EXAM_EXPLANATION_CHUNKS[sid][key]={...}``."""
    text = path.read_text(encoding="utf-8")
    marker = f'["{sid}"][{json.dumps(key)}]='
    idx = text.find(marker)
    if idx < 0:
        fail(f"{path.name}: нет присваивания для {sid}/{key}")
        return {}
    body = text[idx + len(marker):].strip()
    if body.endswith(";"):
        body = body[:-1]
    if not (body.startswith("{") and body.endswith("}")):
        fail(f"{path.name}: полезная нагрузка {sid}/{key} не является объектом")
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        fail(f"{path.name}: полезная нагрузка {sid}/{key} не разбирается ({exc})")
        return {}


def check_question(sid: str, q: dict[str, Any], explanations: dict[str, Any]) -> None:
    qid = q.get("id")
    if not isinstance(qid, int):
        fail(f"{sid}: id вопроса {qid!r} не является целым числом (прогресс ломается)")

    qtype = q.get("type")
    if qtype not in CANONICAL_TYPES:
        fail(f"{sid}/{qid}: тип {qtype!r} не поддерживается приложением")

    if not str(q.get("question") or q.get("ticket") or "").strip():
        fail(f"{sid}/{qid}: пустой текст задания")

    if qtype in {"single_choice", "multiple_choice"}:
        options = q.get("options")
        if not isinstance(options, list) or len(options) < 2:
            fail(f"{sid}/{qid}: вариантов ответа меньше двух")
            return
        ids = [o.get("id") for o in options]
        if len(set(ids)) != len(ids):
            fail(f"{sid}/{qid}: повторяющиеся id вариантов {ids}")
        if any(o.get("correct") for o in options) and not q.get("correct_option_ids"):
            fail(f"{sid}/{qid}: есть correct-варианты, но нет correct_option_ids")
        for cid in q.get("correct_option_ids") or []:
            if cid not in ids:
                fail(f"{sid}/{qid}: correct_option_ids ссылается на несуществующий вариант {cid}")
        correct = [o for o in options if o.get("correct") or o.get("id") in (q.get("correct_option_ids") or [])]
        if qtype == "single_choice" and len(correct) != 1:
            fail(f"{sid}/{qid}: в single_choice правильным помещено {len(correct)} вариантов")
        if qtype == "multiple_choice" and len(correct) < 2:
            fail(f"{sid}/{qid}: в multiple_choice правильным помещено {len(correct)} вариантов")
    elif qtype == "open_text":
        accepted = q.get("accepted_answers")
        if not isinstance(accepted, list) or not accepted:
            fail(f"{sid}/{qid}: open_text без accepted_answers (используйте ticket)")
        elif q.get("case_sensitive"):
            if len(set(accepted)) != len(accepted):
                fail(f"{sid}/{qid}: точные дубли в accepted_answers при case_sensitive")
        else:
            folded = {a.strip().lower().replace("ё", "е") for a in accepted if isinstance(a, str)}
            if len(folded) != len(accepted):
                fail(f"{sid}/{qid}: дубли в accepted_answers, различающиеся только регистром")
    elif qtype == "matching":
        left = q.get("left_items") or []
        right_ids = {r.get("id") for r in (q.get("right_items") or [])}
        mapping = q.get("correct_mapping") or []
        if not left or not right_ids:
            fail(f"{sid}/{qid}: matching без left_items/right_items")
            return
        used_left = [m.get("left_id") for m in mapping]
        if sorted(used_left) != sorted(l.get("id") for l in left):
            fail(f"{sid}/{qid}: каждый левый пункт должен участвовать ровно один раз")
        for m in mapping:
            if m.get("right_id") not in right_ids:
                fail(f"{sid}/{qid}: соответствие ссылается на несуществующий правый пункт {m.get('right_id')}")
    elif qtype == "ticket":
        # A ticket answer may live either in the bank itself or in a lazily loaded
        # explanation chunk; the app shows the same thing in both cases.
        ex = explanations.get(str(q.get("id"))) or {}
        inline = str(q.get("answer_markdown") or "").strip() or str(q.get("answer_text") or "").strip()
        chunked = str(ex.get("ticket_answer_markdown") or ex.get("ticket_answer_text") or "").strip()
        if not (inline or chunked):
            fail(f"{sid}/{qid}: у билета нет ответа ни в банке, ни в разборах — показать его нечем")


def main() -> int:
    catalog_path = ASSETS / "subjects_core.js"
    if not catalog_path.exists():
        fail("subjects_core.js отсутствует: сначала запустите tools/build_data_bundles.py")
    else:
        catalog = load_json_assignment(catalog_path, "EXAM_SUBJECTS")

    if catalog is None:
        pass
    else:
        metas = catalog.get("subjects") or []
        by_id = catalog.get("by_id") or {}
        seen_ids: set[str] = set()
        expected_files: set[Path] = set()

        if not metas:
            fail("в subjects_core.js нет ни одного предмета")
        if sorted(by_id) != sorted(m["id"] for m in metas):
            fail("ключи by_id не совпадают со списком subjects")

        for meta in metas:
            sid = meta.get("id")
            if not sid:
                fail("предмет без id")
                continue
            if sid in seen_ids:
                fail(f"дубль subject.id: {sid}")
            seen_ids.add(sid)

            entry = by_id.get(sid) or {}
            questions = entry.get("questions") or []
            inner_meta = entry.get("subject") or {}

            for key in ("title", "item_count", "question_count", "ticket_count"):
                if inner_meta.get(key) != meta.get(key):
                    fail(f"{sid}: {key} расходится между subjects и by_id.subject")

            if meta.get("item_count") != len(questions):
                fail(f"{sid}: item_count={meta.get('item_count')}, а вопросов {len(questions)}")

            ids: set[int] = set()
            tickets = 0
            groups: set[Any] = set()
            for q in questions:
                if q.get("type") == "ticket":
                    tickets += 1
                    tn = q.get("ticket_number")
                    if tn is not None:
                        groups.add(tn)
                if q.get("id") in ids:
                    fail(f"{sid}: дубль id вопроса {q.get('id')} (прогресс и разборы перемешаются)")
                ids.add(q.get("id"))

            if meta.get("ticket_count") != tickets:
                fail(f"{sid}: ticket_count={meta.get('ticket_count')}, а билетов {tickets}")
            if meta.get("test_question_count") != len(questions) - tickets:
                fail(f"{sid}: test_question_count не совпадает с числом проверяемых вопросов")
            if meta.get("ticket_group_count") != len(groups):
                fail(f"{sid}: ticket_group_count={meta.get('ticket_group_count')}, а групп {len(groups)}")

            index = meta.get("explanations_index") or {}
            index_by_id = index.get("by_id") or {}
            chunks = index.get("chunks") or {}

            # Chunk contents are needed before questions are checked: a ticket may
            # keep its answer in a chunk instead of the bank.
            sid_explanations: dict[str, Any] = {}
            for key, rel in chunks.items():
                chunk_path = ASSETS / rel
                expected_files.add(chunk_path.resolve())
                if not chunk_path.exists():
                    fail(f"{sid}: файл разбора {rel} отсутствует")
                    continue
                for qid, payload in load_chunk(chunk_path, sid, key).items():
                    if index_by_id.get(str(qid)) != key:
                        fail(f"{sid}: разбор {qid} лежит в {key}, но индекс указывает на {index_by_id.get(str(qid))}")
                    if str(qid) in sid_explanations:
                        fail(f"{sid}: разбор {qid} продублирован в {key}")
                    sid_explanations[str(qid)] = payload

            for qid in index_by_id:
                if str(qid) not in {str(i) for i in ids}:
                    fail(f"{sid}: explanations_index ссылается на несуществующий вопрос {qid}")

            for q in questions:
                check_question(sid, q, sid_explanations)

            missing = set(index_by_id) - set(sid_explanations)
            if missing:
                fail(f"{sid}: {len(missing)} разборов из индекса не попали ни в один файл (например {sorted(missing)[:3]})")

            if meta.get("explanation_count") != len(index_by_id):
                fail(f"{sid}: explanation_count={meta.get('explanation_count')}, а в индексе {len(index_by_id)}")
            if index.get("chunk_count") != len(chunks):
                fail(f"{sid}: chunk_count={index.get('chunk_count')}, а чанков {len(chunks)}")

            notes.append(
                f"{sid}: {len(questions)} заданий, {tickets} билетов, "
                f"{len(index_by_id)} разборов в {len(chunks)} файлах"
            )

        # Only meaningful once every subject has declared its files: a leftover chunk
        # is dead weight that would be packaged into every APK build.
        for path in sorted(DATA.glob("*.js")):
            if path.resolve() not in expected_files:
                fail(f"лишний файл {path.name}: его больше не использует ни один предмет")

        progress = catalog.get("progress_compatibility") or {}
        for sid, old_id in progress.get("renamed_from") or {}.items():
            fail(f"внимание: предмет {sid} переименован с {old_id}, прогресс старой версии будет потерян")

    for note in notes:
        print(f"  {note}")
    if problems:
        print(f"ПРОВАЛ: проблем {len(problems)}")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK: сборочный бандл согласован, предметов — {len(notes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())