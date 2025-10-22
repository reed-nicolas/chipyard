\#!/usr/bin/env bash
# chipyard-full-flow-local.sh
# Local replica of chipyard-ci-full-flow that logs the entire run.

set -eo pipefail

# Toggles (set to 0 to skip heavy parts)
DO_VLSI="${DO_VLSI:-1}"
DO_BRIDGES="${DO_BRIDGES:-1}"
DO_FIRECHIP="${DO_FIRECHIP:-1}"

# Defaults (override by exporting before running)
SHA_SHORT="$(git rev-parse --short HEAD 2>/dev/null || echo local)"
REMOTE_WORK_DIR="${REMOTE_WORK_DIR:-/scratch/${USER}/cy-workdir-${SHA_SHORT}-$$}"
JAVA_TMP_DIR="${JAVA_TMP_DIR:-/scratch/${USER}/cy-javatmpdir-${SHA_SHORT}-$$}"
MAKEFLAGS="${MAKEFLAGS:--j32}"

# Stable log export location
STABLE_LOG_DIR="${STABLE_LOG_DIR:-/scratch/${USER}/cy-logs}"

# Prepare scratch and clean from prior runs of the same names
mkdir -p "$(dirname "$REMOTE_WORK_DIR")" "$(dirname "$JAVA_TMP_DIR")" "$STABLE_LOG_DIR"
rm -rf "$REMOTE_WORK_DIR" "$JAVA_TMP_DIR" || true
mkdir -p "$REMOTE_WORK_DIR" "$JAVA_TMP_DIR"

# Set up logging: write to run-local file AND a stable "live" file continuously
TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$REMOTE_WORK_DIR/_logs"
mkdir -p "$LOG_DIR" "$STABLE_LOG_DIR"
LOG_FILE="$LOG_DIR/full-flow-$TS.log"
STABLE_LIVE_LOG="$STABLE_LOG_DIR/full-flow-live-$TS.log"
: > "$STABLE_LIVE_LOG"  # ensure it exists immediately

# mirror all stdout/stderr to both files
# avoid color buffering issues by keeping it simple
exec > >(tee -a "$LOG_FILE" | tee -a "$STABLE_LIVE_LOG") 2>&1

echo "Scratch:          $REMOTE_WORK_DIR"
echo "Java tmp:         $JAVA_TMP_DIR"
echo "Full log:         $LOG_FILE"
echo "Stable live log:  $STABLE_LIVE_LOG"
echo "Stable log dir:   $STABLE_LOG_DIR"
echo "Toggles:          DO_VLSI=$DO_VLSI DO_BRIDGES=$DO_BRIDGES DO_FIRECHIP=$DO_FIRECHIP"
echo "MAKEFLAGS:        $MAKEFLAGS"
echo "Commit (hint):    $(git rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
echo

# Clean up handler (keeps artifacts and produces stable copies + symlinks)
finalize_logs() {
  echo
  echo "Finalizing logs and artifacts..."
  mkdir -p "$STABLE_LOG_DIR/run-$TS"

  # Final timestamped copies
  if [ -f "$LOG_FILE" ]; then
    cp -f "$LOG_FILE" "$STABLE_LOG_DIR/full-flow-$TS.log"
  fi
  if [ -f "$REMOTE_WORK_DIR/build-setup.log" ]; then
    cp -f "$REMOTE_WORK_DIR/build-setup.log" "$STABLE_LOG_DIR/build-setup-$TS.log"
  fi

  # Mirror the run logs directory
  if [ -d "$LOG_DIR" ]; then
    rsync -a "$LOG_DIR/" "$STABLE_LOG_DIR/run-$TS/_logs/"
  fi

  # Maintain convenient symlinks
  ln -sfn "full-flow-$TS.log"     "$STABLE_LOG_DIR/latest.log"
  ln -sfn "run-$TS"               "$STABLE_LOG_DIR/latest"
  ln -sfn "$REMOTE_WORK_DIR"      "$STABLE_LOG_DIR/latest.workdir"

  echo "Stable copies:"
  [ -f "$STABLE_LOG_DIR/full-flow-$TS.log" ]   && echo "  - $STABLE_LOG_DIR/full-flow-$TS.log"
  [ -f "$STABLE_LOG_DIR/build-setup-$TS.log" ] && echo "  - $STABLE_LOG_DIR/build-setup-$TS.log"
  echo "  - $STABLE_LOG_DIR/latest.log -> full-flow-$TS.log"
  echo "  - $STABLE_LOG_DIR/latest/     (mirrored _logs)"
  echo "  - $STABLE_LOG_DIR/latest.workdir -> $REMOTE_WORK_DIR"
  sync || true
}

trap 'echo; echo "Done. Logs and artifacts kept at: $REMOTE_WORK_DIR"; echo "  - Full log:        $LOG_FILE"; echo "  - build-setup log: $REMOTE_WORK_DIR/build-setup.log (if generated)"; finalize_logs' EXIT

conda_hook() {
  if command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)" || true
  fi
}

