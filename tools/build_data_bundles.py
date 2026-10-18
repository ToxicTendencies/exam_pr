#!/usr/bin/env python3
"""Build the offline runtime data bundles for every exam bank in data/subjects/.

Why this script exists
======================

The Android app is a thin WebView shell. Everything the user studies lives in
``app/src/main/assets`` and is generated from human-edited JSON banks:

    data/subjects/<subject>.json      ->  app/src/main/assets/subjects_core.js
    (long answers / walkthroughs)      ->  app/src/main/assets/subject_data/<id>_ex_NNN.js

Adding a new subject is intentionally a pure data operation: drop a JSON bank in
``data/subjects/``, run this script, rebuild the APK. No Java, HTML, CSS or JS
changes are ever required, and the app has no in-app "import bank" screen.

Accepted source layouts
=======================

1. A self-contained bank (``schema_version: 2.2-subject-bank``)::

       data/subjects/<subject>.json

2. A manifest (``schema_version: 2.2-subject-import``) that pulls in several
   external banks, e.g. tickets kept apart from test questions::

       data/subjects/<subject>.json
       data/imports/<subject>/tickets.json
       data/imports/<subject>/tests.json

Files and folders whose name starts with ``_`` are treated as templates and are
skipped, so templates can live next to real banks.

Question types
==============

Canonical runtime types (what the app understands)::

    single_choice    one correct option
    multiple_choice  several correct options
    open_text        typed answer, compared against accepted_answers
    matching         left/right correspondence
    ticket           memorisation card with a revealed answer

Authoring shorthands are expanded into the canonical types by this script, so a
bank can be written in whichever style is most convenient::

    true_false  / boolean   -> single_choice with two options
    sequence    / ordering  -> matching where every position is used once
    card        / flashcard -> ticket

Useful conveniences
===================

- ``id`` may be omitted; stable sequential ids are generated.
- ``options`` may be a plain list of strings (ids 1..N are assigned).
- ``correct`` on an option-less question may be an index or list of indices.
- ticket answers accept ``answer``, ``answer_markdown``, ``answer_text``,
  ``answer_md`` or ``front``/``back`` / ``term``/``definition``.

Progress safety
===============

User progress is keyed by ``subject.id`` + the final runtime question id.
``subject.id``, the source ids and every ``id_offset`` must therefore stay stable
after a release. The app silently drops progress entries whose question no longer
exists, so shrinking a bank is safe, but renumbering loses that item's history.

CLI
===

    python tools/build_data_bundles.py            # generate runtime assets
    python tools/build_data_bundles.py --check    # validate only, write nothing
    python tools/build_data_bundles.py <folder>   # use a different bank folder
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUBJECTS_DIR = ROOT / "data" / "subjects"
ASSETS = ROOT / "app" / "src" / "main" / "assets"
SUBJECT_ASSETS = ASSETS / "subject_data"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Canonical types the app can render.
CANONICAL_TYPES = {"single_choice", "multiple_choice", "open_text", "matching", "ticket"}

# Authoring shorthands -> canonical type.
TYPE_ALIASES = {
    "single_choice": "single_choice", "single": "single_choice", "choice": "single_choice",
    "one_correct": "single_choice", "одиночный": "single_choice",
    "multiple_choice": "multiple_choice", "multiple": "multiple_choice", "multi": "multiple_choice",
    "several": "multiple_choice", "множественный": "multiple_choice",
    "open_text": "open_text", "text": "open_text", "short_answer": "open_text",
    "word": "open_text", "ввод_текста": "open_text",
    "matching": "matching", "match": "matching", "соответствие": "matching",
    "ticket": "ticket", "card": "ticket", "flashcard": "ticket",
    "billet": "ticket", "билет": "ticket",
    "true_false": "true_false", "boolean": "true_false", "yes_no": "true_false",
    "верно_неверно": "true_false",
    "sequence": "sequence", "ordering": "sequence", "порядок": "sequence",
}

IMPORT_FORMATS = {"auto", "canonical", "exam_tickets_v1", "exam_tests_v1", "exam_cards_v1"}

TRUE_WORDS = {"true", "yes", "y", "1", "да", "истина", "верно", "+"}
FALSE_WORDS = {"false", "no", "n", "0", "нет", "ложь", "неверно", "-"}

# Explanations are split into chunks so the WebView never parses one huge file.
# A chunk prefers to hold every question of the same exam ticket; it is closed once
# it would exceed CHUNK_TARGET_BYTES, which keeps a single script load small on
# mid-range phones while still avoiding dozens of tiny requests.
CHUNK_TARGET_BYTES = 300_000
CHUNK_MIN_ITEMS = 8

# Compact metadata that is useful in the UI. Large provenance objects stay in the
# source JSON and never reach the runtime bundle.
OPTIONAL_INT_FIELDS = ("source_id", "ticket_number", "ticket_question_number", "source_exam_question_id")
OPTIONAL_TEXT_FIELDS = ("topic", "subtopic", "difficulty", "skill", "title")
OPTIONAL_LIST_FIELDS = ("tags",)


# --------------------------------------------------------------------------- #
# diagnostics
# --------------------------------------------------------------------------- #

def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class Ctx:
    """Collects every problem in a bank instead of stopping at the first one."""

    def __init__(self) -> None:
        self.errors: list[tuple[str, str, str | None]] = []

    def err(self, path: Path, message: str, hint: str | None = None) -> None:
        self.errors.append((rel(path), message, hint))

    def ok(self) -> bool:
        return not self.errors

    def raise_if_failed(self) -> None:
        if not self.errors:
            return
        lines = []
        for where, message, hint in self.errors:
            lines.append(f"{where}: {message}")
            if hint:
                lines.append(f"    подсказка: {hint}")
        raise SystemExit(
            "Сборка данных не выполнена, найдено проблем: %d\n%s" % (len(self.errors), "\n".join(lines))
        )


def fail(path: Path, message: str) -> None:
    raise SystemExit(f"{rel(path)}: {message}")


def read_json(path: Path, ctx: Ctx) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        ctx.err(path, "файл не найден")
        return None
    except json.JSONDecodeError as exc:
        ctx.err(path, "некорректный JSON: строка %d, столбец %d — %s" % (exc.lineno, exc.colno, exc.msg))
        return None
    if not isinstance(data, dict):
        ctx.err(path, "верхний уровень JSON должен быть объектом")
        return None
    return data


def as_int(value: Any, label: str, path: Path, ctx: Ctx) -> int | None:
    if isinstance(value, bool):
        ctx.err(path, f"{label} должен быть целым числом")
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    ctx.err(path, f"{label} должен быть целым числом")
    return None


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def first_text(source: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = clean_text(source.get(key))
        if value:
            return value
    return ""


# --------------------------------------------------------------------------- #
# question normalisation
# --------------------------------------------------------------------------- #

def copy_optional_metadata(core: dict[str, Any], q: dict[str, Any], path: Path, ctx: Ctx) -> None:
    for key in OPTIONAL_INT_FIELDS:
        if key in q and q.get(key) not in (None, ""):
            value = as_int(q.get(key), f"вопрос {core['id']}: поле {key}", path, ctx)
            if value is not None:
                core[key] = value
    for key in OPTIONAL_TEXT_FIELDS:
        value = clean_text(q.get(key))
        if value:
            core[key] = value
    for key in OPTIONAL_LIST_FIELDS:
        value = q.get(key)
        if isinstance(value, list):
            items = [clean_text(x) for x in value if clean_text(x)]
            if items:
                core[key] = items


def canonical_type(raw: Any, path: Path, qid: Any, ctx: Ctx) -> str | None:
    key = clean_text(raw).lower().replace(" ", "_").replace("-", "_")
    if not key:
        ctx.err(path, f"вопрос {qid}: не указан type")
        return None
    if key not in TYPE_ALIASES:
        ctx.err(
            path,
            f"вопрос {qid}: неизвестный тип {raw!r}",
            "допустимо: " + ", ".join(sorted(CANONICAL_TYPES)) + " (или сокращения true_false, sequence, card)",
        )
        return None
    return TYPE_ALIASES[key]


def expand_true_false(q: dict[str, Any]) -> None:
    """Turn ``type: true_false`` into a two-option single_choice question."""
    raw = q.get("correct")
    if raw is None:
        raw = q.get("answer")
    truth: bool | None = None
    if isinstance(raw, bool):
        truth = raw
    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        truth = bool(raw)
    elif isinstance(raw, str):
        token = raw.strip().lower()
        if token in TRUE_WORDS:
            truth = True
        elif token in FALSE_WORDS:
            truth = False
    if truth is None:
        raise ValueError("для true_false нужно поле correct (true/false) со значением ответа")
    true_label = clean_text(q.get("true_label")) or "да"
    false_label = clean_text(q.get("false_label")) or "нет"
    q["options"] = [
        {"id": 1, "text": true_label, "correct": truth},
        {"id": 2, "text": false_label, "correct": not truth},
    ]
    q["correct_option_ids"] = [1 if truth else 2]
    q["type"] = "single_choice"


def expand_sequence(q: dict[str, Any]) -> None:
    """Turn ``type: sequence`` into a matching question with unique positions."""
    items = q.get("items") or q.get("steps") or []
    if not isinstance(items, list) or not items:
        raise ValueError("для sequence нужен непустой массив items (шаги в случайном порядке)")
    order = q.get("correct_order") or q.get("order") or []
    if not isinstance(order, list) or not order:
        raise ValueError("для sequence нужен correct_order — правильные номера шагов (1..N)")
    if len(order) != len(items):
        raise ValueError(f"correct_order содержит {len(order)} значений, а items — {len(items)}")
    positions = []
    for value in order:
        try:
            positions.append(int(value))
        except Exception:
            raise ValueError("correct_order должен состоять только из целых чисел") from None
    if sorted(positions) != list(range(1, len(items) + 1)):
        raise ValueError("correct_order должен быть перестановкой чисел 1..N без повторов")
    texts = [clean_text(x) for x in items]
    if not all(texts):
        raise ValueError("все шаги items должны быть непустым текстом")
    q["left_items"] = [{"id": i + 1, "text": texts[i]} for i in range(len(items))]
    q["right_items"] = [{"id": i + 1, "text": str(i + 1)} for i in range(len(items))]
    q["correct_mapping"] = [{"left_id": i + 1, "right_id": positions[i]} for i in range(len(items))]
    q["type"] = "matching"


def expand_card(q: dict[str, Any]) -> None:
    """Turn ``type: card`` into a ticket, accepting front/back style fields."""
    front = first_text(q, ("front", "term", "question", "ticket"))
    back = first_text(q, ("back", "definition", "answer_text", "answer_markdown"))
    if not back:
        nested = q.get("answer")
        if isinstance(nested, str):
            back = nested.strip()
        elif isinstance(nested, dict):
            back = first_text(nested, ("answer_markdown", "answer_md", "markdown", "answer_text", "text"))
    if not back:
        raise ValueError("для card нужен ответ: back / definition / answer / answer_markdown / answer_text")
    q["type"] = "ticket"
    q["ticket"] = front
    q["answer_markdown"] = back


def ticket_answer_fields(q: dict[str, Any]) -> tuple[str, str]:
    markdown = first_text(q, ("answer_markdown", "answer_md"))
    text = first_text(q, ("answer_text",))
    if not markdown and not text:
        nested = q.get("answer")
        if isinstance(nested, str):
            text = nested.strip()
        elif isinstance(nested, dict):
            markdown = first_text(nested, ("answer_markdown", "answer_md", "markdown"))
            text = first_text(nested, ("answer_text", "text"))
    if not markdown and not text:
        back = first_text(q, ("back", "definition"))
        if back:
            markdown = back
    return markdown, text


def normalize_options(
    q: dict[str, Any], qtype: str, qid: int, path: Path, ctx: Ctx
) -> tuple[list[dict[str, Any]], list[int]] | None:
    raw_options = q.get("options")
    if raw_options is None:
        raw_options = q.get("answers")
    if not isinstance(raw_options, list) or len(raw_options) < 2:
        ctx.err(path, f"вопрос {qid}: нужно минимум 2 варианта ответа в options")
        return None

    # Convenience form: options as plain strings plus correct index/indices.
    if all(isinstance(o, str) for o in raw_options):
        texts = [clean_text(o) for o in raw_options]
        indices: list[int] = []
        explicit = q.get("correct_option_ids")
        if explicit is None:
            explicit = q.get("correct")
        if isinstance(explicit, bool):
            explicit = None
        if isinstance(explicit, (int, float)):
            indices = [int(explicit)]
        elif isinstance(explicit, list):
            for value in explicit:
                try:
                    indices.append(int(value))
                except Exception:
                    ctx.err(path, f"вопрос {qid}: correct_option_ids должен содержать целые числа")
                    return None
        elif explicit is not None:
            ctx.err(path, f"вопрос {qid}: correct_option_ids должен быть числом или массивом чисел")
            return None
        if not indices:
            ctx.err(
                path,
                f"вопрос {qid}: варианты заданы текстом, поэтому нужен correct_option_ids или correct (номера с 1)",
            )
            return None
        if any(i < 1 or i > len(texts) for i in indices):
            ctx.err(path, f"вопрос {qid}: correct_option_ids ссылается на несуществующий вариант")
            return None
        raw_options = [{"id": i + 1, "text": texts[i], "correct": (i + 1) in indices} for i in range(len(texts))]

    seen: set[int] = set()
    normalized: list[dict[str, Any]] = []
    derived: list[int] = []
    for option in raw_options:
        if not isinstance(option, dict):
            ctx.err(path, f"вопрос {qid}: каждый вариант ответа должен быть объектом")
            return None
        oid = as_int(option.get("id"), f"вопрос {qid}: id варианта", path, ctx)
        if oid is None:
            return None
        if oid in seen:
            ctx.err(path, f"вопрос {qid}: повторяющийся id варианта {oid}")
            return None
        seen.add(oid)
        otext = clean_text(option.get("text") or option.get("title"))
        if not otext:
            ctx.err(path, f"вопрос {qid}: у варианта {oid} пустой текст")
            return None
        correct = bool(option.get("correct", False))
        normalized.append({"id": oid, "text": otext, "correct": correct})
        if correct:
            derived.append(oid)

    correct_ids = q.get("correct_option_ids")
    if correct_ids is None:
        correct_ids = derived
    elif isinstance(correct_ids, list):
        parsed: list[int] = []
        for value in correct_ids:
            parsed_id = as_int(value, f"вопрос {qid}: correct_option_ids", path, ctx)
            if parsed_id is None:
                return None
            parsed.append(parsed_id)
        correct_ids = parsed
    else:
        ctx.err(path, f"вопрос {qid}: correct_option_ids должен быть массивом")
        return None

    if len(set(correct_ids)) != len(correct_ids):
        ctx.err(path, f"вопрос {qid}: повторяется значение в correct_option_ids")
        return None
    if not correct_ids:
        ctx.err(path, f"вопрос {qid}: не указан ни один правильный вариант")
        return None
    if any(x not in seen for x in correct_ids):
        ctx.err(path, f"вопрос {qid}: correct_option_ids ссылается на отсутствующий вариант")
        return None
    if qtype == "single_choice" and len(correct_ids) != 1:
        ctx.err(
            path,
            f"вопрос {qid}: у single_choice должен быть ровно один правильный вариант",
            "для нескольких правильных используйте type: multiple_choice",
        )
        return None
    if qtype == "multiple_choice" and len(correct_ids) < 2:
        ctx.err(
            path,
            f"вопрос {qid}: у multiple_choice нужно минимум 2 правильных варианта",
            "для одного правильного используйте type: single_choice",
        )
        return None

    correct_set = set(correct_ids)
    for option in normalized:
        option["correct"] = option["id"] in correct_set
    return normalized, correct_ids


def normalize_matching(q: dict[str, Any], qid: int, path: Path, ctx: Ctx) -> bool:
    left = q.get("left_items") or q.get("left") or []
    right = q.get("right_items") or q.get("right") or []
    mapping = q.get("correct_mapping") or q.get("mapping") or []
    if not isinstance(left, list) or not isinstance(right, list) or not left or not right:
        ctx.err(path, f"вопрос {qid}: matching требует непустые left_items и right_items")
        return False
    if not isinstance(mapping, list):
        ctx.err(path, f"вопрос {qid}: correct_mapping должен быть массивом")
        return False

    def side(items: Any, key: str) -> tuple[list[dict[str, Any]], set[int]] | None:
        seen: set[int] = set()
        out: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                ctx.err(path, f"вопрос {qid}: каждый элемент {key} должен быть объектом")
                return None
            iid = as_int(item.get("id"), f"вопрос {qid}: id в {key}", path, ctx)
            if iid is None:
                return None
            if iid in seen:
                ctx.err(path, f"вопрос {qid}: повторяющийся id {iid} в {key}")
                return None
            seen.add(iid)
            itext = clean_text(item.get("text") or item.get("title"))
            if not itext:
                ctx.err(path, f"вопрос {qid}: у элемента {iid} в {key} пустой текст")
                return None
            out.append({"id": iid, "text": itext})
        return out, seen

    left_result = side(left, "left_items")
    right_result = side(right, "right_items")
    if left_result is None or right_result is None:
        return False
    norm_left, left_ids = left_result
    norm_right, right_ids = right_result

    norm_map: list[dict[str, int]] = []
    mapped_left: set[int] = set()
    for item in mapping:
        if not isinstance(item, dict):
            ctx.err(path, f"вопрос {qid}: каждый элемент correct_mapping должен быть объектом")
            return False
        lid = as_int(item.get("left_id"), f"вопрос {qid}: left_id", path, ctx)
        rid = as_int(item.get("right_id"), f"вопрос {qid}: right_id", path, ctx)
        if lid is None or rid is None:
            return False
        if lid not in left_ids or rid not in right_ids:
            ctx.err(path, f"вопрос {qid}: correct_mapping ссылается на отсутствующий элемент")
            return False
        if lid in mapped_left:
            ctx.err(path, f"вопрос {qid}: для left_id {lid} указано более одного соответствия")
            return False
        mapped_left.add(lid)
        norm_map.append({"left_id": lid, "right_id": rid})
    if mapped_left != left_ids:
        missing = sorted(left_ids - mapped_left)
        ctx.err(
            path,
            f"вопрос {qid}: не у всех левых позиций есть соответствие",
            f"нет соответствия у left_id: {', '.join(str(x) for x in missing)}",
        )
        return False

    q["left_items"] = norm_left
    q["right_items"] = norm_right
    q["correct_mapping"] = norm_map
    return True


def normalize_question(
    q: dict[str, Any], path: Path, ctx: Ctx | None = None
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Validate one source question and return ``(runtime_core, explanation)``.

    ``ctx`` accumulates problems; without it the first problem raises at once.
    """
    strict = ctx is None
    local = Ctx()
    ctx = ctx or local

    qid_raw = q.get("id")
    qid = as_int(qid_raw, "id вопроса", path, ctx) if qid_raw is not None else -1
    label = qid_raw if qid_raw is not None else "?"
    qtype = canonical_type(q.get("type"), path, label, ctx)
    if qtype is None:
        return None if not strict else fail(path, f"вопрос {label}: неизвестный тип {q.get('type')!r}")

    if qtype == "true_false":
        try:
            expand_true_false(q)
        except ValueError as exc:
            ctx.err(path, f"вопрос {label}: {exc}")
            return None if not strict else fail(path, f"вопрос {label}: {exc}")
        qtype = "single_choice"
    elif qtype == "sequence":
        try:
            expand_sequence(q)
        except ValueError as exc:
            ctx.err(path, f"вопрос {label}: {exc}")
            return None if not strict else fail(path, f"вопрос {label}: {exc}")
        qtype = "matching"
    elif qtype == "ticket":
        try:
            expand_card(q)
        except ValueError as exc:
            ctx.err(path, f"вопрос {label}: {exc}")
            return None if not strict else fail(path, f"вопрос {label}: {exc}")

    if qtype == "ticket":
        text = first_text(q, ("ticket", "question", "front", "term"))
    else:
        text = clean_text(q.get("question") or q.get("text"))
    if not text:
        ctx.err(path, f"вопрос {label}: пустой текст вопроса")
        return None if not strict else fail(path, f"вопрос {label}: пустой текст вопроса")

    core: dict[str, Any] = {"id": qid, "type": qtype, "question": text}
    copy_optional_metadata(core, q, path, ctx)

    if qtype in {"single_choice", "multiple_choice"}:
        result = normalize_options(q, qtype, qid, path, ctx)
        if result is None:
            return None if not strict else fail(path, f"вопрос {qid}: некорректные варианты ответа")
        core["options"], core["correct_option_ids"] = result
    elif qtype == "open_text":
        accepted_raw = q.get("accepted_answers")
        if accepted_raw is None:
            accepted_raw = q.get("answers")
        if isinstance(accepted_raw, str):
            accepted_raw = [accepted_raw]
        if not isinstance(accepted_raw, list):
            ctx.err(path, f"вопрос {qid}: accepted_answers должен быть массивом строк")
            return None if not strict else fail(path, f"вопрос {qid}: accepted_answers должен быть массивом строк")
        accepted = [clean_text(x) for x in accepted_raw if clean_text(x)]
        if not accepted:
            ctx.err(
                path,
                f"вопрос {qid}: accepted_answers пуст",
                "если ответ не проверяется автоматически, используйте type: ticket",
            )
            return None if not strict else fail(path, f"вопрос {qid}: accepted_answers пуст")
        core["accepted_answers"] = accepted
        if "case_sensitive" in q:
            core["case_sensitive"] = bool(q.get("case_sensitive"))
        # Case-insensitive answers that differ only by case are redundant noise, but
        # with case_sensitive: true they are legitimately different answers.
        if not core.get("case_sensitive"):
            if len({norm_text(a) for a in accepted}) != len(accepted):
                ctx.err(
                    path,
                    f"вопрос {qid}: accepted_answers содержит дубли, совпадающие без учёта регистра",
                    "уберите лишние варианты или поставьте case_sensitive: true",
                )
                return None if not strict else fail(path, f"вопрос {qid}: дубли в accepted_answers")
        elif len(set(accepted)) != len(accepted):
            ctx.err(path, f"вопрос {qid}: accepted_answers содержит точные дубли")
            return None if not strict else fail(path, f"вопрос {qid}: точные дубли в accepted_answers")
    elif qtype == "ticket":
        answer_markdown, answer_text = ticket_answer_fields(q)
        if not answer_markdown and not answer_text:
            ctx.err(
                path,
                f"вопрос {qid}: билету нужен ответ",
                "подойдут answer_markdown, answer_text, answer (строка или объект) либо back/definition",
            )
            return None if not strict else fail(path, f"вопрос {qid}: билету нужен ответ")
    elif qtype == "matching":
        if not normalize_matching(q, qid, path, ctx):
            return None if not strict else fail(path, f"вопрос {qid}: некорректное соответствие")
        # normalize_matching rewrites q in place; the runtime entry needs its own copy
        # because core is a fresh dict and would otherwise lose the whole question.
        core["left_items"] = q["left_items"]
        core["right_items"] = q["right_items"]
        core["correct_mapping"] = q["correct_mapping"]

    explanation = q.get("explanation")
    if explanation is None and (q.get("explanation_markdown") or q.get("explanation_text")):
        explanation = {
            "answers_markdown": clean_text(q.get("explanation_markdown")),
            "correct_answer_markdown": clean_text(q.get("explanation_text")),
        }
    if explanation is not None and not isinstance(explanation, dict):
        ctx.err(path, f"вопрос {qid}: explanation должен быть объектом")
        return None if not strict else fail(path, f"вопрос {qid}: explanation должен быть объектом")
    if qtype == "ticket":
        explanation = dict(explanation or {})
        answer_markdown, answer_text = ticket_answer_fields(q)
        if answer_markdown:
            explanation["ticket_answer_markdown"] = answer_markdown
        if answer_text:
            explanation["ticket_answer_text"] = answer_text
    return core, explanation


