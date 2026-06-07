# Data collection post-run hook for Chipyard simulations
# Tri-state: DATACOLL=on forces logging, DATACOLL=off disables, unset follows config.json
DATACOLL ?=

# Python for log_data.py. Override with CHIPYARD_PYTHON if your default python3 lacks
# sqlite load_extension support (required for vec_runs / RAG indexing).
CHIPYARD_PYTHON ?= python3

# Invoke log_data.py after a run. Args: (1)=bench name, (2)=log file path, (3)=run target (e.g. run-binary)
# Never fails the build: script exits 0 on any error; || true for extra safety
define log_data_post_run
	DATACOLL=$(DATACOLL) $(CHIPYARD_PYTHON) $(base_dir)/util/log_data.py \
		--config-file $(base_dir)/.chipyard/config.json \
		--chipyard-config $(CONFIG) \
		--bench $(1) \
		--log-path $(2) \
		--run-target $(3) \
		--sim-dir $(sim_dir) \
		--simulator $(sim_name) || true
endef
