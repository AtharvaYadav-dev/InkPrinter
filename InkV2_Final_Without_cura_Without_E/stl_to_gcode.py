import argparse
import trimesh
from pathlib import Path
from shapely.geometry import Polygon
import numpy as np

# Load profile from config_manager (your updated version)
from config_manager import load_profile
from custom_slicer import slice_layers

def convert(
    stl_file: str,
    gcode_file: str,
    z_height: float = 0.4,
    speed: int = 1000,
    nozzle: float = 0.4,
    profile_args: dict = None
) -> bool:
    print("=" * 60)
    print(" STL  ->  G-code  Converter  (Custom Slicer)")
    print("=" * 60)
    print(f"  Input  : {stl_file}")
    print(f"  Output : {gcode_file}")
    
    print("\n[Step 1/2] Sectioning STL (3D) ...")
    try:
        mesh = trimesh.load(stl_file)
    except Exception as e:
        print(f"  [error] Failed to load STL: {e}")
        return False
        
    bounds = mesh.bounds
    z_min, z_max = bounds[0][2], bounds[1][2]
    
    print(f"  -> Z bounds: {z_min:.2f} to {z_max:.2f}")
    
    all_layers_polygons = []
    
    current_z = z_min + (z_height / 2.0)
    layer_idx = 0
    
    while current_z < z_max:
        try:
            slice_2d = mesh.section(plane_origin=[0, 0, current_z], plane_normal=[0, 0, 1])
        except Exception as e:
            print(f"  [error] Failed to section STL at Z={current_z:.3f}: {e}")
            slice_2d = None
            
        layer_polygons = []
        if slice_2d:
            slice_2d, _ = slice_2d.to_planar()
            for polygon in slice_2d.polygons_full:
                if polygon.is_valid and not polygon.is_empty and polygon.area > 1e-7:
                    layer_polygons.append(polygon)
                    
        all_layers_polygons.append(layer_polygons)
        
        current_z += z_height
        layer_idx += 1
            
    if not any(all_layers_polygons):
        print("  [error] No valid polygons found in any STL cross section.")
        return False

    print(f"\n[Step 2/2] Slicing {len(all_layers_polygons)} layers with Custom 3D Slicer ...")
    
    ok = slice_layers(
        layers_polygons=all_layers_polygons, 
        gcode_file=gcode_file, 
        nozzle=nozzle, 
        speed=speed, 
        z_height=z_height,
        wall_line_count=1
    )

    if ok:
        print(f"\n[OK] STL conversion complete. Saved to {gcode_file}")
    else:
        print("\n[FAIL] STL conversion failed during slicing.")
    print("=" * 60)
    return ok

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stl", help="Path to input STL file")
    parser.add_argument("gcode", help="Output G-code file")
    args = parser.parse_args()

    stl_path = Path(args.stl).resolve()
    gcode_path = Path(args.gcode).resolve()

    # Load real profile.json from config_manager
    profile_data = load_profile()
    
    speed = profile_data.get("speed_print", 10) * 60 if "speed_print" in profile_data else 1000
    nozzle = profile_data.get("machine_nozzle_size", 0.4)
    z_height = profile_data.get("layer_height", 0.4)

    convert(str(stl_path), str(gcode_path), z_height=z_height, speed=speed, nozzle=nozzle, profile_args=profile_data)
