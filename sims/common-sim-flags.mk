#----------------------------------------------------------------------------------------
# common gcc configuration/optimization
#----------------------------------------------------------------------------------------
SIM_OPT_CXXFLAGS := -O3
LRISCV=-lriscv

export USE_CHISEL6=1

DRAMSIM_INCLUDE_FLAGS = -I$(dramsim2_dir) -I$(dramsim3_dir)/src
DRAMSIM_LINK_FLAGS = -L$(dramsim2_dir) -ldramsim -L$(dramsim3_dir) -ldramsim3 -Wl,-rpath,$(dramsim3_dir)

SIM_CXXFLAGS = \
	$(CXXFLAGS) \
	$(SIM_OPT_CXXFLAGS) \
	-std=c++17 \
	-I$(RISCV)/include \
	$(DRAMSIM_INCLUDE_FLAGS) \
	-I$(GEN_COLLATERAL_DIR) \
	$(EXTRA_SIM_CXXFLAGS)

SIM_LDFLAGS = \
	$(LDFLAGS) \
	-L$(RISCV)/lib \
	-Wl,-rpath,$(RISCV)/lib \
	-L$(sim_dir) \
	$(LRISCV) \
	-lfesvr \
	$(DRAMSIM_LINK_FLAGS) \
	$(EXTRA_SIM_LDFLAGS)

CLOCK_PERIOD ?= 1.0
RESET_DELAY ?= 777.7

SIM_PREPROC_DEFINES = \
	+define+CLOCK_PERIOD=$(CLOCK_PERIOD) \
	+define+RESET_DELAY=$(RESET_DELAY) \
	+define+PRINTF_COND=$(TB).printf_cond \
	+define+STOP_COND=!$(TB).reset \
	+define+MODEL=$(MODEL) \
	+define+RANDOMIZE_MEM_INIT \
	+define+RANDOMIZE_REG_INIT \
	+define+RANDOMIZE_GARBAGE_ASSIGN \
	+define+RANDOMIZE_INVALID_ASSIGN \
	$(EXTRA_SIM_PREPROC_DEFINES)
