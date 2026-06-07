# Chipyard Data Collection — Quick Start Guide

For users who have forked the repo and run `build-setup` on a Millennium machine. This guide starts after environment setup (conda, toolchain, etc.).

---

## Step 1: Initialize the database

Create the artifact directories and initialize the SQLite database:

```bash
mkdir -p /scratch/chipyard-data/builds /scratch/chipyard-data/logs
python3 util/log_data.py --init-db --config-file .chipyard/config.json
```

Run from the Chipyard repo root. If `.chipyard/config.json` is missing, create it first:

```bash
mkdir -p .chipyard
cat > .chipyard/config.json << 'EOF'
{
  "enable_data_collection": "on",
  "db_path": "/scratch/chipyard-data/chipyard.db",
  "artifact_dir": "/scratch/chipyard-data",
  "build_dir": "builds",
  "log_dir": "logs"
}
EOF
```

---

## Step 2: Build the simulator

```bash
cd sims/verilator
source ../../env.sh
make CONFIG=RocketConfig
```

---

## Step 3: Run a binary

```bash
make CONFIG=RocketConfig BINARY=$RISCV/riscv64-unknown-elf/share/riscv-tests/isa/rv64ui-p-simple run-binary
```

To force data collection for this run (even if config has it off):

```bash
make CONFIG=RocketConfig BINARY=$RISCV/riscv64-unknown-elf/share/riscv-tests/isa/rv64ui-p-simple DATACOLL=on run-binary
```

---

## Step 4: View output in SQL

List runs:

```bash
sqlite3 -header -column /scratch/chipyard-data/chipyard.db "SELECT id, config, benchmark, simulator, log_path, timestamp FROM runs;"
```

View a full row:

```bash
sqlite3 /scratch/chipyard-data/chipyard.db ".mode line" "SELECT * FROM runs;"
```

Verify logs were copied:

```bash
ls -la /scratch/chipyard-data/logs/
```

---

## Notes

- `/scratch/chipyard-data` is shared across Millennium nodes.
- `source env.sh` must be run from the Chipyard root before `make` so `$RISCV` is set.
- Use `DATACOLL=off` to skip logging for a single run.