def norm_text(value: str) -> str:
    return str(value or "").strip().lower().replace("\u0451", "\u0435")


# --------------------------------------------------------------------------- #
# imports
# --------------------------------------------------------------------------- #

def infer_import_format(data: dict[str, Any], path: Path) -> str:
    questions = data.get("questions") or []
    ticket_like = True
    test_like = True
    card_like = True
    for q in questions:
        if not isinstance(q, dict):
            continue
        nested_answer = q.get("answer") if isinstance(q.get("answer"), dict) else {}
        has_answer = bool(
            clean_text(q.get("answer_markdown"))
            or clean_text(q.get("answer_text"))
            or clean_text(q.get("back"))
            or clean_text(nested_answer.get("answer_markdown"))
            or clean_text(nested_answer.get("answer_text"))
        )
        accepted = [clean_text(x) for x in (q.get("accepted_answers") or []) if clean_text(x)]
        raw_type = clean_text(q.get("type")).lower()
        if raw_type != "open_text" or accepted or not has_answer:
            ticket_like = False
        if raw_type not in {"single_choice", "multiple_choice"} or not isinstance(q.get("options"), list):
            test_like = False
        if raw_type not in {"card", "flashcard", "ticket"} or not has_answer:
            card_like = False
    if ticket_like:
        return "exam_tickets_v1"
    if card_like:
        return "exam_cards_v1"
    if test_like:
        return "exam_tests_v1"
    return "canonical"


