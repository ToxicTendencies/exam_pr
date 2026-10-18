# Startup fix — 1.0.2

Исправлена нативная Android-сборка, из-за которой версия 1.0.1 могла устанавливаться, но завершаться сбоем при запуске.

Причина: предыдущий APK содержал нативные файлы не из текущего проекта: старый `MainActivity` другого шаблона и фактически пустой `resources.arsc` без Android resource package.

В 1.0.2:
- package: `app.examtraining`;
- versionCode: `4`;
- versionName: `1.0.2`;
- используется рабочая нативная оболочка с `LocalOnlyWebViewClient` и `ThemeBridge`;
- `resources.arsc` содержит полноценный resource package;
- APK выровнен `zipalign` до подписи;
- подпись выполнена стандартным `apksigner`;
- v1/v2/v3 signatures проверены;
- UI smoke test проходит.
