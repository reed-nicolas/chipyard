# Data collection post-run hook for Chipyard simulations
# Tri-state: DATACOLL=on forces logging, DATACOLL=off disables, unset follows config.json
DATACOLL ?=

# Invoke log_data.py after a run. Args: (1)=bench name, (2)=log file path
# Never fails the build: script exits 0 on any error; || true for extra safety
define log_data_post_run
	DATACOLL=$(DATACOLL) python3 $(base_dir)/util/log_data.py \
		--config-file $(base_dir)/.chipyard/config.json \
		--chipyard-config $(CONFIG) \
		--bench $(1) \
		--log-path $(2) \
		--sim-dir $(sim_dir) \
		--simulator $(sim_name) || true
endef
