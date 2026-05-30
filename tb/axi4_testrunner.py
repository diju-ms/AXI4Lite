import os
import sys
import ast
import time  # Added for OS file sync verification
import argparse
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from cocotb_tools.runner import get_runner

def auto_discover_cocotb_tests(file_path, filter_string=None):
    """Programmatically extracts test names decorated with @cocotb.test() using AST."""
    test_names = []
    if not file_path.exists():
        return test_names

    with open(file_path, "r", encoding="utf-8") as f:
        node = ast.parse(f.read(), filename=str(file_path))

    for body_item in node.body:
        if isinstance(body_item, (ast.AsyncFunctionDef, ast.FunctionDef)):
            for decorator in body_item.decorator_list:
                is_cocotb_test = False
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    if getattr(decorator.func.value, 'id', '') == 'cocotb' and decorator.func.attr == 'test':
                        is_cocotb_test = True
                elif isinstance(decorator, ast.Attribute):
                    if getattr(decorator.value, 'id', '') == 'cocotb' and decorator.attr == 'test':
                        is_cocotb_test = True
                
                if is_cocotb_test:
                    if filter_string is None or filter_string in body_item.name:
                        test_names.append(body_item.name)
                    break
    return test_names

def main():
    parser = argparse.ArgumentParser(
        description="Automated Regression Runner and Test Wrapper for AXI4-Lite IP Verification.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-w", "--waves", action="store_true", help="Enable simulation waveform generation.")
    parser.add_argument("-f", "--format", choices=["fst", "vcd"], default="fst", help="Waveform trace format.")
    parser.add_argument("-s", "--sim", default="verilator", help="Target hardware simulator engine.")
    parser.add_argument("-t", "--test", default=None, help="Filter string to run specific tests.")
    
    args = parser.parse_args()
    
    sim = args.sim
    enable_waves = args.waves
    wave_format = args.format
    test_filter = args.test
    
    hdl_toplevel_name = "axi4_lite_top"
    test_module_name = "axi4_tb_top"
    
    tb_path = Path(__file__).resolve().parent
    proj_path = tb_path.parent
    test_file_path = tb_path / f"{test_module_name}.py"
    
    sim_base_dir = tb_path / "sim"
    sim_base_dir.mkdir(parents=True, exist_ok=True)
    regression_log_path = sim_base_dir / "regression.log"
    
    all_tests = auto_discover_cocotb_tests(test_file_path, test_filter)
    if not all_tests:
        print(f"[Error] No tests found matching criteria.")
        sys.exit(1)

    if str(tb_path) not in sys.path:
        sys.path.insert(0, str(tb_path))
        
    sources = [
        proj_path / "design" / "axi4_lite_master.sv",
        proj_path / "design" / "axi4_lite_slave.sv",
        proj_path / "design" / "axi4_lite_top.sv",
    ]
    
    base_build_dir = tb_path / "build"
    runner = get_runner(sim)
    
    # --- PHASE 1: Clean Stale Residuals ---
    for stale_file in [tb_path / "dump.fst", tb_path / "dump.vcd"]:
        if stale_file.exists():
            stale_file.unlink()

    # --- PHASE 2: Compile Design ---
    build_args = []
    if sim == "verilator":
        build_args.extend(["--trace-fst" if wave_format == "fst" else "--trace", "--trace-structs"])
    elif sim == "icarus":
        build_args.append("-g2012")
        
    try:
        runner.build(
            sources=sources, hdl_toplevel=hdl_toplevel_name,
            always=False, clean=False, build_args=build_args,
            build_dir=base_build_dir, waves=True  
        )
    except Exception as e:
        print(f"\n[Fatal Error] Hardware compilation failed: {e}")
        sys.exit(1)
    
    log_accumulator = []
    def log_print(message=""):
        print(message)
        log_accumulator.append(message + "\n")

    log_print("="*80)
    log_print(f"[RUNNER EXECUTOR] Initializing Verification Run for {len(all_tests)} Test Targets")
    log_print("================================================================================")
    log_print(f" SIMULATOR      : {sim}")
    log_print(f" WAVE DUMPING   : {enable_waves} (Format: {wave_format})")
    log_print(f" TARGET FILTER  : {test_filter if test_filter else 'NONE (RUNNING EVERY TESTCASE)'}")
    log_print(f" REGRESSION LOG : {regression_log_path.relative_to(proj_path)}")
    log_print("="*80 + "\n")

    test_records = []

    # --- PHASE 3: Sandbox Loop Execution ---
    for test_name in all_tests:
        test_isolated_dir = sim_base_dir / test_name
        test_isolated_dir.mkdir(parents=True, exist_ok=True)
        
        sim_args = []
        if sim in ["questa", "modelsim", "vcs"]:
            sim_args.extend(["-l", str(test_isolated_dir / f"{test_name}_sim.log")])
        elif sim == "icarus":
            sim_args.append(f"-l{test_isolated_dir}/{test_name}_sim.log")
            
        test_env = {"COCOTB_TEST_FILTER": f"{test_module_name}.{test_name}$"}
        
        log_print(f"--> Running Test Case: [{test_name}]")
        log_print(f"    Sandbox Workspace: {test_isolated_dir.relative_to(proj_path)}")
        
        target_log_path = test_isolated_dir / "run.log"
        xml_report_path = test_isolated_dir / f"results_{test_name}.xml"
        
        runner.test(
            hdl_toplevel=hdl_toplevel_name, test_module=test_module_name,       
            build_dir=base_build_dir, test_dir=tb_path, test_args=sim_args,                 
            waves=enable_waves, extra_env=test_env, log_file=target_log_path, results_xml=xml_report_path
        )

        # --- OPTIMIZATION: Wait for OS File Flush Synchronization ---
        retry_loops = 5
        while retry_loops > 0 and (not target_log_path.exists() or target_log_path.stat().st_size == 0):
            time.sleep(0.05)  # Let filesystem buffering catch up and write data cleanly
            retry_loops -= 1

        # --- PHASE 4: Waveform Relocation ---
        if enable_waves:
            cocotb_default_fst = tb_path / "dump.fst"
            cocotb_default_vcd = tb_path / "dump.vcd"
            final_wave_ext = "fst" if wave_format == "fst" else "vcd"
            isolated_wave_dest = test_isolated_dir / f"{test_name}.{final_wave_ext}"
            
            if cocotb_default_fst.exists():
                shutil.move(str(cocotb_default_fst), str(isolated_wave_dest))
                log_print(f"    Waveform Captured: {isolated_wave_dest.relative_to(proj_path)}")
            elif cocotb_default_vcd.exists():
                shutil.move(str(cocotb_default_vcd), str(isolated_wave_dest))
                log_print(f"    Waveform Captured: {isolated_wave_dest.relative_to(proj_path)}")

        # --- PHASE 5: Statistics Extraction ---
        status, sim_time, real_time = "PASSED", "0.0", "0.0"
        if xml_report_path.exists():
            try:
                tree = ET.parse(xml_report_path)
                root = tree.getroot()
                for tc in root.iter("testcase"):
                    if tc.get("name") == test_name:
                        real_time = tc.get("time", "0.0")
                        sim_time = tc.get("sim_time_ns", "0.0")
                        if tc.find("failure") is not None: status = "FAILED"
                        elif tc.find("skipped") is not None: status = "SKIPPED"
                        break
            except Exception:
                status = "CRASHED/ERROR"
        else:
            status = "MISSING_XML"

        test_records.append({"name": test_name, "status": status, "real_time": real_time, "sim_time": sim_time})
        log_print(f"    Status Result    : {status}\n")

    # --- PHASE 6: Summary Generation ---
    total_run = len(test_records)
    passed_count = sum(1 for t in test_records if t["status"] == "PASSED")
    failed_count = sum(1 for t in test_records if t["status"] == "FAILED")
    other_count = total_run - (passed_count + failed_count)

    log_print("="*80)
    log_print("                       AXI4LITE REGRESSION SUMMARY REPORT")
    log_print("="*80)
    log_print(f" {'TEST CASE NAME':<35} | {'STATUS':<10} | {'SIM TIME (ns)':<13} | {'REAL TIME (s)':<10}")
    log_print(" " + "-"*78)
    for record in test_records:
        log_print(f" {record['name']:<35} | {record['status']:<10} | {record['sim_time']:<13} | {record['real_time']:<10}")
    log_print(" " + "-"*78)
    log_print(f" TOTAL TESTS RUN : {total_run}")
    log_print(f" PASSED          : {passed_count}")
    log_print(f" FAILED          : {failed_count}")
    if other_count > 0: log_print(f" OTHER (ERRORS)  : {other_count}")
    log_print("="*80 + "\n")
    
    # --- PHASE 7: Construct Unified regression.log ---
    with open(regression_log_path, "w", encoding="utf-8") as main_log:
        main_log.writelines(log_accumulator[:6])
        for test_name in all_tests:
            # Re-verify matching to prevent missing logs from filtered skip arrays
            if not any(r["name"] == test_name for r in test_records):
                continue
            main_log.write(f"\n" + "#"*80 + f"\n# SIMULATION LOG TRACE FOR: {test_name}\n" + "#"*80 + "\n\n")
            indiv_log_path = sim_base_dir / test_name / "run.log"
            if indiv_log_path.exists() and indiv_log_path.stat().st_size > 0:
                with open(indiv_log_path, "r", encoding="utf-8") as f_in:
                    main_log.write(f_in.read())
            else:
                main_log.write(f"[Warning] No simulator run.log trace file found for {test_name}.\n")
        main_log.write(f"\n" + "#"*80 + f"\n# FINAL REGRESSION SUMMARY REPORT MATRIX\n" + "#"*80 + "\n\n")
        main_log.writelines(log_accumulator[6:])

    print(f"--> [SUCCESS] Comprehensive log compiled at: {regression_log_path.relative_to(proj_path)}\n")

    
    if failed_count > 0 or other_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
