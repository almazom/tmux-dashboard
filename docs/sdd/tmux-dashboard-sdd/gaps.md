# Tmux Dashboard - Open Gaps & Questions

> Status: ALL FILLED | Last updated: 2026-01-15 (MSK)

## Summary

Total gaps: 12
Filled: 12
Remaining: 0

## Interview Results

### GAP-001: Problem statement

**Question:** Какую проблему решаем?

**Decision:** После SSH входа пользователь всегда попадает в tmux-дашборд; выбор/создание сессий и возврат в дашборд после detach, без доступа к «сырому» shell.

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Пользователь подтвердил tmux-first как ключевое требование.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Автостарт через zsh + exec, attach как дочерний процесс.

---

### GAP-002: Users/roles

**Question:** Кто пользователи и роли?

**Decision:** Единственный пользователь — владелец сервера (один аккаунт, без ролей).

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Прямой ответ пользователя.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Нет ролевой модели.

---

### GAP-003: Goals/success criteria

**Question:** Топ-3 результата?

**Decision:** (1) Вход только через tmux-дашборд, (2) быстрый выбор/создание сессии, (3) возврат в дашборд после detach.

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Принят предложенный вариант.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Основные критерии приемки для E2E.

---

### GAP-004: Timeline

**Question:** Есть ли дедлайн?

**Decision:** Жесткого дедлайна нет.

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Принят предложенный вариант.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Планирование без фиксированной даты.

---

### GAP-005: Constraints

**Question:** Какие есть жесткие ограничения?

**Decision:** Linux, zsh + oh-my-zsh, Python 3.11+, tmux установлен; root доступ есть.

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Прямой ответ пользователя.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Автостарт через zsh, зависимости допустимы.

---

### GAP-006: Scope v1

**Question:** Какой минимальный scope?

**Decision:** Расширенный UI: предпросмотр, поиск/фильтр, горячие клавиши, удаление.

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Пользователь выбрал расширенный набор функций.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Больше UI-компонентов, обязательный help и confirm.

---

### GAP-007: Core flows

**Question:** Топ-3 пользовательских сценария?

**Decision:** (1) SSH → автостарт → поиск/фильтр → attach; (2) создание новой сессии → авто-attach; (3) предпросмотр + удаление → возврат в список, detach возвращает в дашборд.

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Принят предложенный вариант с приоритетом входа в существующие сессии.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Все сценарии отражены в UI Flow и E2E тестах.

---

### GAP-008: Exit behavior (conflict resolution)

**Question:** Можно ли выйти в shell?

**Decision:** Нет, выход из дашборда завершает SSH-сессию (tmux-only).

**Source:** up2u all

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Пользователь выбрал up2u all; применен предложенный вариант для согласованности с tmux-only.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** `q`/Ctrl+C закрывают SSH, без перехода в shell.

---

### GAP-009: Data & integrations

**Question:** Нужны ли данные/интеграции?

**Decision:** Внешних интеграций нет; без БД; только текущее состояние tmux.

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Принят предложенный вариант.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Предпросмотр строится через tmux API, без JSONL логов.

---

### GAP-010: NFR

**Question:** Какие NFR обязательны?

**Decision:** Быстрый отклик (<100мс), корректная работа с ~100 сессиями, graceful fallback без tmux, цветной UI с монохромным fallback, язык UI — English.

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Принят предложенный вариант.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Должно быть отражено в requirements.md и тестах.

---

### GAP-011: Autostart mechanism

**Question:** Чем запускать дашборд после SSH?

**Decision:** `~/.zshrc`/`~/.zprofile` с проверкой интерактивности и `TMUX`.

**Source:** up2u all

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** up2u all, выбран самый простой и совместимый вариант.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** ForceCommand не используется в v1.

---

### GAP-012: Non-goals

**Question:** Что явно НЕ входит в v1?

**Decision:** Нет чтения/анализа JSONL логов Codex/Claude, нет внешних интеграций, нет управления удаленными хостами, нет переименования/бэкапов сессий.

**Source:** user

**Confidence:** 100% (Kimi: n/a, Claude: n/a)

**Short Reason:** Принят предложенный вариант.

**AI Recommendations:**
- Kimi: "not used" (n/a)
- Claude: "not used" (n/a)

**User Approval:** Yes (2026-01-15 17:12 MSK)

**Implementation Notes:** Уточнение по JSONL учитывает комментарий пользователя.

---

## Decisions Based on Project Analysis

Analyzed existing patterns from:
- N/A (repo is empty)

Key pattern alignments:
1. **Greenfield:** нет существующих ограничений по архитектуре.
2. **Docs-first:** все решения фиксируются в SDD.

## Auto-Filled Assumptions

List optional items that were auto-filled from context and confirmed by the user:

- AS-001: Логирование в JSONL с полями `ts/level/event/session_name/message`. (confidence: 90%) - Rationale: базовый стандарт для машиночитаемых логов; подтверждено через up2u all.
- AS-002: Тестовая стратегия = ручной E2E + минимальные unit-тесты для `tmux_manager`. (confidence: 85%) - Rationale: проект зеленый, нет существующей тестовой базы.
- AS-003: Префикс переменных окружения `TMUX_DASHBOARD_`. (confidence: 90%) - Rationale: единый нейминг для конфигурации.
- AS-004: Ошибки показываются в статус-строке и логируются, приложение не падает. (confidence: 85%) - Rationale: соответствует NFR надежности.
- AS-005: Один этап поставки (single-phase). (confidence: 95%) - Rationale: дедлайна нет, scope фиксирован.