def adapt_card_question(q: dict[str, Any], offset: int, path: Path) -> dict[str, Any]:
    original_id = as_int(q.get("id"), "id карточки", path, Ctx())
    if original_id is None:
        raise ValueError("у карточки отсутствует числовой id")
    nested = q.get("answer") if isinstance(q.get("answer"), dict) else {}
    answer_markdown = clean_text(q.get("answer_markdown") or nested.get("answer_markdown") or q.get("back"))
    answer_text = clean_text(q.get("answer_text") or nested.get("answer_text"))
    if not answer_markdown and not answer_text:
        raise ValueError(f"карточка {original_id}: не найден ответ (back / answer / answer_markdown / answer_text)")
    source = q.get("source") if isinstance(q.get("source"), dict) else {}
    out: dict[str, Any] = {
        "id": original_id + offset,
        "source_id": original_id,
        "type": "ticket",
        "ticket": clean_text(q.get("front") or q.get("term") or q.get("question")),
        "ticket_number": q.get("ticket_number") or source.get("original_number") or original_id,
        "topic": clean_text(q.get("topic") or q.get("question") or q.get("front")),
    }
    if not out["ticket"]:
        raise ValueError(f"карточка {original_id}: пустой текст (front / term / question)")
    if answer_markdown:
        out["answer_markdown"] = answer_markdown
    if answer_text:
        out["answer_text"] = answer_text
    if isinstance(q.get("tags"), list):
        out["tags"] = q["tags"]
    return out


