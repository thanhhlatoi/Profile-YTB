# Implementation Plan

This plan upgrades the existing application incrementally. Each phase must preserve the
legacy profile/task behavior, pass the verification gate, and update this checklist before
the next phase starts.

## Delivery Rules

- Do not rewrite the application wholesale.
- Keep existing database rows and imported Chrome directories intact.
- Use versioned migrations for every schema change.
- Keep browser operations out of the Qt UI thread.
- Make worker commands/results typed and profile-scoped.
- Do not log proxy credentials or other secrets.
- Require approval for upload, publish, messaging, deletion and account changes.
- Do not implement captcha bypass, detection evasion or security circumvention.
- If a dependency or architectural choice materially changes deployment, stop and ask for
  approval before adding it.

## Phase 0 — Audit and Plan

- [x] Read application source, tests, scripts and dependency configuration.
- [x] Document current technology, structure, storage and Chrome lifecycle.
- [x] Record compatibility requirements and current architectural risks.
- [x] Define target architecture, state boundaries and migration strategy.
- [x] Create `ARCHITECTURE.md`.
- [x] Create this `IMPLEMENTATION_PLAN.md`.
- [x] Run baseline tests and lint after documentation changes.

Exit criteria:

- Audit documents match the implementation.
- No production code changed in Phase 0.
- `pytest`, `ruff check app tests` and `git diff --check` pass.

## Phase 1 — Profile Manager Foundation

Goal: make profile management clear and extensible without breaking old data.

### Data and services

- [ ] Add versioned migration runner and baseline schema version.
- [ ] Add compatible fields for purpose, group, pinned state, agent state, current task,
  proxy reference, last validation and validation error.
- [ ] Decide whether groups/tags are normalized immediately or introduced as a compatible
  normalized model with legacy `tags` retained during transition.
- [ ] Add typed profile validation result for browser binary, user-data directory and proxy.
- [ ] Add profile clone service that never clones imported Chrome data implicitly.
- [ ] Add import/export service for JSON and CSV with schema validation and secret redaction.
- [ ] Add sort/filter query objects for group, tag, Chrome state, Agent state, proxy and
  last run.
- [ ] Centralize Chrome state transitions and process ownership checks.

### UI

- [ ] Replace the profile text list with a card/table view using checkboxes.
- [ ] Show profile ID, name, purpose, group, tags, path, proxy, statuses, last run, current
  task, pinned state, notes and validation warnings.
- [ ] Add profile detail panel with open, close, restart, proxy check, logs, connect agent,
  assign task, pause agent, screenshot, and emergency stop controls.
- [ ] Add clone, pin/unpin, group/tag editing and import/export controls.
- [ ] Preserve search, important filter, context menu, tray and existing CRUD behavior.
- [ ] Add sample/demo data provider for UI development only; never mix it into real data.

### Tests and gate

- [ ] Migration from a legacy database preserves rows and columns.
- [ ] Profile validation returns understandable errors.
- [ ] Clone does not overwrite source or imported data.
- [ ] JSON/CSV round trips preserve supported configuration.
- [ ] Chrome state transitions reject invalid transitions.
- [ ] Run tests, lint and a PyInstaller build.

## Phase 2 — Bulk Action Manager

Goal: execute profile-scoped actions with bounded concurrency and visible results.

- [ ] Add bulk action command/result models.
- [ ] Add configurable start delay and maximum concurrent Chrome count.
- [ ] Add queue cancellation and global emergency stop integration.
- [ ] Add per-profile progress states: queued, running, succeeded, failed, cancelled.
- [ ] Add bulk action and per-profile audit records.
- [ ] Add preset storage for create/list/update/delete and target selection by profile,
  group or tags.
- [ ] Make `stop_all` include discovered processes, not only in-memory processes.
- [ ] Keep bulk orchestration outside the UI thread.

Tests:

- [ ] Concurrency limit is never exceeded.
- [ ] Delay and cancellation work deterministically.
- [ ] One profile failure does not fail unrelated profiles.
- [ ] Every profile receives a result and audit record.

Gate: tests, lint, manual UI smoke test with sample data, PyInstaller build.

## Phase 3 — Proxy Manager

Goal: manage proxy configuration independently and safely.

- [ ] Add versioned `proxies` table and profile-to-proxy assignment model.
- [ ] Store protocol, host, port, masked credential reference, checked IP/country, status,
  timestamps and error reason.
- [ ] Add `ProxyCheckAdapter` interface with a deterministic fake for tests.
- [ ] Add manual proxy check and profile IP check with timeout and cancellation.
- [ ] Detect duplicate checked IPs and surface warnings.
- [ ] Never put proxy username/password in logs or unprotected command-line arguments.
- [ ] Add proxy selection before launch and interface for future scheduled rotation, without
  implementing rotation until an explicit policy is approved.

Tests:

- [ ] Proxy input validation.
- [ ] Timeout/error classification.
- [ ] Duplicate IP detection.
- [ ] Secret redaction in logs and exported configuration.

Gate: tests, lint, build, manual check using fake adapter. Real proxy testing requires
explicit endpoint/provider configuration and must not be hard-coded.

## Phase 4 — Task Scheduler

Goal: separate task definition, scheduling and execution.

- [ ] Introduce `TaskManager` facade so UI does not call scheduler internals.
- [ ] Add task description, target set/group, timeout, retries, backoff and next-run fields.
- [ ] Add task execution history and per-run log records.
- [ ] Support interval, once, daily, weekly and manual triggers.
- [ ] Add profile-start and proxy-ready event triggers through the event bus.
- [ ] Add pause/resume, cancellation and timeout handling.
- [ ] Prevent duplicate execution on the same profile with a durable per-profile lease.
- [ ] Keep legacy single-profile tasks readable and executable during migration.

