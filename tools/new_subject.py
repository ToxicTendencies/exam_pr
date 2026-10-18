#!/usr/bin/env python3
"""Create a new, immediately buildable question bank in ``data/subjects/``.

Adding a subject is a data-only operation: the generated bank is validated by
``build_data_bundles.py`` and needs no Java/HTML/CSS/JS changes. This scaffolder
writes a bank that already passes validation, containing one real example of
every requested question type, so the workflow is:

    python tools/new_subject.py --id anatomy --title "Анатомия" --order 30
    python tools/build_data_bundles.py --check     # must pass on the fresh file
    # edit data/subjects/anatomy.json, then rebuild the APK

Types (comma separated, ``all`` for every one):

    single_choice, multiple_choice, open_text, matching, ticket,
    true_false, sequence, card

``true_false``, ``sequence`` and ``card`` are authoring shorthands: the builder
expands them into the canonical types, so they are safe to use in a real bank
too.

The subject id becomes part of saved progress keys. Pick it once and never
change it, otherwise users lose their history for that subject.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUBJECTS_DIR = ROOT / "data" / "subjects"

ALL_TYPES = (
    "single_choice",
    "multiple_choice",
    "open_text",
    "matching",
    "ticket",
    "true_false",
    "sequence",
    "card",
)

ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


def examples_for(qtype: str, qid: int) -> dict[str, Any]:
    """One ready-to-edit example question of the requested type."""
    base: dict[str, Any] = {
        "id": qid,
        "type": qtype,
        "topic": "Тема 1",
        "ticket_number": 1,
        "ticket_question_number": qid,
    }

    if qtype == "single_choice":
        base["question"] = "Текст вопроса с одним правильным ответом"
        # Plain strings are allowed; ids 1..N are assigned automatically.
        base["options"] = ["Первый вариант", "Второй вариант", "Третий вариант", "Четвёртый вариант"]
        base["correct"] = 2
        base["explanation"] = {
            "topic_markdown": "**Разбор темы.** Объясните, почему именно так.",
            "answers_markdown": "Разбор каждого варианта.",
            "correct_answer_markdown": "Правильный ответ — **второй вариант**.",
        }
    elif qtype == "multiple_choice":
        base["question"] = "Текст вопроса с несколькими правильными ответами"
        base["options"] = [
            {"id": 1, "text": "Правильный вариант 1", "correct": True},
            {"id": 2, "text": "Неправильный вариант", "correct": False},
            {"id": 3, "text": "Правильный вариант 2", "correct": True},
        ]
        base["explanation"] = {
            "topic_markdown": "**Разбор темы.**",
            "answers_markdown": "Разбор каждого варианта.",
            "correct_answer_markdown": "Правильные ответы — **1 и 3**.",
        }
    elif qtype == "open_text":
        base["question"] = "Введите термин или короткий ответ"
        base["accepted_answers"] = ["Правильный ответ", "Допустимый вариант"]
        # Set case_sensitive to true only when the capitalisation really matters,
        # otherwise "правильный ответ" and "Правильный ответ" become duplicates.
        base["case_sensitive"] = False
        base["explanation"] = {
            "topic_markdown": "**Разбор темы.**",
            "answers_markdown": "Какие ответы принимаются и почему.",
            "correct_answer_markdown": "Ожидается: **Правильный ответ**.",
        }
    elif qtype == "matching":
        base["question"] = "Установите соответствие между понятием и определением"
        base["left_items"] = [
            {"id": 1, "text": "Понятие 1"},
            {"id": 2, "text": "Понятие 2"},
        ]
        # There may be more right-hand options than pairs: unused ones are distractors.
        base["right_items"] = [
            {"id": 1, "text": "Определение 1"},
            {"id": 2, "text": "Определение 2"},
            {"id": 3, "text": "Лишний вариант"},
        ]
        base["correct_mapping"] = [
            {"left_id": 1, "right_id": 1},
            {"left_id": 2, "right_id": 2},
        ]
        base["explanation"] = {
            "topic_markdown": "**Разбор темы.**",
            "answers_markdown": "Разбор соответствий.",
            "correct_answer_markdown": "1 → 1; 2 → 2.",
        }
    elif qtype == "ticket":
        # A ticket is a memorisation card: the answer is revealed in the app.
        base.pop("ticket_question_number")
        base["ticket"] = "Формулировка билета или тема, на которую нужен развёрнутый ответ"
        base["answer_markdown"] = "**Развёрнутый ответ**\n\nПолный текст ответа на билет."
        base["explanation"] = {}
    elif qtype == "true_false":
        base["question"] = "Верно или неверно: <текст утверждения>"
        # answer may also be "да"/"нет", "верно"/"неверно", 1/0.
        base["answer"] = True
        base["explanation"] = {
            "topic_markdown": "**Разбор темы.**",
            "answers_markdown": "Почему утверждение верно или неверно.",
            "correct_answer_markdown": "**Верно.**",
        }
    elif qtype == "sequence":
        base["question"] = "Расположите этапы в правильном порядке"
        base["steps"] = ["Первый этап", "Второй этап", "Третий этап"]
        # correct_order holds 1..N: steps[i] belongs at position correct_order[i].
        # Writing 1,2,3 means "the steps are already listed in the right order".
        base["correct_order"] = [1, 2, 3]
        base["explanation"] = {
            "topic_markdown": "**Разбор темы.**",
            "answers_markdown": "Почему порядок именно такой.",
            "correct_answer_markdown": "1 → 2 → 3.",
        }
    elif qtype == "card":
        base.pop("ticket_question_number")
        base["front"] = "Термин или вопрос на лицевой стороне карточки"
        base["back"] = "**Определение** на обратной стороне. Поддерживается простой markdown."
        base["explanation"] = {}
    else:  # pragma: no cover - guarded by argparse choices
        raise ValueError(qtype)
    return base


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Создать новый банк вопросов в data/subjects/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Пример:\n  python tools/new_subject.py --id anatomy --title \"Анатомия\" --order 30",
    )
    parser.add_argument("--id", required=True, help="латинский id предмета, например anatomy")
    parser.add_argument("--title", required=True, help="название, которое увидит пользователь")
    parser.add_argument("--order", type=int, default=100, help="позиция в списке предметов (меньше — выше)")
    parser.add_argument("--language", default="ru", help="язык интерфейса банка, по умолчанию ru")
    parser.add_argument(
        "--types",
        default="all",
        help="типы примеров через запятую либо all (по умолчанию)",
    )
    parser.add_argument("--force", action="store_true", help="перезаписать существующий файл")
    parser.add_argument(
        "--out",
        help="куда записать банк вместо data/subjects/<id>.json (например, для шаблона)",
    )
    args = parser.parse_args()

    if not ID_RE.match(args.id):
        print(f"Ошибка: id должен быть латиницей в нижнем регистре, начиная с буквы: {args.id!r}", file=sys.stderr)
        print("Примеры: anatomy, pediatrics, ob_znakomstva", file=sys.stderr)
        return 2

    requested = ALL_TYPES if args.types.strip().lower() == "all" else tuple(
        t.strip() for t in args.types.split(",") if t.strip()
    )
    unknown = [t for t in requested if t not in ALL_TYPES]
    if unknown:
        print(f"Ошибка: неизвестные типы: {', '.join(unknown)}", file=sys.stderr)
        print(f"Доступны: {', '.join(ALL_TYPES)}", file=sys.stderr)
        return 2

    SUBJECTS_DIR.mkdir(parents=True, exist_ok=True)
    target = Path(args.out).resolve() if args.out else SUBJECTS_DIR / f"{args.id}.json"
    relative = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
    if target.exists() and not args.force:
        print(f"Ошибка: {relative} уже существует.", file=sys.stderr)
        print(
            "Внимание: смена id ломает прогресс пользователей. Если нужен другой id —\n"
            "переименуйте файл и удалите его вручную, либо используйте --force с тем же id.",
            file=sys.stderr,
        )
        return 1

    bank = {
        "schema_version": "2.2-subject-bank",
        "subject": {
            "id": args.id,
            "title": args.title,
            "language": args.language,
            "order": args.order,
        },
        "questions": [examples_for(qtype, i) for i, qtype in enumerate(requested, start=1)],
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Создан {relative}")
    print(f"  предмет: {args.title} (id={args.id}, order={args.order})")
    print(f"  примеров: {len(requested)} ({', '.join(requested)})")
    print()
    print("Дальше:")
    print("  1. python tools/build_data_bundles.py --check")
    print(f"  2. отредактируйте {relative}")
    print("  3. python tools/build_data_bundles.py")
    print("  4. пересоберите APK")
    return 0


if __name__ == "__main__":
    sys.exit(main())