def adapt_ticket_question(q: dict[str, Any], offset: int, path: Path) -> dict[str, Any]:
    original_id = as_int(q.get("id"), "id билета", path, Ctx())
    if original_id is None:
        raise ValueError("у билета отсутствует числовой id")
    nested_answer = q.get("answer") if isinstance(q.get("answer"), dict) else {}
    answer_markdown = clean_text(q.get("answer_markdown") or nested_answer.get("answer_markdown"))
    answer_text = clean_text(q.get("answer_text") or nested_answer.get("answer_text"))
    if not answer_markdown and not answer_text:
        raise ValueError(f"билет {original_id}: нет ответа в answer / answer_markdown / answer_text")

    source = q.get("source") if isinstance(q.get("source"), dict) else {}
    ticket_number = q.get("ticket_number") or source.get("original_number") or original_id
    out: dict[str, Any] = {
        "id": original_id + offset,
        "source_id": original_id,
        "type": "ticket",
        "ticket": clean_text(q.get("ticket") or q.get("question")),
        "ticket_number": ticket_number,
        "topic": clean_text(q.get("topic") or q.get("question")),
    }
    if not out["ticket"]:
        raise ValueError(f"билет {original_id}: пустой текст вопроса")
    if answer_markdown:
        out["answer_markdown"] = answer_markdown
    if answer_text:
        out["answer_text"] = answer_text
    if isinstance(q.get("tags"), list):
        out["tags"] = q["tags"]
    return out


