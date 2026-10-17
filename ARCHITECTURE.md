# Architecture Audit

## 1. Scope and Current Technology

This repository is a Linux desktop application for managing independent Chrome profiles.
The current stack is:

- Python 3.11+.
- PySide6 for the desktop UI.
- SQLAlchemy 2.x with SQLite for profile and task configuration.
- APScheduler `BackgroundScheduler` for recurring and one-time tasks.
- `subprocess.Popen` and `psutil` for Chrome process lifecycle management.
- Pydantic 2 for profile input validation.
- `platformdirs` for the per-user application data directory.
- Pytest and Ruff for verification.
- PyInstaller for the Ubuntu executable build.

The current application is a single desktop process. Chrome processes are launched as
child process groups, but there is no application worker process per profile yet.

## 2. Current Project Structure

```text
app/
  main.py                         Application bootstrap and service wiring
  config.py                       AppPaths and SQLite URL
  constants.py                    Profile/task/action string enums
  models/database.py              SQLAlchemy models and initial schema creation
  services/
    browser_detection.py          Detect Chrome/Chromium binaries
    chrome_profile_discovery.py   Discover existing Chrome user-data directories
    chrome_process_service.py     Open, discover, close and restart Chrome
    profile_service.py            Profile CRUD, soft delete and restore
    scheduler_service.py          APScheduler adapter
    task_service.py               Task CRUD and action execution
  ui/
    main_window.py                Main window, page rendering and action wiring
    dialogs/profile_dialog.py     Profile form and validation dialog
  utils/
    paths.py                      Path containment helpers
    validation.py                 ProfileInput and browser argument validation
tests/                            Business/service tests
scripts/                          Install, run, build and desktop launcher scripts
```

The repository also contains generated `build/` and `dist/` artifacts. They are ignored
by Git and should not be treated as source-of-truth runtime code.

## 3. Current Data Storage

`AppPaths.create()` creates, with mode `0700`, the following per-user directories under
`platformdirs.user_data_dir("chrome-profile-manager", "ChromeProfileManager")`:

```text
profiles/   Data directories for profiles created by this app
trash/      Soft-deleted app-owned profile directories
logs/       Plain text application log (`app.log`)
database/   SQLite database (`profiles.db`)
config/     JSON settings (`settings.json`)
```

The database currently has two tables:

### `profiles`

- Identity: `id`, unique `name`.
- Chrome location: `profile_directory`, nullable `user_data_dir`, `browser_type`,
  `browser_binary`.
- UI metadata: `color`, `notes`, `tags`, `important`, `deleted`, `imported`.
- Basic proxy fields: `proxy_enabled`, `proxy_scheme`, `proxy_host`, `proxy_port`.
- Launch fields: `startup_urls`, `extra_arguments`.
- Runtime fields: `status`, `pid`, `last_opened_at`.
- Timestamps: `created_at`, `updated_at`.

`startup_urls` is stored as newline-separated text. `tags` is stored as free-form text.
There is no normalized group, tag, proxy, agent, audit, screenshot or run-history table.

### `tasks`

- Identity and target: `id`, `name`, single required `profile_id`.
- Action: `action_type`, JSON string `payload`.
- Schedule: `schedule_type`, `scheduled_at`, `interval_minutes`.
- Runtime: `enabled`, `status`, `last_run_at`, `next_run_at`, `last_error`.
- Timestamps: `created_at`, `updated_at`.

There is no task execution history table, timeout/retry configuration, multi-profile
target, trigger metadata, or structured task log.

## 4. Current Startup and Control Flow

`app/main.py` currently performs this sequence:

1. Creates `QApplication`.
2. Creates `AppPaths` and the SQLAlchemy session factory.
3. Creates `ChromeProcessService`, then calls `discover()`.
4. Creates `ProfileService`, `TaskService`, and `SchedulerService`.
5. Starts the scheduler and restores persisted tasks.
6. Creates and shows `MainWindow`.
7. Enters the Qt event loop.
8. Stops the scheduler after the event loop exits.

