import subprocess
from pathlib import Path
import json
import argparse

# Load profile from config_manager (your updated version)
from config_manager import load_profile



# -----------------------------
# Paths
# -----------------------------
cura_path = Path("C:/Program Files/UltiMaker Cura 5.9.1")
resources_path = cura_path / "share" / "cura" / "resources"
def_path = resources_path / "definitions"
extruder_def_path = resources_path / "extruders"

machine_def = def_path / "specialize_india_500.def.json"
extruder_def = extruder_def_path / "specialize_india_500_extruder_0.def.json"


# -----------------------------
# Convert Profile → CuraEngine args
# -----------------------------
def json2args(profile_dict):
    args = []
    for k, v in profile_dict.items():

        # CuraEngine requires lowercase booleans (true/false)
        if isinstance(v, bool):
            v = str(v).lower()

        args += ["-s", f"{k}={v}"]
    return args



# -----------------------------
# Run CuraEngine
# -----------------------------
def runCuraEngine(input_stl: Path, output_gcode: Path, profile_args):
    cura_engine = cura_path / "CuraEngine.exe"

    cmd = [
        str(cura_engine),
        "slice",
        "-v",
        "-p",

        "-j", str(machine_def),
        "-j", str(extruder_def),

        "-s", "machine_extruder_count=1",

        # Mandatory overrides for flat ink printing
        "-s", "wall_line_count=1",
        "-s", "wall_thickness=0.4",
        "-s", "top_layers=0",
        "-s", "bottom_layers=0",
        "-s", "top_bottom_thickness=0",

        "-s", "infill_sparse_density=100",
        "-s", "infill_pattern=lines",
        "-s", "infill_angles=[90]",
        "-s", "inset_direction=outside_in",
        "-s", "connect_infill_polygons=true",

        # Preserving thin features
        "-s", "print_thin_walls=true",
        "-s", "fill_outline_gaps=true",
        "-s", "fill_perimeter_gaps=everywhere",
        "-s", "filter_out_tiny_gaps=false",
        "-s", "min_wall_line_width=0.1",
    ]

    # Add user profile values
    cmd.extend(profile_args)

    # Required in Cura when top/bottom = 0
    cmd.extend([
        "-s", "roofing_layer_count=0",
        "-s", "roofing_monotonic=true"
    ])

    cmd += ["-l", str(input_stl), "-o", str(output_gcode)]

    print("\nRunning command:\n", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    print("\n----- CuraEngine STDOUT -----")
    print(result.stdout)

    print("----- CuraEngine STDERR -----")
    print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError("CuraEngine slicing failed!")

    print("Slicing successful:", output_gcode)



# -----------------------------
# MAIN (Command-line support)
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stl", help="Path to input STL file")
    parser.add_argument("gcode", help="Output G-code file")
    args = parser.parse_args()

    stl_path = Path(args.stl).resolve()
    gcode_path = Path(args.gcode).resolve()

    # ✔ Load real profile.json from config_manager
    profile_data = load_profile()
    profile_args = json2args(profile_data)

    print(f"\nProfile Args -> {profile_args}\n")

    runCuraEngine(stl_path, gcode_path, profile_args)
