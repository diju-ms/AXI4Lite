import os
from pathlib import Path
#from cocotb.runner import get_runner
from cocotb_tools.runner import get_runner
 
 
def test_axi4lite_runner():
    """Simulate axi4_lite_top using the Python runner.
 
    This file can be run directly or via pytest discovery.
    """
    sim = os.getenv("SIM", "verilator")
 
    # tb/ is the folder this file lives in
    tb_path   = Path(__file__).resolve().parent
    # design/ is one level up from tb/
    proj_path = tb_path.parent
 
    sources = [
        proj_path / "design" / "axi4_lite_master.sv",
        proj_path / "design" / "axi4_lite_slave.sv",
        proj_path / "design" / "axi4_lite_top.sv",
    ]
 
    runner = get_runner(sim)

    # Set environment variables to control waveform dumping
    os.environ["COCOTB_DUMP_WAVE_FORMAT"] = "vcd"  # Use vcd format
    # Set VCD_NAME to specify the output VCD file name  
    #env = os.environ.copy()  
    os.environ["VCD_NAME"] = "my_wave.vcd"  


    runner.build(
        sources=sources,
        hdl_toplevel="axi4_lite_top",
        always=True,
        waves=True,  
        build_args =["--trace"],  # Enable VCD tracing in Verilator
        #build_args=["-g2012"],
        #timescale=("1ns", "1ps"),
    )
    runner.test(
        hdl_toplevel="axi4_lite_top",
        test_module="axi4_tb_top",   # maps to tb/axi4_tb_top.py
    )
 
 
if __name__ == "__main__":
    test_axi4lite_runner()