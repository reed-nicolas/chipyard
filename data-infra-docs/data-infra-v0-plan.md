# Chipyard Data Collection — v0 Implementation Plan

Based on `data-infra-spec.md`, this plan is a minimal vertical slice that proves logging works for exactly one run target (`run-binary`) before expanding to other simulators or waveform targets.

---

## 1. New Files to Add

| Path | Purpose |
|------|---------|
| `.chipyard/config.json` | Default config (created by `datacoll-setup.py` if missing) |
| `util/log_data.py` | Entrypoint: reads config, resolves DATACOLL tri-state, copies log, parses metrics, inserts into DB |
| `util/datacoll/__init__.py` | Package marker for `from datacoll.config import ...` |
| `util/datacoll/config.py` | Load and merge `.chipyard/config.json` with runtime overrides |
| `util/datacoll/db.py` | DB init, schema creation, migrations, `insert_run`, `get_or_create_build_id` |
| `util/datacoll/schema.sql` | DDL for `builds` and `runs` tables |
| `sims/data-collection.mk` | Defines `DATACOLL`, `log_data_post_run` macro; passes `--simulator $(sim_name)` |
| `scripts/datacoll-setup.py` | Creates/updates `.chipyard/config.json`; interactive prompt (Yes/No/Enter) or flags; Berkeley IP or email default |

---

## 2. Existing Files to Edit

| Path | Edits (high level) |
|------|--------------------|
| `sims/data-collection.mk` | Define `DATACOLL ?= ` (unset). Define `log_data_post_run` macro invoking `log_data.py` with `--config-file`, `--chipyard-config`, `--bench`, `--log-path`, `--sim-dir`, `--simulator $(sim_name)`. |
| `common.mk` | Add `include $(base_dir)/sims/data-collection.mk`. Append `$(call log_data_post_run,...)` to `%.run`, `%.run.fast`, `$(output_dir)/%.run`. |
| `scripts/build-setup.sh` | Add `--datacoll=on|off|default` flag. Call `scripts/datacoll-setup.py --chipyard-dir $CYDIR`; export `DATACOLL` when flag is set so the script skips the interactive prompt. |

**Include chain (verified):**

- `sims/verilator/Makefile`: `include $(base_dir)/variables.mk`, `include $(base_dir)/common.mk`
- `sims/vcs/Makefile`: `include $(base_dir)/variables.mk`, `include $(sim_dir)/vcs.mk`, `include $(base_dir)/common.mk`

Both simulators include `common.mk`, where the `%.run` rule is defined. A single hook there covers Verilator and VCS. Simulator-specific Makefiles do not define their own `%.run`; they inherit it from `common.mk`.

---

## 3. SQLite Schema DDL

```sql
CREATE TABLE IF NOT EXISTS builds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_hash TEXT NOT NULL,
    branch TEXT,
    remote_url TEXT,
    is_dirty INTEGER NOT NULL,  /* 0 or 1, SQLite has no BOOLEAN */
    config TEXT NOT NULL,
    build_path TEXT,
    user TEXT,
    host TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    build_id INTEGER,
    commit_hash TEXT NOT NULL,
    branch TEXT,
    remote_url TEXT,
    is_dirty INTEGER NOT NULL,
    config TEXT NOT NULL,
    benchmark TEXT,
    cycles INTEGER,
    instructions INTEGER,
    ipc REAL,
    cpi REAL,
    metrics TEXT,  /* JSON string for extensibility */
    log_path TEXT,
    run_dir TEXT,      /* absolute path to sim dir (e.g. .../sims/verilator) */
    simulator TEXT,    /* e.g. verilator, vcs */
    github_user TEXT,  /* extracted from remote.origin.url */
    user TEXT,
    host TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (build_id) REFERENCES builds(id)
);

CREATE INDEX IF NOT EXISTS idx_builds_commit_config ON builds(commit_hash, config);
CREATE INDEX IF NOT EXISTS idx_runs_build_id ON runs(build_id);
CREATE INDEX IF NOT EXISTS idx_runs_config_benchmark ON runs(config, benchmark);
```

---

## 4. Artifact Directory Layout under `/scratch/chipyard-data`

```
/scratch/chipyard-data/
├── chipyard.db          # SQLite DB (db_path from config)
├── builds/              # build_dir subdir (future: per-build outputs)
│   └── <commit>_<config>/  # optional in v0; build_path can point to sim_dir
└── logs/                # log_dir subdir
    └── 2026-03-04_15-30-10_<user>_RocketConfig_hello.log
```