def adapt_import_questions(
    data: dict[str, Any],
    import_format: str,
    offset: int,
    path: Path,
) -> list[dict[str, Any]]:
    questions = data.get("questions") or []
    if not isinstance(questions, list) or not questions:
        raise ValueError("questions пуст")
    if import_format == "auto":
        import_format = infer_import_format(data, path)
    if import_format not in IMPORT_FORMATS - {"auto"}:
        raise ValueError(f"неподдерживаемый формат импорта {import_format!r}")

    result: list[dict[str, Any]] = []
    for q in questions:
        if not isinstance(q, dict):
            raise ValueError("каждый импортируемый вопрос должен быть объектом")
        if import_format == "exam_tickets_v1":
            result.append(adapt_ticket_question(q, offset, path))
        elif import_format == "exam_cards_v1":
            result.append(adapt_card_question(q, offset, path))
        else:
            out = dict(q)
            original_id = as_int(q.get("id"), "id импортируемого вопроса", path, Ctx())
            if original_id is None:
                raise ValueError("у вопроса отсутствует числовой id")
            out["id"] = original_id + offset
            if offset and "source_id" not in out:
                out["source_id"] = original_id
            result.append(out)
    return result


def imported_path(manifest_path: Path, value: Any, ctx: Ctx) -> Path | None:
    raw = clean_text(value)
    if not raw:
        ctx.err(manifest_path, "пустой путь в imports")
        return None
    candidate = (manifest_path.parent / raw).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        ctx.err(manifest_path, f"путь импорта должен оставаться внутри проекта: {raw}")
        return None
    if not candidate.is_file():
        ctx.err(manifest_path, f"файл импорта не найден: {raw}")
        return None
    return candidate


