# Chipyard Data Collection Specification

## Overview

When a user builds and runs a Chipyard configuration (simulator run or benchmark), key results and metadata are recorded in a shared database. Each build and each run becomes a row in the database, with pointers to stored artifacts. All data is saved under a central directory (configurable, default `/scratch/chipyard-data`). Logging is opt-out per user, controlled by `.chipyard/config.json` or a command line flag. This design is intentionally non invasive: it does not modify core Chipyard code or `env.sh`, only adds post build and post run hooks to call a Python logging tool.

## Configuration (`.chipyard/config.json`)

Store this file at the root of the Chipyard repo (`$CHIPYARD_ROOT/.chipyard/config.json`). It contains default settings for data collection.

Example fields:

- `enable_data_collection`: `"on"` or `"off"`  
  The user’s persistent opt-in/opt-out. When created via `datacoll-setup.py`, the default is group-based: `"on"` if `git user.email` ends with `berkeley.edu` or the machine IP is in Berkeley ranges; otherwise `"off"`.

- `db_path`: string  
  Filesystem path to the SQLite database file (for example `"/scratch/chipyard-data/chipyard.db"`).

- `artifact_dir`: string  
  Base directory to copy logs and artifacts (for example `"/scratch/chipyard-data"`).

- `build_dir`: string  
  Subdirectory under `artifact_dir` for build outputs (default `"builds"`).

- `log_dir`: string  
  Subdirectory under `artifact_dir` for run logs (default `"logs"`).

These can be overridden at runtime. For example, running `make ... DATACOLL=on` will temporarily turn data collection on for that run, regardless of `enable_data_collection`. If `DATACOLL=off`, it will turn it off. If unset, use the value in `config.json`. This provides the requested tri state override: default, on, off.

## Integration Points (Makefile Hooks)

A shared fragment `sims/data-collection.mk` is included from `common.mk`. It defines a `log_data_post_run` macro that invokes `util/log_data.py` after each run. The hook is appended to `%.run`, `%.run.fast`, and `$(output_dir)/%.run` rules in `common.mk`. Make always calls the script; the script reads `DATACOLL` and config to decide whether to collect. Both Verilator and VCS inherit these rules. Thus, an example `make` command that a user can run in the terminal is:
```shell
# Example: run a binary under Verilator and collect data for this run only
make CONFIG=RocketConfig BINARY=../../tests/hello.riscv DATACOLL=on run-binary
```

Users can also do `DATACOLL=off` or just leave `DATACOLL` unset so that the script must fall back to the persistent default in `.chipyard/config.json`.

Here, `log_data.py` is the Python tool that receives config name, benchmark, log path, and simulator from the Makefile (as CLI args), gathers Git state, copies and parses the log file, and records everything.

Do not modify `env.sh`.

The script `scripts/datacoll-setup.py` creates or updates `.chipyard/config.json`. It is invoked by `scripts/build-setup.sh` during setup. When run interactively (TTY), it prompts the user: Yes (enable), No (disable), or Enter (use group-based default). In non-interactive mode or when stdin is not a TTY, it uses the group-based default without prompting. Build-setup supports `--datacoll=on`, `--datacoll=off`, or `--datacoll=default` to set `DATACOLL` for that invocation; the script reads `DATACOLL` and skips the prompt when it is set.

## Database Schema

Define two main tables, `builds` and `runs`, with an optional `metrics` field for extensibility.

### `builds` table

One row per unique `(commit, config)` build.

Columns:

- `id` (INTEGER PRIMARY KEY)

- `commit_hash` (TEXT)  
  The Git SHA of Chipyard at build time

- `branch` (TEXT)  
  Git branch name

- `remote_url` (TEXT)  
  Git remote (to distinguish upstream vs fork)

- `is_dirty` (BOOLEAN)  
  True if the working tree had uncommitted changes when building

- `config` (TEXT)  
  Chipyard config name (for example `RocketConfig`)

- `build_path` (TEXT)  
  Path to the built simulator or executable (relative or absolute)

- `user` (TEXT), `host` (TEXT)  
  Who and where it was built

- `timestamp` (DATETIME)  
  When the build completed

### `runs` table

One row per simulation or test run.

Columns:

- `id` (INTEGER PRIMARY KEY)

- `build_id` (INTEGER)  
  Foreign key to `builds.id` (if this run used a known build)

- `commit_hash`, `branch`, `remote_url`, `is_dirty`  
  Repeat of repo info (in case the run is recorded separately)

- `config` (TEXT)  
  Config name (repeat, for easy queries)

- `benchmark` (TEXT)  
  Name of the benchmark or test suite (for example `"rv64ui-p-simple"` or custom)

- `cycles`, `instructions` (INTEGER)  
  Raw cycle and instruction counts (if available)

- `ipc`, `cpi` (REAL)  
  Derived metrics (instructions per cycle, cycles per instruction)

- `metrics` (JSON or TEXT)  
  Stores any additional counters (cache misses, branch mispredictions, top down categories, user defined PerfCounter values). This allows arbitrary key value metrics per run.

- `log_path` (TEXT)  
  Filepath to the copied simulation log in `artifact_dir`

- `run_dir` (TEXT)  
  Absolute path to the simulator directory (e.g. `/path/to/chipyard/sims/verilator`)

- `simulator` (TEXT)  
  Simulator name (e.g. `"verilator"`, `"vcs"`)