**v0 simplification:** `builds/` may remain empty; `build_path` can reference the simulator path in the repo (e.g. `sims/verilator/simulator-chipyard.harness-RocketConfig`). Copying build artifacts is deferred. Only run logs are copied to shared storage. This satisfies “do not point to logs inside private directory”—logs live under `artifact_dir/logs/`. Build sharing (reuse of compiled simulators across users/machines) is **not** proven in v0; `build_path` may remain machine/user-specific until build artifact copying is implemented.

Log filename format: `{timestamp}_{user}_{config}_{bench}.log`  
Example: `2026-03-04_15-30-10_alice_RocketConfig_hello.log`

---

## 5. Tri-State Logic (DATACOLL)

| `DATACOLL` | Behavior |
|------------|----------|
| `on` | Collect regardless of config.json |
| `off` | Never collect |
| unset | Use `enable_data_collection` from config.json (group-based default when created) |

**Implementation:** Make always calls `log_data.py` after run. Script reads config + `DATACOLL` (from env), decides to proceed or no-op. No Make conditionals; done entirely in the script.

---

## 6. End-to-End Test Procedure

Copy-paste commands to validate the v0 vertical slice. Assumes Chipyard is set up (conda/env.sh sourced, RISCV set, toolchain built).

**Default behavior:** When created via `datacoll-setup.py`, `enable_data_collection` uses a group-based default: `"on"` for Berkeley (email or IP); otherwise `"off"`.

### Step 1: Create config.json if missing

```bash
mkdir -p /scratch/reednicolas/chipyard/.chipyard
cat > /scratch/reednicolas/chipyard/.chipyard/config.json << 'EOF'
{
  "enable_data_collection": "on",
  "db_path": "/scratch/chipyard-data/chipyard.db",
  "artifact_dir": "/scratch/chipyard-data",
  "build_dir": "builds",
  "log_dir": "logs"
}
EOF
```

### Step 2: Initialize database and directories

```bash
mkdir -p /scratch/chipyard-data/builds /scratch/chipyard-data/logs
python3 /scratch/reednicolas/chipyard/util/log_data.py --init-db \
  --config-file /scratch/reednicolas/chipyard/.chipyard/config.json
```

*(Alternatively, `log_data.py` can auto-init on first use if `--init-db` is omitted but DB file is missing.)*

### Step 3: Run one simulator command (run-binary)

```bash
cd /scratch/reednicolas/chipyard/sims/verilator
source /scratch/reednicolas/chipyard/env.sh
```

**Option A — riscv-tests (recommended, no build):**  
On Chipyard setups, `$RISCV` is the toolchain install prefix. Tests live directly under it:

```bash
make CONFIG=RocketConfig BINARY=$RISCV/riscv64-unknown-elf/share/riscv-tests/isa/rv64ui-p-simple run-binary
```

**Option B — tests/hello.riscv:**  
Chipyard `tests/` uses CMake, not Make:

```bash
cd /scratch/reednicolas/chipyard/tests && cmake -S . -B build && cmake --build build
cd /scratch/reednicolas/chipyard/sims/verilator
make CONFIG=RocketConfig BINARY=../../tests/build/hello.riscv run-binary
```

*(Branch or toolchain setup may vary; if `tests/` has a different build system, adjust accordingly.)*

### Step 4: Verify DB was populated

```bash
sqlite3 /scratch/chipyard-data/chipyard.db "SELECT id, config, benchmark, log_path, timestamp FROM runs;"
```

Expected output (one row, benchmark name depends on binary used):

```
1|RocketConfig|rv64ui-p-simple|/scratch/chipyard-data/logs/2026-03-04_15-30-10_<user>_RocketConfig_rv64ui-p-simple.log|2026-03-04 15:30:10
```

*(Use `hello` if you ran with tests/build/hello.riscv. Exact timestamp and user will vary.)*

Optional: inspect full row:

```bash
sqlite3 /scratch/chipyard-data/chipyard.db "SELECT * FROM runs \G"
```

*(SQLite uses `.mode line` for vertical output:)*

```bash
sqlite3 /scratch/chipyard-data/chipyard.db ".mode line" "SELECT * FROM runs;"
```

### Step 5: Verify log was copied

