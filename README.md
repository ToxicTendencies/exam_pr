# ExamTraining

Универсальный Android Studio / Gradle-проект офлайн-тренажёра для нескольких предметов.

## Что поддерживается

- несколько независимых предметов в одном приложении;
- выбор предмета нажатием на его название;
- отдельный прогресс и очередь ошибок для каждого предмета;
- `single_choice`, `multiple_choice`, `open_text`, `matching`, `ticket`;
- сокращения при записи банка: `true_false`, `sequence`, `card`;
- режимы «По порядку», «Случайно», «Только ошибки»;
- билеты с развёрнутым ответом и ручной отметкой «Знаю / Повторить»;
- тесты и полный разбор результатов (билеты в автоматический тест не включаются);
- банк вопросов с поиском и постепенной подгрузкой;
- светлая / тёмная / системная тема;
- пользовательские цвета темы;
- полностью офлайн.

## Требования

- Android Studio;
- JDK 17;
- Android SDK Platform 35;
- Android Build Tools 35.x;
- Python 3 для генерации runtime-данных из JSON.

## Данные предметов

Канонические JSON-файлы находятся в:

```text
data/subjects/
```

Один самодостаточный файл или один манифест = один предмет.

Подключённые предметы:

```text
data/subjects/pharmacology.json
data/subjects/biology.json
data/subjects/pediatrics.json
```

Исходные отдельные банки биологии находятся в `data/imports/biology/` и подключаются манифестом `biology.json`.

### Добавить новый предмет

```bash
python tools/new_subject.py --id anatomy --title "Анатомия" --order 30
```

Команда создаёт `data/subjects/anatomy.json` с одним рабочим примером каждого типа
вопроса (`single_choice`, `multiple_choice`, `open_text`, `matching`, `ticket`,
а также сокращения `true_false`, `sequence`, `card`). Созданный файл сразу проходит
проверку. Дальше отредактируйте его обычным текстовым редактором и пересоберите
данные.

Полезные ключи:

```bash
python tools/new_subject.py --id anatomy --title "Анатомия" --types ticket,card
python tools/new_subject.py --id anatomy --title "Анатомия" --out templates/example.json
```

Шаблоны:

```text
data/subjects/_subject_template.json      минимальный каркас (сборщиком игнорируется)
templates/subject_bank_template.json      пример каждого типа вопроса
templates/tickets_subject_template.json   банк только из билетов
```

Полная инструкция: `docs/SUBJECTS_DATA_FORMAT.md`.

### Пересборка и проверка данных

```bash
python tools/build_data_bundles.py --check   # только проверить, ничего не писать
python tools/build_data_bundles.py           # собрать runtime-файлы в assets
python tools/verify_runtime_bundle.py        # проверить уже собранный бандл
```

Скрипт сам находит все предметы и создаёт runtime-файлы в
`app/src/main/assets/`: `subjects_core.js` и небольшие файлы разборов
`subject_data/<id>_ex_NNN.js`. Разборы грузятся частями по мере надобности, поэтому
большой банк не тормозит при запуске. Устаревшие файлы разборов удаляются при сборке.


## Импорт отдельных банков билетов и тестов

Манифест `schema_version: 2.2-subject-import` может подключать несколько JSON-файлов. Формат `exam_tickets_v1` преобразует записи `open_text` с вложенным объектом `answer` в билеты, а `exam_tests_v1` импортирует тестовые вопросы и сохраняет их группировку по билетам. Подробная инструкция: `docs/IMPORTING_PAIRED_BANKS.md`.

## Сборка

1. Открыть корневую папку проекта в Android Studio.
2. После изменения банка выполнить `python tools/build_data_bundles.py`.
3. Дождаться Gradle Sync.
4. Собрать APK через **Build → Build APK(s)** или `./gradlew assembleDebug`.

## Android-конфигурация

- namespace/applicationId: `app.examtraining`
- minSdk: 23
- targetSdk: 35
- compileSdk: 35
- Java: 17
- разрешения не запрашиваются;
- сетевой доступ WebView заблокирован.

## Важно про прогресс

Прогресс хранится по `subject.id`. Например:

```text
pharmacology
anatomy
biology
```

Поэтому `subject.id` после выпуска предмета лучше не менять. Название `subject.title` менять можно.


## Безопасный выбор цвета

Настройка пользовательских цветов не использует HTML `input type="color"`. Нажатие на цветной образец открывает встроенный редактор RGB + HEX внутри WebView. Это исключает зависимость от системного Android color chooser и предотвращает падение на несовместимых версиях WebView.

## Шаблоны банков данных

Готовые файлы для добавления новых предметов находятся в `templates/`:

- `subject_bank_template.json` — пример каждого типа задания (генерируется `tools/new_subject.py`);
- `tickets_subject_template.json` — предмет с билетами и развёрнутыми ответами;
- `ПРИМЕР_И_ШАБЛОН_БАНКА.json` — разобранный пример с пояснениями;
- `paired_bank_example/` — пример отдельных банков билетов и тестов с манифестом;
- `SUBJECTS_DATA_FORMAT.md` — описание формата и правила добавления предметов.

Рабочие заполненные банки кладутся в `data/subjects/`.

## Проверки

```bash
python tools/build_data_bundles.py --check    # валидация исходных банков
python tools/build_data_bundles.py            # сборка
python tools/verify_runtime_bundle.py         # согласованность собранного бандла
python tools/verify_biology_import.py         # ничего не потерялось при импорте биологии

cd tools/ui_tests
npm install     # один раз, ставит jsdom
npm test        # 103 проверки интерфейса без эмулятора и браузера
```

`tools/ui_tests` поднимает настоящий `index.html` + `app.js` в jsdom с
синтетическим банком, поэтому проверяются реальные экраны, режимы, прогресс,
поиск и ленивая загрузка разборов. Эмулятор и Android Studio не нужны.

Playwright-скрипты `tools/ui_smoke_test.py` и `tools/biology_ui_smoke_test.py`
оставлены как дополнительные проверки в настоящем браузере; им нужен
`playwright install chromium` (путь к браузеру переопределяется через
`CHROMIUM_PATH`).



## Current Android release

Version `1.4.0` (`versionCode 17`). The historical 1.0.2 packaging fix is documented in `docs/STARTUP_FIX.md`; phone startup hardening is documented in `docs/PHONE_STARTUP_FIX_1_2_1.md`; system-theme and test-statistics separation is documented in `docs/THEME_AND_TEST_STATS_1_2_2.md`.


## Safe Android shell

The Android shell is intentionally minimal: a single `Activity` with a local `WebView`. It does not use system color pickers, storage pickers, or network access. A tiny local-only `NativeTheme` JavaScript bridge exposes the Android system dark/light mode and system-bar styling to the bundled offline UI.

Application ID: `app.examtraining`

Release line: `1.4.0`