Tests:

- [ ] Retry/backoff behavior.
- [ ] Timeout behavior.
- [ ] No duplicate task on the same profile.
- [ ] Multi-profile target expansion and partial failure.
- [ ] Scheduler restore after application restart.

Gate: tests, lint, build and restart/recovery smoke test.

## Phase 5 — Internal Agent API and Workers

Goal: create a safe browser-operation abstraction without integrating an LLM.

- [ ] Define typed `AgentService` interface for open, close, restart, navigate, inspect,
  screenshot, click, type, scroll, logs, pause, resume and stop.
- [ ] Define normalized action result with action ID, profile ID, timestamp, status, error,
  optional screenshot reference and sanitized metadata.
- [ ] Implement `BrowserAdapter` boundary; the first adapter may expose only safe lifecycle
  and observation operations.
- [ ] Implement `ApprovalService` interface and policy evaluator before sensitive actions.
- [ ] Implement `AgentWorker`/`ProfileWorker` supervision using process or equivalent
  isolation and a message protocol.
- [ ] Add event bus for worker state/result/error updates.
- [ ] Ensure workers never call Qt objects directly.
- [ ] Add per-profile emergency stop and system-wide stop coordinator.

Tests:

- [ ] Worker crash isolation.
- [ ] Normalized result contract.
- [ ] Command timeout and cancellation.
- [ ] State event delivery.
- [ ] Emergency stop cancels queued and waiting work.

Gate: tests, lint, build, worker lifecycle smoke test. No LLM or autonomous account action.

## Phase 6 — Agent Manager and Task Planning

Goal: allow a user to submit a natural-language task while retaining human control.

- [ ] Add Agent Manager UI with profile selection and task input.
- [ ] Add planner interface returning a reviewable, structured plan.
- [ ] Display planned steps, scope, data inputs, permissions and expected side effects.
- [ ] Require approval before sensitive or out-of-plan actions.
- [ ] Display current step, completed steps, reason, result, error and screenshot.
- [ ] Add pause, resume and stop-now controls.
- [ ] Keep planner/LLM provider behind an adapter; no provider or secret is hard-coded.

Tests:

- [ ] Plan validation and scope enforcement.
- [ ] Approval required for sensitive actions.
- [ ] Out-of-plan action is blocked.
- [ ] Pause/resume/stop behavior.

Gate: tests, lint, build, manual review of a read-only demo task.

## Phase 7 — Permissions, Approval and Emergency Stop

- [ ] Implement permission enum: `READ_ONLY`, `NAVIGATE`, `INTERACT`, `UPLOAD`, `PUBLISH`,
  `MESSAGE`, `ACCOUNT_CHANGE`.
- [ ] Add profile/task permission policies with least-privilege defaults.
- [ ] Add approval modal showing action, reason, profile and data to be used.
- [ ] Persist approve-once/deny decisions and audit trail.
- [ ] Block upload, publish, message, delete and account changes without approval.
- [ ] Block actions outside the approved plan.
- [ ] Add emergency stop per profile and globally, including browser action cancellation.

Tests:

- [ ] Permission matrix.
- [ ] Approval once/deny/expiry.
- [ ] Audit record redaction.
- [ ] Emergency stop propagation.

Gate: tests, lint, build and approval-flow manual test.

## Phase 8 — Monitoring and Operations

- [ ] Add Live Monitor with periodic screenshots or live view where supported.
- [ ] Capture before/after screenshots for important actions.
- [ ] Add user-facing timeline and separate technical logs.
- [ ] Add alerts for timeout, repeated failure, plan deviation, permission violation and
  proxy failure.
- [ ] Add retention/cleanup policy for screenshots and logs.
- [ ] Add health diagnostics for database, browser binary, profile paths and workers.
- [ ] Update README with configuration, proxy, debug, backup, migration and recovery docs.

Tests and gate:

- [ ] Alert classification tests.
- [ ] Artifact retention tests.
- [ ] Monitoring recovery after worker restart.
- [ ] Full test suite, lint and reproducible PyInstaller build.

## Dependency Decisions Requiring Approval Before Implementation

The current stack is sufficient for Phase 1 and most of Phase 2. Before implementing
browser automation or production workers, confirm these choices:

1. **Browser automation backend:** Playwright, Selenium, or another approved adapter.
   Playwright is a strong default for isolated contexts, but adds browser/runtime
   packaging and deployment considerations.
2. **Worker transport:** `multiprocessing` pipes/queues for a local-only app, or a local
   IPC protocol if workers must be independently restartable. Do not introduce a network
   service without a concrete requirement.
3. **Secret storage:** OS keyring backend available on the target Ubuntu environments,
   with an explicit fallback policy. Plaintext JSON/database storage is not acceptable for
   proxy credentials.
4. **Proxy IP provider:** user-configured endpoint/provider and privacy expectations. The
   application must not embed a provider URL, credential or proxy account.
5. **Planner/LLM provider:** local or remote provider, data handling policy, and allowed
   models. Phase 5 does not require this decision.

## Phase Reporting Template

After every implemented phase, report:

- Files changed.
- Data migrations added and compatibility impact.
- Features completed.
- Features intentionally not completed.
- Tests/build/lint commands and exact results.
- Known issues and next phase entry criteria.