The UI owns a three-second refresh timer. `MainWindow.refresh()` discovers process state,
loads profiles/tasks, rebuilds list widgets, and rewrites logs/settings views.

## 5. How Chrome Is Opened and Closed

### Open

`ChromeProcessService.open(profile_id)`:

1. Loads the profile from the database.
2. Returns early if an in-memory or discovered process appears to be running.
3. Creates the app-owned data directory when needed.
4. Sets `STARTING` and commits.
5. Builds an argument list containing:
   - browser executable;
   - `--user-data-dir` using the imported directory or app-owned profile directory;
   - `--profile-directory`;
   - `--no-remote`;
   - optional proxy server;
   - validated extra arguments;
   - startup URLs.
6. Launches with `shell=False` and `start_new_session=True`.
7. Stores PID and sets `RUNNING`.

### Discover

`discover()` scans all system processes and matches command lines by both
`--user-data-dir` and `--profile-directory`. It writes `RUNNING`/`STOPPED` and PID into
the database. This is useful for recovery after app restart, but currently has no
explicit ownership/session identity and scans all profiles on every refresh.

### Close

`close(profile_id)` resolves the in-memory `Popen` or stored PID, sets `STOPPING`,
terminates the process and recursive children with `psutil`, waits up to five seconds,
kills survivors, then writes `STOPPED` and clears PID. `restart()` calls close, sleeps
briefly, and opens again.

## 6. Existing Functionality That Must Be Preserved

- Discover/import Chrome and Chromium profiles from common Linux locations.
- Create, edit, soft-delete, restore and permanently delete app-owned profiles.
- Protect app-owned profile paths with `ensure_inside`.
- Open, close, restart and open URL for one profile.
- Detect running profiles after application restart.
- Configure startup URLs, extra arguments and basic proxy settings.
- Mark profiles as important and filter/search profiles.
- Create, run, enable/disable and delete tasks.
- Run immediate, once, interval and daily task variants already represented by the code.
- Persist application logs and display settings/log pages.
- Keep system tray behavior and the existing Ubuntu/PyInstaller entry points.

Any schema extension must retain existing columns and rows. Imported Chrome profiles must
continue pointing at their existing `user_data_dir`; migration must never copy or delete
Chrome data implicitly.

## 7. Audit Findings and Refactor Risks

### High priority

1. **Schema evolution is not versioned.** `Base.metadata.create_all()` is combined with
   three ad-hoc `ALTER TABLE` checks for `profiles`. There is no migration table, no
   transactionally ordered migration runner, and no migration for task changes.
2. **UI and services are tightly coupled.** `MainWindow` directly calls process, task,
   scheduler and profile services and polls every three seconds. Long-running or bulk
   work can block the GUI thread.
3. **No isolated worker per profile.** A failure or blocking browser operation in a future
   agent implementation could affect the main process. The target architecture needs
   supervised workers and message-based results.
4. **Task execution is not a durable queue.** The per-profile `RLock` only exists in
   memory, the task is marked `RUNNING` before lock acquisition, and there is no durable
   execution record, timeout, retry policy, or cancellation mechanism.
5. **Scheduler coverage is incomplete.** The UI creates only `immediate` and `interval`
   values, while the service also handles `once` and `daily`. Daily uses an interval
   trigger rather than a calendar/cron trigger, and weekly/event triggers are absent.
6. **`stop_all()` is incomplete after restart.** It only iterates `_processes`, so Chrome
   processes discovered from persisted PIDs are not stopped by that method.

### Medium priority

1. Profile identity, group, tags, proxy, agent state and runtime state are not normalized.
2. `tags`, URLs and task payloads are plain text/JSON strings without structured schemas.
3. Proxy credentials are not modeled. Adding credentials directly to command-line
   arguments would expose secrets through process inspection; a protected secret store or
   OS keyring abstraction is required.
4. Browser binary validation occurs for create/update, but imported profile validation and
   user-data directory health checks are not exposed as a service result.
5. Process matching relies on command-line strings and does not have an explicit launch
   lease or ownership marker. It can be fragile with path normalization and duplicate
   browser instances.
