"""
dxf_to_gcode.py
===============
Converts a DXF file directly to G-code (no UI).

Pipeline
--------
    DXF  →  Shapely polygons  →  trimesh STL (temp file)  →  CuraEngine  →  .gcode
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import ezdxf
from ezdxf.path import make_path
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union

# Reuse the working STL and CuraEngine functions from svg_to_gcode
from svg_to_gcode import (
    find_cura_path,
    polygons_to_stl,
    stl_to_gcode,
    _safe_remove
)

def dxf_to_polygons(dxf_file: str, nozzle: float = 0.4) -> list:
    """
    Parse a DXF file and return a list of shapely Polygon objects.
    Open strokes are buffered by their nozzle/2 width to create solid traces.
    """
    try:
        doc = ezdxf.readfile(dxf_file)
    except Exception as e:
        print(f"  [error] Failed to read DXF file: {e}")
        return []

    msp = doc.modelspace()
    polygons = []

    for entity in msp:
        try:
            path = make_path(entity)
            if len(path) == 0:
                continue

            # Flatten the DXF path to a series of discrete 2D points
            pts = [(v.x, v.y) for v in path.flattening(distance=0.01)]
            if len(pts) < 2:
                continue

            start = pts[0]
            end = pts[-1]
            dist = (start[0] - end[0])**2 + (start[1] - end[1])**2
            is_closed = dist < 1e-5

            if is_closed:
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_valid and not poly.is_empty:
                    polygons.append(poly)
            else:
                line = LineString(pts)
                poly = line.buffer(nozzle / 2.0)
                if poly.is_valid and not poly.is_empty:
                    polygons.append(poly)
        except Exception:
            # Some entities (like complex blocks or text) might fail to make paths
            pass

    if not polygons:
        return []

    # Union overlapping polygons to clean up the mesh
    print(f"  -> Extracted {len(polygons)} path(s), merging...")
    try:
        unioned = unary_union(polygons)
        final_polygons = []
        if unioned.geom_type == 'Polygon':
            final_polygons.append(unioned)
        elif unioned.geom_type == 'MultiPolygon':
            final_polygons.extend(list(unioned.geoms))
        print(f"  -> {len(final_polygons)} polygon(s) after union.")
        return final_polygons
    except Exception as e:
        print(f"  [warn] Polygon union failed: {e}")
        return polygons


def convert(
    dxf_file: str,
    gcode_file: str,
    scale: float = 1.0,
    z_height: float = 0.4,
    speed: int = 1000,
    nozzle: float = 0.4,
    cura_path: Path | None = None,
    profile_path: str | None = None,
    keep_stl: bool = False,
) -> bool:
    """
    Full DXF → G-code conversion (no UI).
    Returns True on success, False on any failure.
    """
    import json
    
    print("=" * 60)
    print(" DXF  ->  G-code  Converter  (patch)")
    print("=" * 60)
    print(f"  Input  : {dxf_file}")
    print(f"  Output : {gcode_file}")
    print(f"  Scale  : {scale}x   Z-height: {z_height}mm   Speed: {speed}mm/s   Nozzle: {nozzle}mm")

    # 1. Locate CuraEngine
    if cura_path is None:
        try:
            cura_path = find_cura_path()
            print(f"  CuraEngine: {cura_path}")
        except FileNotFoundError as e:
            print(f"\n  [error] {e}")
            return False
    else:
        cura_path = Path(cura_path)
        if not (cura_path / "CuraEngine.exe").exists():
            print(f"\n  [error] CuraEngine.exe not found in: {cura_path}")
            return False

    # 2. Load optional profile
    profile = None
    if profile_path:
        try:
            with open(profile_path, "r") as f:
                profile = json.load(f)
            print(f"  Profile: {profile_path}")
        except Exception as e:
            print(f"  [warn] Could not load profile: {e}  (using defaults)")

    # 3. DXF → polygons
    print("\n[Step 1/3] Parsing DXF ...")
    polygons = dxf_to_polygons(dxf_file, nozzle=nozzle)
    if not polygons:
        print("  [error] No valid polygons found in the DXF.")
        return False

    # 4. Polygons → STL
    print("\n[Step 2/3] Building STL ...")
    if keep_stl:
        stl_file = str(Path(gcode_file).with_suffix(".stl"))
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False)
        stl_file = tmp.name
        tmp.close()

    ok = polygons_to_stl(polygons, stl_file, z_height=z_height, scale_factor=scale)
    if not ok:
        if not keep_stl:
            _safe_remove(stl_file)
        return False

    # 5. STL → G-code
    print("\n[Step 3/3] Slicing with CuraEngine ...")
    ok = stl_to_gcode(
        stl_file, gcode_file,
        cura_path=cura_path,
        nozzle=nozzle,
        speed=speed,
        z_height=z_height,
        profile=profile,
    )

    if not keep_stl:
        _safe_remove(stl_file)

    if ok:
        print("\n[OK] Conversion complete!")
    else:
        print("\n[FAIL] Conversion failed.")
    print("=" * 60)
    return ok


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dxf_to_gcode",
        description="Convert a DXF file to G-code without any GUI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("dxf",   help="Path to the input DXF file")
    p.add_argument("gcode", help="Path for the output .gcode file")

    p.add_argument("--scale",    type=float, default=1.0,
                   help="Uniform scale factor applied to DXF geometry (default: 1.0)")
    p.add_argument("--zheight",  type=float, default=0.4,
                   help="Layer / extrusion height in mm (default: 0.4)")
    p.add_argument("--speed",    type=int,   default=1000,
                   help="Print and travel speed in mm/s (default: 1000)")
    p.add_argument("--nozzle",   type=float, default=0.4,
                   help="Nozzle diameter in mm (default: 0.4)")
    p.add_argument("--cura",     type=str,   default=None,
                   help="Path to the CuraEngine installation folder (auto-detected if omitted)")
    p.add_argument("--profile",  type=str,   default=None,
                   help="Path to a JSON profile file (CuraEngine -s overrides)")
    p.add_argument("--keep-stl", action="store_true",
                   help="Keep the intermediate STL file next to the output G-code")
    return p


if __name__ == "__main__":
    parser  = _build_parser()
    args    = parser.parse_args()

    success = convert(
        dxf_file     = args.dxf,
        gcode_file   = args.gcode,
        scale        = args.scale,
        z_height     = args.zheight,
        speed        = args.speed,
        nozzle       = args.nozzle,
        cura_path    = args.cura,
        profile_path = args.profile,
        keep_stl     = args.keep_stl,
    )
    sys.exit(0 if success else 1)
