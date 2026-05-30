# ─────────────────────────────────────────────────────────────────────────────
#
# Usage:
#   make                     run all tests with verilator
#   make SIM=questa          run with Questa
#   make TEST=TestReset      run a single named test
#   make WAVES=1             open GTKWave after run (Icarus only)
# ─────────────────────────────────────────────────────────────────────────────


PWD=$(shell pwd)
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

#top design unit name
TOPLEVEL := axi4_lite_top

#top python tb file name
MODULE := axi4_tb_top

# design/ is one level up from tb/
DESIGN_DIR = $(PWD)/../design

# Add tb/ to PYTHONPATH so axi4_bfm.py is importable from axi4_tb_top.py
export PYTHONPATH := $(PWD):$(PYTHONPATH)


ifeq ($(SIM),verilator)
  COMPILE_ARGS += --timing        # required for cocotb with Verilator
  COMPILE_ARGS += --assert        # enable SVA (partial support)
  COMPILE_ARGS += -Wall           # recommended
  COMPILE_ARGS += -Wno-EOFNEWLINE #to avoid lint issue %Warning-EOFNEWLINE: Missing newline at end of file
  COMPILE_ARGS += -Wno-WIDTHTRUNC #to avoid lint issue for size mismatches
  COMPILE_ARGS += -I$(DESIGN_DIR) # compiler flag that stands for Include. It tells the compiler, "Hey, when you are looking for header files (like .h in C/C++) or package/include files (like .vh or .svh in Verilog), look inside the directory I'm about to specify."

  # Add this to enable wave dumping when you type: make WAVES=1
  ifeq ($(WAVES),1)
    PLUSARGS += --trace
#VCD option
    #EXTRA_ARGS += --trace --trace-structs
#FST option
    EXTRA_ARGS += --trace-fst --trace-structs
  endif
endif 


# Simulator-specific flags
ifeq ($(SIM),icarus)
  COMPILE_ARGS += -g2012
endif
ifeq ($(SIM),questa)
  COMPILE_ARGS += -sv
  SIM_ARGS     += -do "log -r /*; run -all"
endif
ifeq ($(SIM),vcs)
  COMPILE_ARGS += -sverilog +v2k
endif


ifeq ($(TOPLEVEL_LANG),verilog)
    #VERILOG_SOURCES = $(DESIGN_DIR)/axi_lite_slave_v1_0_S00_AXI.v
    # Automatically finds all .v and .sv files in the RTL folder
    VERILOG_SOURCES = $(wildcard $(DESIGN_DIR)/*.v) $(wildcard $(DESIGN_DIR)/*.sv)
else
    $(error A valid value (verilog or vhdl) was not provided for TOPLEVEL_LANG=$(TOPLEVEL_LANG))
endif


# Cocotb include line
include $(shell cocotb-config --makefiles)/Makefile.sim

.PHONY: waves clean_all
waves:
	gtkwave dump.vcd &

clean_all: clean
	rm -rf __pycache__ results.xml *.vcd *.fst sim_build obj_dir