```bash
ls -la /scratch/chipyard-data/logs/
```

### Step 6: Test opt-out (optional)

```bash
make CONFIG=RocketConfig BINARY=$RISCV/riscv64-unknown-elf/share/riscv-tests/isa/rv64ui-p-simple DATACOLL=off run-binary
sqlite3 /scratch/chipyard-data/chipyard.db "SELECT COUNT(*) FROM runs;"
```

Count should **not** increase after the DATACOLL=off run.

---

## 7. Make Integration Details

### `data-collection.mk`

- Define `DATACOLL ?= ` (unset by default)
- Define `log_data_post_run` macro with args `(1)=bench`, `(2)=log_path`:
  - Calls: `python3 ... log_data.py --config-file ... --chipyard-config $(CONFIG) --bench $(1) --log-path $(2) --sim-dir $(sim_dir) --simulator $(sim_name)`
  - Passes `DATACOLL=$(DATACOLL)` in the environment

### `common.mk` modification

Append to the `%.run`, `%.run.fast`, and `$(output_dir)/%.run` rules (after the closing `)` of the `set -o pipefail` block):

```makefile
	&& $(call log_data_post_run,$(call get_out_name,$*),$(call get_sim_out_name,$*).log)
```

The macro receives `(1)=bench` (from `get_out_name`) and `(2)=log_path`. Variables `base_dir`, `CONFIG`, `sim_dir`, `sim_name` are in scope from the sim Makefiles.

---

## 8. log_data.py Interface (v0)

```
Usage: log_data.py [options]

Options:
  --init-db            Initialize (create) the database and schema
  --config-file PATH   Path to .chipyard/config.json (default: $CHIPYARD_ROOT/.chipyard/config.json)
  --chipyard-config N  Chipyard config name (e.g. RocketConfig)
  --bench BENCHMARK    Benchmark/binary name (e.g. hello, rv64ui-p-simple)
  --log-path PATH      Path to the simulation log file (to copy and parse)
  --sim-dir PATH       Simulator directory (for repo context)
  --simulator NAME     Simulator name (e.g. verilator, vcs)

Environment:
  DATACOLL             on | off | (unset = use config)
```

Script flow:
1. Load config, resolve tri-state (exit 0 if collect disabled)
2. If `--init-db`: mkdir artifact_dir/{builds,logs}, create DB, apply schema + migrations, exit
3. Else: gather git info (including github_user from remote_url), copy log to `artifact_dir/logs/`, parse metrics, get/create build_id, insert run row (with run_dir, simulator, github_user), exit

---

## 9. How to Test (Post-Implementation)

Exact commands to validate the v0 implementation:

**1. Initialize the DB:**
```bash
python3 /scratch/reednicolas/chipyard/util/log_data.py --init-db \
  --config-file /scratch/reednicolas/chipyard/.chipyard/config.json
```

**2. Run one Verilator run-binary with DATACOLL=on:**
```bash
cd /scratch/reednicolas/chipyard/sims/verilator
source /scratch/reednicolas/chipyard/env.sh
make CONFIG=RocketConfig BINARY=$RISCV/riscv64-unknown-elf/share/riscv-tests/isa/rv64ui-p-simple DATACOLL=on run-binary
```

**3. Query sqlite3 to show the inserted runs row and copied log path:**
```bash
sqlite3 -header -column /scratch/chipyard-data/chipyard.db "SELECT id, config, benchmark, simulator, log_path, timestamp FROM runs;"
ls -la /scratch/chipyard-data/logs/
```

---

## 10. Interactive Opt-In (datacoll-setup.py)

- `scripts/datacoll-setup.py` creates or updates `.chipyard/config.json`
- When run interactively (TTY): prompts Yes / No / Enter (use default)
- Default determination (v0): `"on"` if machine IP is in Berkeley ranges OR `git config user.email` ends with `berkeley.edu`; else `"off"`
- TODO: Future default may use server IP instead of GitHub email
- Build-setup flag: `--datacoll=on|off|default` (sets `DATACOLL` env; script skips prompt when set)
- Does not overwrite existing config; only updates `enable_data_collection` if file exists

## 11. Out of Scope for v0

- Build artifact copying (builds/ directory)
- VCS simulator (hook is in place; requires VCS installed)
- Waveform logging
- run-asm-tests, run-bmark-tests (expand after run-binary works)
- Postgres compatibility (schema is compatible, no migration tooling)