echo "== Checkout to scratch =="
REPO_TOP="$(git rev-parse --show-toplevel)"
rsync -a --delete "$REPO_TOP/" "$REMOTE_WORK_DIR/"

echo "== Setup repo =="
cd "$REMOTE_WORK_DIR"
conda_hook
export MAKEFLAGS
git submodule sync
chmod +x ./build-setup.sh

SETUP_SKIP=""
# If a copied env already exists (or we are in one), skip step 1 to avoid recreation error
if [[ -d ".conda-env" || -n "${CONDA_DEFAULT_ENV:-}" ]]; then
  SETUP_SKIP="-s 1"
fi

# Run setup; mirrored to both logs by exec redirection
./build-setup.sh -v $SETUP_SKIP | tee build-setup.log

echo "== Run config finder =="
conda_hook
# shellcheck disable=SC1091
source env.sh
pushd sims/verilator >/dev/null
make find-config-fragments
make find-configs
popd >/dev/null

echo "== Run smoke test (verilog) =="
conda_hook
# shellcheck disable=SC1091
source env.sh
make -C sims/verilator verilog

if [[ "$DO_VLSI" == "1" ]]; then
  echo "== VLSI test =="
  conda_hook
  # shellcheck disable=SC1091
  source env.sh
  pushd vlsi >/dev/null

  # avoid clashing deps
  conda config --remove channels litex-hub || true
  conda config --remove channels defaults || true

  # installs for example-sky130.yml
  conda create -y --prefix ./.conda-sky130   -c defaults -c litex-hub open_pdks.sky130a=1.0.457_0_g32e8f23
  git clone https://github.com/rahulk29/sram22_sky130_macros.git
  git -C sram22_sky130_macros checkout 1f20d16

  # installs for example-openroad.yml
  conda create -y --prefix ./.conda-yosys    -c defaults -c litex-hub yosys=0.27_4_gb58664d44
  conda create -y --prefix ./.conda-openroad -c defaults -c litex-hub openroad=2.0_7070_g0264023b6
  conda create -y --prefix ./.conda-klayout  -c defaults -c litex-hub klayout=0.28.5_98_g87e2def28
  conda create -y --prefix ./.conda-signoff  -c defaults -c litex-hub magic=8.3.376_0_g5e5879c netgen=1.5.250_0_g178b172

  cat > tutorial.yml <<EOF
# Tutorial configs
# pdk
technology.sky130.sky130A: $PWD/.conda-sky130/share/pdk/sky130A
technology.sky130.sram22_sky130_macros: $PWD/sram22_sky130_macros

# tools
synthesis.yosys.yosys_bin: $PWD/.conda-yosys/bin/yosys
par.openroad.openroad_bin: $PWD/.conda-openroad/bin/openroad
par.openroad.klayout_bin: $PWD/.conda-klayout/bin/klayout
drc.magic.magic_bin: $PWD/.conda-signoff/bin/magic
drc.klayout.klayout_bin: $PWD/.conda-klayout/bin/klayout
lvs.netgen.netgen_bin: $PWD/.conda-signoff/bin/netgen

# speed up tutorial runs & declutter log output
par.openroad.timing_driven: false
par.openroad.write_reports: false
EOF

  export tutorial=sky130-openroad
  export EXTRA_CONFS=tutorial.yml
  export VLSI_TOP=RocketTile
  make buildfile
  make syn
  popd >/dev/null
fi

if [[ "$DO_BRIDGES" == "1" ]]; then
  echo "== FireChip bridge tests =="
  conda_hook
  # shellcheck disable=SC1091
  source env.sh
  pushd sims/firesim >/dev/null
  # shellcheck disable=SC1091
  source sourceme-manager.sh --skip-ssh-setup
  popd >/dev/null
  pushd sims/firesim-staging >/dev/null
  export TEST_DISABLE_VERILATOR=1
  export TEST_DISABLE_VIVADO=1
  make launch-sbt SBT_COMMAND=";project firechip_bridgestubs; testOnly firechip.bridgestubs.BridgeTests"
  popd >/dev/null
fi

if [[ "$DO_FIRECHIP" == "1" ]]; then
  echo "== FireChip target tests =="
  conda_hook
  # shellcheck disable=SC1091
  source env.sh
  pushd sims/firesim >/dev/null
  # shellcheck disable=SC1091
  source sourceme-manager.sh --skip-ssh-setup
  popd >/dev/null
  pushd sims/firesim-staging >/dev/null
  export TEST_MINIMAL_BENCHMARKS=1
  export TEST_DISABLE_VERILATOR=1
  export TEST_DISABLE_VIVADO=1
  make launch-sbt SBT_COMMAND=";project firechip; testOnly firechip.chip.CITests"
  popd >/dev/null
fi

echo
echo "== Per-step timing from build-setup.log =="
sed -n '/Per-step timing/,$p' build-setup.log || true
echo "Full log:        $LOG_FILE"
echo "Build-setup log: $REMOTE_WORK_DIR/build-setup.log"
