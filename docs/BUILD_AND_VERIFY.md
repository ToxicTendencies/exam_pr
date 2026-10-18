# ExamTraining — сборка и проверка

## Перед сборкой: сформировать данные предметов

Из корня проекта:

```bash
python tools/build_data_bundles.py
```

или:

```bash
python3 tools/build_data_bundles.py
```

Скрипт сканирует `data/subjects/*.json`, игнорирует файлы с `_` в начале и создаёт runtime assets.

Если в JSON есть ошибка структуры, сборка данных завершается с понятным сообщением и APK собирать не следует.

## Android Studio

Проект использует Android Gradle Plugin 8.7.3 и Gradle 8.9.

Открывать корневую папку проекта.

### Debug

```bash
./gradlew assembleDebug
```

### Release

```bash
./gradlew assembleRelease
```

Release-ключ не включён в source ZIP. Для release используйте постоянный keystore проекта.

## Проверка интерфейса

```bash
python tools/ui_smoke_test.py
```

Smoke test временно добавляет тестовый второй предмет, проверяет переключение, независимый прогресс, соответствия, билеты, исключение билетов из автоматического теста и разборы, после чего удаляет тестовый предмет и восстанавливает runtime assets из настоящих JSON.

## Что должно быть в assets после генерации

```text
app/src/main/assets/
├── app.js
├── index.html
├── styles.css
├── subjects_core.js
└── subject_data/
    └── <subject_id>_explanations.js
```

Старые `questions_core.js` и `explanations_data.js` больше не используются.