def collect_source_questions(
    data: dict[str, Any], path: Path, ctx: Ctx
) -> tuple[list[dict[str, Any]], list[Path]] | None:
    questions_raw = data.get("questions") or []
    if questions_raw and not isinstance(questions_raw, list):
        ctx.err(path, "questions должен быть массивом")
        return None
    questions: list[dict[str, Any]] = list(questions_raw)
    source_files: list[Path] = [path]

    imports = data.get("imports") or []
    if imports and not isinstance(imports, list):
        ctx.err(path, "imports должен быть массивом")
        return None
    for index, descriptor in enumerate(imports, 1):
        if not isinstance(descriptor, dict):
            ctx.err(path, f"imports #{index} должен быть объектом")
            return None
        source_path = imported_path(path, descriptor.get("path"), ctx)
        if source_path is None:
            return None
        source_data = read_json(source_path, ctx)
        if source_data is None:
            return None
        import_format = clean_text(descriptor.get("format") or descriptor.get("kind") or "auto")
        if import_format not in IMPORT_FORMATS:
            ctx.err(path, f"imports #{index}: неподдерживаемый формат {import_format!r}")
            return None
        offset = as_int(descriptor.get("id_offset", 0), f"imports #{index}: id_offset", path, ctx)
        if offset is None:
            return None
        try:
            questions.extend(adapt_import_questions(source_data, import_format, offset, source_path))
        except ValueError as exc:
            ctx.err(source_path, str(exc))
            return None
        source_files.append(source_path)
    return questions, source_files


def assign_missing_ids(questions: list[dict[str, Any]], path: Path, ctx: Ctx) -> bool:
    """Give every id-less question a stable sequential id that cannot collide."""
    reserved: set[int] = set()
    for q in questions:
        if isinstance(q, dict) and q.get("id") is not None:
            value = as_int(q.get("id"), "id вопроса", path, ctx)
            if value is None:
                return False
            reserved.add(value)
    nxt = 1
    for q in questions:
        if not isinstance(q, dict):
            ctx.err(path, "каждый вопрос должен быть объектом")
            return False
        if q.get("id") is None:
            while nxt in reserved:
                nxt += 1
            q["id"] = nxt
            reserved.add(nxt)
    return True


