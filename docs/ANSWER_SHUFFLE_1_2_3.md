# Answer shuffle — 1.2.3

Added an application setting **Варианты ответов → Перемешивать**.

- Applies to single-choice and multiple-choice questions in Learn and Test modes.
- The shuffled order stays stable while the current question is being answered.
- A new order is generated for the next question.
- Correct-answer validation continues to use the original option IDs.
- The setting is stored in localStorage and survives app restarts.
- When shuffle is enabled, visible numbering follows the shuffled display order.

Version: `1.2.3` (`versionCode 15`).
