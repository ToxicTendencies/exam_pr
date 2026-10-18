# System theme and isolated test statistics — 1.2.2

## Theme

- Default appearance is `system`.
- Android system night mode is read directly from `Configuration.UI_MODE_NIGHT_MASK` through the local-only `NativeTheme` bridge.
- CSS also has a `prefers-color-scheme: dark` bootstrap so the first WebView frame does not flash the light palette.
- Existing v1 UI settings are migrated to v2: custom palette colors are preserved, while appearance is reset once to `system`.
- Status and navigation bars are synchronized with the active palette.

## Statistics separation

Learning and test statistics are now separate data paths.

Learning answers update only:

- learned/mastered questions;
- learning error queue;
- answered-at-least-once state;
- learning progress percentage.

Test answers no longer call the learning `mark()` function and therefore do not affect learning records or the learning error queue.

Per subject, test statistics store:

- `started`: number of test sessions launched;
- `completed`: number of tests finished through the final question;
- `correct`: total correct answers in test mode;
- `wrong`: total wrong answers in test mode.

The Progress screen shows test attempts in a separate block with started/completed counts and aggregate correct/wrong percentages.

An abandoned test counts as started, but not completed. Answers already submitted in an abandoned test remain part of the aggregate test-answer percentages.

## Migration

Subject state schema moves from v4 to v5. Existing learning records are preserved. Because older versions did not record whether a historical answer came from Learn or Test, old mixed history cannot be reconstructed reliably; the new separate test counters start at zero on v4 → v5 migration.

## Version

- versionCode: `14`
- versionName: `1.2.2`