def composite_source_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(rel(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# explanation chunking
# --------------------------------------------------------------------------- #

def plan_explanation_chunks(
    core_questions: list[dict[str, Any]], explanations: dict[str, dict[str, Any]]
) -> tuple[dict[str, list[int]], list[str]]:
    """Group explained questions into load-once chunks.

    Questions that belong to the same exam ticket are gathered first, then every
    group is closed once it would exceed CHUNK_TARGET_BYTES. A group is never
    smaller than CHUNK_MIN_ITEMS (unless it is the very last piece), so a large
    ticket stays readable instead of turning into dozens of tiny requests.
    """
    logical: dict[str, list[int]] = {}
    order: list[str] = []
    batch: list[int] = []

    for q in core_questions:
        qid = q["id"]
        if str(qid) not in explanations:
            continue
        ticket_number = q.get("ticket_number")
        if ticket_number is None:
            batch.append(qid)
            continue
        key = f"t{ticket_number}"
        if key not in logical:
            logical[key] = []
            order.append(key)
        logical[key].append(qid)
    if batch:
        logical["b"] = batch
        order.append("b")

    groups: dict[str, list[int]] = {}
    chunks: list[str] = []

    def emit(base: str, items: list[int]) -> None:
        key = f"{base}_{len(chunks):03d}"
        groups[key] = items
        chunks.append(key)

    for base in order:
        items = logical[base]
        current: list[int] = []
        current_bytes = 0
        for qid in items:
            size = len(compact(explanations[str(qid)]).encode("utf-8"))
            oversized = current and current_bytes + size > CHUNK_TARGET_BYTES
            if oversized and len(current) >= CHUNK_MIN_ITEMS:
                emit(base, current)
                current = []
                current_bytes = 0
            current.append(qid)
            current_bytes += size
        if current:
            emit(base, current)
    return groups, chunks


# --------------------------------------------------------------------------- #
# subject loading
# --------------------------------------------------------------------------- #

def load_subject(
    path: Path, ctx: Ctx | None = None
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], list[Path]] | None:
    strict = ctx is None
    local = Ctx()
    ctx = ctx or local

    data = read_json(path, ctx)
    if data is None:
        return None if not strict else fail(path, "не удалось прочитать файл")

    subject = data.get("subject") or {}
    if not isinstance(subject, dict):
        ctx.err(path, "subject должен быть объектом")
        return None if not strict else fail(path, "subject должен быть объектом")
    sid = clean_text(subject.get("id") or path.stem).lower()
    if not ID_RE.fullmatch(sid):
        ctx.err(
            path,
            f"недопустимый subject.id {sid!r}",
            "разрешены латинские строчные буквы, цифры, '_' и '-'",
        )
        return None if not strict else fail(path, f"недопустимый subject.id {sid!r}")
    title = clean_text(subject.get("title"))
    if not title:
        dataset = data.get("dataset") if isinstance(data.get("dataset"), dict) else {}
        title = clean_text(dataset.get("title") or path.stem)
    dataset = data.get("dataset") if isinstance(data.get("dataset"), dict) else {}
    language = clean_text(subject.get("language") or dataset.get("language") or "ru")

    collected = collect_source_questions(data, path, ctx)
    if collected is None:
        return None if not strict else fail(path, "не удалось прочитать источники вопросов")
    questions, source_files = collected
    if not questions:
        ctx.err(
            path,
            "в предмете нет ни одного задания",
            "минимальный вопрос: {\"id\": 1, \"type\": \"ticket\", \"ticket\": \"...\", \"answer_markdown\": \"...\"}; "
            "готовый банк создаёт команда: python tools/new_subject.py --id <id> --title \"<название>\"",
        )
        return None if not strict else fail(path, "в предмете нет ни одного задания")
    if not assign_missing_ids(questions, path, ctx):
        return None if not strict else fail(path, "не удалось назначить id")

    core_questions: list[dict[str, Any]] = []
    explanations: dict[str, dict[str, Any]] = {}
    seen_ids: set[int] = set()
    for q in questions:
        result = normalize_question(q, path, ctx)
        if result is None:
            continue
        core, explanation = result
        qid = core["id"]
        if qid in seen_ids:
            ctx.err(
                path,
                f"повторяющийся итоговый id вопроса {qid}",
                "разведите пересекающиеся банки через id_offset в imports или задайте уникальные id",
            )
            continue
        seen_ids.add(qid)
        core_questions.append(core)
        if explanation:
            explanations[str(qid)] = explanation

    order = as_int(subject.get("order", 1000), "subject.order", path, ctx)
    if order is None:
        return None if not strict else fail(path, "subject.order должен быть целым числом")
    ticket_count = sum(1 for q in core_questions if q["type"] == "ticket")
    test_question_count = len(core_questions) - ticket_count
    ticket_numbers = sorted({int(q["ticket_number"]) for q in core_questions if q.get("ticket_number") is not None})

    chunk_groups, chunk_order = plan_explanation_chunks(core_questions, explanations)
    chunk_files: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for index, key in enumerate(chunk_order):
        chunk_files[key] = f"subject_data/{sid}_ex_{index:03d}.js"
        for qid in chunk_groups[key]:
            by_id[str(qid)] = key

    meta = {
        "id": sid,
        "title": title,
        "language": language,
        "order": order,
        "item_count": len(core_questions),
        "question_count": len(core_questions),
        "ticket_count": ticket_count,
        "test_question_count": test_question_count,
        "ticket_group_count": len(ticket_numbers),
        "explanation_count": len(explanations),
        "explanations_script": "",
        "explanations_index": {
            "count": len(explanations),
            "chunk_count": len(chunk_order),
            "complete": len(explanations) == len(core_questions),
            "chunks": chunk_files,
            "by_id": by_id,
        },
        "canonical_sha256": composite_source_hash(source_files),
    }
    runtime = {"subject": meta, "questions": core_questions}
    return sid, meta, runtime, explanations, source_files


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def discover_banks(subject_dir: Path) -> list[Path]:
    files = []
    for path in sorted(subject_dir.rglob("*.json")):
        relative = path.relative_to(subject_dir)
        parts = relative.parts
        if any(part.startswith("_") for part in parts):
            continue
        files.append(path)
    return files


def build(check_only: bool = False, quiet: bool = False) -> None:
    ctx = Ctx()
    files = discover_banks(SUBJECTS_DIR)
    if not files:
        raise SystemExit(
            f"В папке {rel(SUBJECTS_DIR)} нет ни одного банка.\n"
            "Скопируйте шаблон: templates/01_bank_all_types.json -> data/subjects/<предмет>.json"
        )

    loaded = []
    seen_subjects: dict[str, Path] = {}
    for path in files:
        result = load_subject(path, ctx)
        if result is None:
            continue
        sid, meta, runtime, explanations, source_files = result
        if sid in seen_subjects:
            ctx.err(
                path,
                f"subject.id {sid!r} уже используется в {rel(seen_subjects[sid])}",
                "у каждого предмета должен быть уникальный id",
            )
            continue
        seen_subjects[sid] = path
        loaded.append((sid, meta, runtime, explanations, source_files))

    ctx.raise_if_failed()

    loaded.sort(key=lambda x: (x[1].get("order", 1000), x[1]["title"].casefold(), x[0]))
    subjects = [x[1] for x in loaded]
    by_id = {x[0]: x[2] for x in loaded}

    if check_only:
        print(f"Проверка пройдена: предметов — {len(subjects)}, все банки валидны.")
        _print_summary(loaded)
        return

    ASSETS.mkdir(parents=True, exist_ok=True)
    import shutil

    if SUBJECT_ASSETS.exists():
        shutil.rmtree(SUBJECT_ASSETS)
    SUBJECT_ASSETS.mkdir(parents=True, exist_ok=True)

    catalog = {
        "schema_version": "1.2-multi-subject-runtime",
        "subjects": subjects,
        "by_id": by_id,
    }
    (ASSETS / "subjects_core.js").write_text(
        "window.EXAM_SUBJECTS=" + compact(catalog) + ";\n", encoding="utf-8"
    )

    expected: set[Path] = set()
    for meta in subjects:
        sid = meta["id"]
        index = meta["explanations_index"]
        explanations_payload = _subject_explanations(sid, loaded, index)
        for chunk_key, rel_path in index["chunks"].items():
            payload = explanations_payload.get(chunk_key, {})
            js = (
                "window.EXAM_EXPLANATION_CHUNKS=window.EXAM_EXPLANATION_CHUNKS||{};"
                f"window.EXAM_EXPLANATION_CHUNKS[{json.dumps(sid)}]=window.EXAM_EXPLANATION_CHUNKS[{json.dumps(sid)}]||{{}};"
                f"window.EXAM_EXPLANATION_CHUNKS[{json.dumps(sid)}][{json.dumps(chunk_key)}]="
                + compact(payload)
                + ";\n"
            )
            target = ASSETS / rel_path
            target.write_text(js, encoding="utf-8")
            expected.add(target)

    # Chunks are fully generated: drop leftovers from an older build so they are not
    # shipped inside the APK forever.
    stale = [p for p in (ASSETS / "subject_data").glob("*.js") if p not in expected]
    for path in stale:
        path.unlink()

    for legacy in (ASSETS / "questions_core.js", ASSETS / "explanations_data.js"):
        if legacy.exists():
            legacy.unlink()

    print(f"Собрано предметов: {len(subjects)}")
    _print_summary(loaded)
    print(f"  subjects_core.js: {(ASSETS / 'subjects_core.js').stat().st_size:,} байт".replace(",", " "))


def _subject_explanations(
    sid: str, loaded: list, index: dict[str, Any]
) -> dict[str, dict[str, dict[str, Any]]]:
    explanations = next(x[3] for x in loaded if x[0] == sid)
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for qid_str, chunk_key in index["by_id"].items():
        out.setdefault(chunk_key, {})[qid_str] = explanations[qid_str]
    return out


def _print_summary(loaded: list) -> None:
    for sid, meta, _runtime, _explanations, source_files in loaded:
        sources = ", ".join(rel(p) for p in source_files)
        chunks = meta["explanations_index"]["chunk_count"]
        print(
            f"  {sid}: {meta['title']} — {meta['item_count']} заданий "
            f"({meta['ticket_count']} билетов, {meta['test_question_count']} проверяемых), "
            f"разборов {meta['explanation_count']} в {chunks} частях"
        )
        print(f"    источники: {sources}")


def main() -> None:
    args = [a for a in sys.argv[1:]]
    check_only = False
    quiet = False
    for arg in args:
        if arg in ("--check", "-c"):
            check_only = True
        elif arg in ("--quiet", "-q"):
            quiet = True
        elif arg in ("-h", "--help"):
            print(__doc__)
            return
    build(check_only=check_only, quiet=quiet)


if __name__ == "__main__":
    main()