- `github_user` (TEXT)  
  GitHub user or org extracted from `remote.origin.url` (e.g. `"ucb-bar"`, `"reed-nicolas"`)

- `user`, `host` (TEXT)  
  Who ran it (Unix user, hostname)

- `timestamp` (DATETIME)  
  When the run was executed

All SQL data types above are generic (SQLite or Postgres supported). In SQLite, the `metrics` field can store a JSON encoded string. In Postgres it could be a JSONB column. By default the schema is SQLite, but it should be compatible with Postgres if migrated later.

## Artifact Storage Layout

Under the base `artifact_dir` (for example `/scratch/chipyard-data`), organize files as follows:

- `chipyard.db`  
  The SQLite database file (`db_path`).

- `builds/`  
  Subdirectory for build outputs. Each build gets its own folder or named file, for example `builds/<commit>_<config>/`. The compiled simulator binary and any related files are stored here. The DB’s `builds.build_path` points into this directory.

- `logs/`  
  Subdirectory for run logs. After a simulation, copy the simulator’s stdout log into `logs/` and record its new path in `runs.log_path`. For example:  
  `logs/2026-03-04_15-30-10_alice_RocketConfig_helloworld.log`  
  (timestamp, user, config, bench in the filename)

- Future: other subdirectories can hold waveforms or counter CSVs, if needed. This spec focuses on textual logs and metrics.

All artifact paths saved in the DB should be absolute or relative under `artifact_dir`, not under the user’s private directory, so that data is centrally accessible.

## Logging Workflow

### Before run

On starting a build or run, the Python script gathers context:

- Git commit and branch, and checks `git diff` to set `is_dirty`
- Chipyard config name and benchmark or test name
- `$(USER)` and hostname

### Execute simulation

Let Chipyard run as usual (this creates a log, for example `simulator-<config>.log`).

### After run

The Makefile hook invokes `log_data.py`.

The script:

- Copies the log file into `$artifact_dir/logs/` with a unique name.
- Parses basic metrics (cycles, instructions, perf counters) from the log or from simulator output.
- Opens the SQLite DB and inserts a row into `runs`, filling in all columns.
- If this is the first time this build or config was seen, it also inserts into `builds`.
- If a matching `(commit_hash, config)` already exists in `builds`, it uses that id and does not duplicate.

### Build sharing

If a build is needed:

- First query:  
  ```sql
  SELECT id, build_path FROM builds WHERE commit_hash=? AND config=?
  ```

  - If found, use that `build_path` (skip rebuilding) and note reuse.
- Otherwise, perform the build and then insert a new row in `builds`.

This enables different users to share one build output. In v0 this is a best effort approach. Concurrent locks can be added later.

## Opt out flow

Logging is opt-out per user (default on).

### Persistent setting

The user edits `.chipyard/config.json` to set `enable_data_collection` to `"off"` to disable logging by default. When created via `datacoll-setup.py`, the default is group-based: `"on"` if `git user.email` ends with `berkeley.edu` or the machine IP is in Berkeley ranges; otherwise `"off"`. (Future: default may use additional signals.)

### Per run override

A Make variable (for example `DATACOLL`) or environment variable can override:

- `make CONFIG=Foo DATACOLL=on run-asm-tests` will collect data on that run even if the json setting is off.
- `DATACOLL=off` forces no logging.
- Unset means follow the json setting.

### Consent tracking

The DB itself may have a table of users and their opt out status (future). For now, trust `enable_data_collection`.

## Schema (Example)

### Table `builds`

Records each unique build.

- `id` (INTEGER PK)
- `commit_hash` (TEXT), `branch` (TEXT), `remote_url` (TEXT), `is_dirty` (BOOLEAN)
- `config` (TEXT)
- `build_path` (TEXT)  
  Where the simulator binary lives
- `user` (TEXT), `host` (TEXT), `timestamp` (DATETIME)

### Table `runs`

Records each run.

- `id` (INTEGER PK)
- `build_id` (INTEGER, FK to `builds.id`)
- `commit_hash`, `branch`, `remote_url`, `is_dirty` (as above)
- `config` (TEXT), `benchmark` (TEXT)
- `cycles` (INTEGER), `instructions` (INTEGER), `ipc` (REAL), `cpi` (REAL)
- `metrics` (JSON or TEXT)  
  All other counters and user metrics (cache misses, TMA categories, etc.)
- `log_path` (TEXT)  
  Path to the copied run log file
- `run_dir` (TEXT), `simulator` (TEXT), `github_user` (TEXT)
- `user`, `host`, `timestamp` (as above)

This schema assumes SQLite, but uses common types so it could be ported to Postgres later. For example, `metrics` can be TEXT in SQLite and JSONB in Postgres.

## Future and Ray compatibility (TBD)

### Ray integration

The schema is compatible with Ray Data’s SQL reading (which uses the Python DB API). In future, we may centralize the DB or export it to a Ray compatible store.

### Performance counters

Plan to include fields for all canonical counters (cycle, instr, cache, branch). Additional counters (for example top down microarchitecture categories from Icicle) or FireSim AutoCounter outputs can go into the `metrics` JSON field.

### Migration to Postgres

When switching, ensure table and column names are valid in Postgres. Run a migration script (or use `pgloader`). Using generic types (INTEGER, REAL, TEXT) minimizes hassles.

### Other TBDs

Handling multi host sync (for example periodic push from hosts to central DB) and NDA flagging can be added later. In this spec, such items are marked TBD or optional placeholders and do not block the v0 workflow.