6. Error logging is a plain append-only text file and is not structured, correlated by
   profile/task/action, or separated into user-facing and technical logs.
7. Profile `status` and task `status` are strings without transition guards/state-machine
   functions.
8. `ProfileInput.startup_urls` uses a mutable list default. It is safe in typical Pydantic
   use but should still be changed to a default factory during validation refactor.
9. The close event hides the window instead of exiting. This is intentional tray behavior,
   but the UI needs an explicit distinction between minimize-to-tray and quit.

### Low priority

1. The repository has no fixture factory or sample data for UI testing.
2. UI tests are absent; service tests cover only a small subset of behavior.
3. Generated build artifacts exist locally and can make manual status inspection noisy.

## 8. Target Architecture

```text
Qt UI
├── Profile Manager
├── Bulk Action Manager
├── Proxy Manager
├── Task Manager
├── Agent Manager
└── Live Monitor
          │ commands/events through application facade + event bus
Application Core
├── Profile Service
├── Bulk Action Service
├── Proxy Service
├── Task Service / Scheduler Service
├── Agent Service
├── Approval Service
├── Audit Log Service
└── Emergency Stop Coordinator
          │ repository interfaces
Storage
├── SQLite + versioned migrations
├── Secret Store interface (OS keyring backend later)
└── Artifact store for screenshots/log attachments
Workers
├── Profile Worker (one supervised process per profile)
├── Task Worker
└── Agent Worker
          │ adapters
Adapters
├── Chrome Process Adapter
├── Browser Automation Adapter
├── Screenshot Adapter
├── Page Inspection Adapter
└── Proxy Check Adapter
```

The UI should depend on an application facade and typed events, not on `subprocess`,
`psutil`, SQLAlchemy sessions, or browser automation details. Workers communicate through
typed command/result messages. A worker crash produces a profile-scoped `ERROR` event and
does not crash the Qt process or other profile workers.

## 9. State and Safety Boundaries

### Chrome state

```text
STOPPED -> STARTING -> RUNNING
STARTING -> ERROR
RUNNING -> STOPPING -> STOPPED
RUNNING -> ERROR
ERROR -> STARTING | STOPPED
```

Transitions will be centralized and validated. PID/process discovery is an observation,
not a permission to perform account actions.

### Agent state

Agent state is independent from Chrome state:

```text
DISCONNECTED, IDLE, PLANNING, RUNNING, PAUSED,
WAITING_APPROVAL, ERROR, STOPPED
```

### Permission boundary

The future `ApprovalService` must classify actions as `READ_ONLY`, `NAVIGATE`, `INTERACT`,
`UPLOAD`, `PUBLISH`, `MESSAGE`, and `ACCOUNT_CHANGE`. Upload, publish, message, delete,
account changes, and out-of-plan actions require an approval record before execution.
Emergency stop must cancel queued work, reject waiting actions, and signal the relevant
worker(s).

No feature in this plan includes bypassing captcha, evading detection, simulating human
behavior to defeat website protections, or otherwise circumventing site security.

## 10. Migration Strategy

Before adding new persisted concepts, introduce a small migration runner with a schema
version table and numbered, idempotent migrations. The first migration must represent the
existing schema baseline without changing existing data. Later migrations should:

- add nullable/defaulted columns first;
- backfill derived values deterministically;
- create new tables and indexes transactionally where SQLite permits;
- preserve imported `user_data_dir` and app-owned paths;
- never store plaintext proxy passwords in logs;
- provide a backup/rollback operational instruction for incompatible changes.

The legacy `create_session_factory()` API should remain usable while it delegates schema
initialization to the migration runner.

## 11. Verification Baseline

Current baseline checks:

```bash
.venv/bin/pytest
.venv/bin/ruff check app tests
```

The current test suite contains seven tests covering basic discovery, path safety, profile
CRUD/trash, task execution, process command construction and input validation. It does not
yet cover concurrency, state transitions, scheduler retries/timeouts, proxy checks,
permissions, approvals or worker isolation.
