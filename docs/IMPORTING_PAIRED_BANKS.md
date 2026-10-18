# Подключение отдельных банков билетов и тестов

Начиная с версии 1.3.0 сборщик понимает не только один самодостаточный JSON предмета, но и **манифест предмета**, который подключает несколько исходных банков.

Это удобно, когда:

- билеты с развёрнутыми ответами находятся в одном файле;
- тестовые вопросы находятся во втором файле;
- оба файла большие и их не хочется вручную объединять или переписывать.

## Готовый пример в проекте

Биология подключена так:

```text
data/
├── imports/
│   └── biology/
│       ├── biology_tickets.json
│       └── biology_tests.json
└── subjects/
    └── biology.json
```

`data/subjects/biology.json` — небольшой манифест:

```json
{
  "schema_version": "2.2-subject-import",
  "subject": {
    "id": "biology",
    "title": "Биология",
    "language": "ru",
    "order": 20
  },
  "imports": [
    {
      "path": "../imports/biology/biology_tickets.json",
      "format": "exam_tickets_v1",
      "id_offset": 0
    },
    {
      "path": "../imports/biology/biology_tests.json",
      "format": "exam_tests_v1",
      "id_offset": 10000
    }
  ]
}
```

После добавления файлов выполняется обычная команда:

```bash
python3 tools/build_data_bundles.py
```

## Поддерживаемые форматы импорта

### `exam_tickets_v1`

Предназначен для банков, где записи выглядят так:

```json
{
  "id": 1,
  "type": "open_text",
  "question": "Формулировка билета",
  "accepted_answers": [],
  "answer": {
    "answer_text": "Полный ответ",
    "answer_markdown": "**Полный ответ** с разметкой"
  }
}
```

Сборщик автоматически преобразует такую запись в тип `ticket`. Пустой массив `accepted_answers` не используется для автоматической проверки: пользователь читает ответ и вручную выбирает «Знаю» или «Повторить».

### `exam_tests_v1`

Предназначен для банков `single_choice` и `multiple_choice` с полями:

- `options`;
- `correct_option_ids` или `correct: true` у вариантов;
- `explanation`;
- при наличии — `ticket_number`, `ticket_question_number`, `topic`, `subtopic`, `difficulty`, `skill`.

Последние поля сохраняются в runtime-данных. Приложение показывает номер билета, ищет по теме и позволяет собрать тест только по выбранному билету.

### `canonical`

Подключает другой файл, уже записанный в основном формате `2.2-subject-bank`.

### `auto`

Сборщик определяет формат автоматически:

- `open_text` + пустые `accepted_answers` + вложенный `answer` → `exam_tickets_v1`;
- только `single_choice`/`multiple_choice` с `options` → `exam_tests_v1`;
- иначе → `canonical`.

Для релизного проекта лучше указывать формат явно.

## Зачем нужен `id_offset`

ID всех элементов одного предмета должны быть уникальными. Если билеты имеют ID `1–59`, а тесты — `1–1281`, без смещения возникнет конфликт.

В биологии используется:

```text
билеты: 1–59
тесты: 10001–11281
```

Это достигается `id_offset: 10000` для тестового файла.

После выпуска **не меняйте** `subject.id`, исходные ID и `id_offset`: по итоговому runtime ID хранится пользовательский прогресс.

## Где лежат шаблоны

```text
templates/ПРИМЕР_И_ШАБЛОН_БАНКА.json
templates/paired_bank_example/subject_manifest.json
templates/paired_bank_example/tickets.json
templates/paired_bank_example/tests.json
```

Первый файл — самодостаточный банк со всеми поддерживаемыми типами заданий. Папка `paired_bank_example` показывает вариант с отдельными файлами билетов и тестов.
