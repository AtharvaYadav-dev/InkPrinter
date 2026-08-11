"""
svg_to_gcode.py
===============
Standalone patch: converts an SVG file directly to G-code (no UI).

Pipeline
--------
    SVG  →  Shapely polygons  →  trimesh STL (temp file)  →  CuraEngine  →  .gcode

Usage
-----
    python svg_to_gcode.py input.svg output.gcode [options]

Options
-------
    --scale      FLOAT   Extra uniform scale factor          (default: 1.0)
    --zheight    FLOAT   Extrusion / layer height in mm      (default: 0.4)
    --speed      INT     Print + travel speed in mm/min      (default: 1000)
    --nozzle     FLOAT   Nozzle diameter in mm               (default: 0.4)
    --cura       PATH    CuraEngine installation folder      (default: auto-detect)
    --profile    PATH    JSON profile file for CuraEngine    (optional)
    --keep-stl          Keep the intermediate STL file

Dependencies
-----------
    pip install svgpathtools shapely trimesh numpy
    CuraEngine 5.x must be installed (or --cura path supplied).
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from shapely.affinity import scale as shapely_scale
from shapely.geometry import LineString, Polygon
from svgpathtools import Line, parse_path
from svgpathtools.parser import parse_transform
import trimesh
from custom_slicer import slice_polygons

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 – Auto-detect CuraEngine
# ─────────────────────────────────────────────────────────────────────────────

CURA_CANDIDATES = [
    r"C:\Program Files\UltiMaker Cura 5.9.1",
    r"C:\Program Files\UltiMaker Cura 5.8.0",
    r"C:\Program Files\UltiMaker Cura 5.7.0",
    r"C:\Program Files\Ultimaker Cura 5.6.0",
    r"C:\Program Files\Ultimaker Cura 5.5.0",
    r"C:\Program Files\Ultimaker Cura 5.4.0",
    r"C:\Program Files\Ultimaker Cura 5.3.0",
    r"C:\Program Files\Ultimaker Cura 5.2.0",
    r"C:\Program Files\Ultimaker Cura 5.1.0",
    r"C:\Program Files\Ultimaker Cura 5.0.0",
]


def find_cura_path() -> Path:
    """Return the first CuraEngine installation found, or raise."""
    for candidate in CURA_CANDIDATES:
        p = Path(candidate)
        if (p / "CuraEngine.exe").exists():
            return p
    raise FileNotFoundError(
        "CuraEngine not found. Install UltiMaker Cura 5.x or pass --cura <path>."
    )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 – Nozzle snapping
# ─────────────────────────────────────────────────────────────────────────────

def snap_to_nozzle(sw_mm: float, nozzle: float) -> float:
    """
    Round stroke-width UP to the nearest whole nozzle-diameter multiple.
    This guarantees CuraEngine can fill the polygon with exact parallel passes.
    """
    if sw_mm <= 0:
        return nozzle
    n = math.ceil(sw_mm / nozzle)
    return round(n * nozzle, 6)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 – SVG → Shapely Polygons
# ─────────────────────────────────────────────────────────────────────────────

def _parse_to_mm(val) -> float | None:
    """Convert an SVG unit string (e.g. '210mm', '8.5in') to millimetres."""
    if val is None:
        return None
    m = re.match(r"([0-9.]+)\s*([a-z%]*)", str(val).strip())
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2).lower()
    mapping = {
        "mm": 1.0, "cm": 10.0, "in": 25.4,
        "pt": 25.4 / 72.0, "px": 25.4 / 96.0, "": 25.4 / 96.0,
    }
    return v * mapping.get(u, 25.4 / 96.0)


def svg_to_polygons(svg_file: str, nozzle: float = 0.4) -> list:
    """
    Parse an SVG file and return a list of shapely Polygon objects (in mm).

    Handles: path, rect, circle, ellipse, polygon, polyline.
    Applies:  style inheritance, transform matrices, unit-to-mm scaling, Y-flip.
    Open strokes are buffered by their (snapped) stroke-width.
    """
    tree = ET.parse(svg_file)
    root = tree.getroot()

    # ── Document scale ───────────────────────────────────────────────────────
    width_attr  = root.get("width")
    height_attr = root.get("height")
    viewbox_attr = root.get("viewBox")

    doc_width_mm  = _parse_to_mm(width_attr)
    doc_height_mm = _parse_to_mm(height_attr)
    unit_to_mm    = 25.4 / 96.0   # default fallback (96 DPI)
    flip_y_limit_mm = 0.0

    if viewbox_attr:
        vb = [float(x) for x in viewbox_attr.replace(",", " ").split()]
        if len(vb) == 4:
            if doc_width_mm:
                unit_to_mm = doc_width_mm / vb[2]
            flip_y_limit_mm = (vb[1] + vb[3]) * unit_to_mm
    elif doc_width_mm and doc_height_mm:
        flip_y_limit_mm = doc_height_mm

    # ── Helpers ──────────────────────────────────────────────────────────────
    def clean_tag(tag):
        return tag.split("}")[-1] if "}" in tag else tag

    def get_styles(elem, inherited=None):
        styles = (inherited or {}).copy()
        defaults = {"fill": "black", "stroke": "none", "stroke-width": "1"}
        for k, v in defaults.items():
            styles.setdefault(k, v)

        style_dict = {}
        for part in elem.get("style", "").split(";"):
            if ":" in part:
                try:
                    k, v = part.split(":", 1)
                    style_dict[k.strip()] = v.strip()
                except Exception:
                    pass

        for name in ("fill", "stroke", "stroke-width"):
            val = elem.get(name)
            if val is not None:
                styles[name] = val
            elif name in style_dict:
                styles[name] = style_dict[name]
        return styles

    polygons = []

    def process_element(elem, parent_transform=None, inherited_styles=None):
        tag = clean_tag(elem.tag)
        if tag in ("defs", "metadata", "title", "desc"):
            return

        current_styles = get_styles(elem, inherited_styles)

        # Accumulate transforms
        local_transform = None
        t_str = elem.get("transform", "")
        if t_str:
            try:
                local_transform = parse_transform(t_str)
            except Exception:
                pass

        current_transform = parent_transform
        if local_transform is not None:
            current_transform = (
                np.dot(current_transform, local_transform)
                if current_transform is not None
                else local_transform
            )

        # ── Shape → path_d ──────────────────────────────────────────────────
        path_d   = ""
        is_closed = False

        if tag == "path":
            path_d = elem.get("d", "")
            if path_d.lower().strip().endswith("z"):
                is_closed = True

        elif tag == "rect":
            x, y = float(elem.get("x", 0)), float(elem.get("y", 0))
            w, h = float(elem.get("width", 0)), float(elem.get("height", 0))
            path_d    = f"M {x},{y} L {x+w},{y} L {x+w},{y+h} L {x},{y+h} Z"
            is_closed = True

        elif tag == "circle":
            cx, cy = float(elem.get("cx", 0)), float(elem.get("cy", 0))
            r       = float(elem.get("r", 0))
            path_d  = (
                f"M {cx-r},{cy} A {r},{r} 0 1,0 {cx+r},{cy} "
                f"A {r},{r} 0 1,0 {cx-r},{cy} Z"
            )
            is_closed = True

        elif tag == "ellipse":
            cx, cy = float(elem.get("cx", 0)), float(elem.get("cy", 0))
            rx, ry  = float(elem.get("rx", 0)), float(elem.get("ry", 0))
            path_d  = (
                f"M {cx-rx},{cy} A {rx},{ry} 0 1,0 {cx+rx},{cy} "
                f"A {rx},{ry} 0 1,0 {cx-rx},{cy} Z"
            )
            is_closed = True

        elif tag in ("polygon", "polyline"):
            pts = elem.get("points", "").strip().replace(",", " ").split()
            if len(pts) >= 4:
                path_d = f"M {pts[0]},{pts[1]}"
                for i in range(2, len(pts), 2):
                    path_d += f" L {pts[i]},{pts[i+1]}"
                if tag == "polygon":
                    path_d   += " Z"
                    is_closed = True

        # ── Parse path_d → polygon ───────────────────────────────────────────
        if path_d:
            try:
                path = parse_path(path_d)
                sub_paths = []
                if len(path) > 0:
                    current_sub = [path[0]]
                    for i in range(1, len(path)):
                        if (np.isclose(path[i-1].end.real, path[i].start.real) and
                                np.isclose(path[i-1].end.imag, path[i].start.imag)):
                            current_sub.append(path[i])
                        else:
                            sub_paths.append(current_sub)
                            current_sub = [path[i]]
                    sub_paths.append(current_sub)

                for sub in sub_paths:
                    points = []
                    for seg in sub:
                        samples = 2 if isinstance(seg, Line) else 20
                        for t in np.linspace(0, 1, samples, endpoint=False):
                            p = seg.point(t)
                            points.append([p.real, p.imag])
                    if sub:
                        p_end = sub[-1].end
                        points.append([p_end.real, p_end.imag])

                    if len(points) < 2:
                        continue

                    pts_array = np.array(points)

                    # Apply SVG transform matrix
                    effective_scale = 1.0
                    if current_transform is not None:
                        pts_h = np.hstack([pts_array, np.ones((pts_array.shape[0], 1))])
                        pts_transformed = np.dot(pts_h, current_transform.T)
                        pts_array = pts_transformed[:, :2]
                        a, c, _ = current_transform[0]
                        b, d, _ = current_transform[1]
                        effective_scale = (np.sqrt(a*a + b*b) + np.sqrt(c*c + d*d)) / 2.0

                    # Convert user-units → mm
                    pts_array *= unit_to_mm

                    # Flip Y (SVG = top-left origin; CNC = bottom-left origin)
                    if flip_y_limit_mm > 0:
                        pts_array[:, 1] = flip_y_limit_mm - pts_array[:, 1]

                    sub_closed = is_closed or np.allclose(pts_array[0], pts_array[-1], atol=1e-3)
                    fill       = current_styles["fill"].lower()
                    stroke     = current_styles["stroke"].lower()
                    sw_str     = current_styles["stroke-width"]

                    try:
                        sw = float(re.findall(r"[-+]?\d*\.?\d+", str(sw_str))[0])
                    except Exception:
                        sw = 1.0

                    sw_mm = sw * effective_scale * unit_to_mm

                    if sub_closed and fill != "none":
                        if not np.array_equal(pts_array[0], pts_array[-1]):
                            pts_array = np.vstack([pts_array, pts_array[0]])
                        poly = Polygon(pts_array)
                        if not poly.is_valid:
                            poly = poly.buffer(0)
                        if poly.is_valid and not poly.is_empty:
                            if poly.geom_type == "Polygon":
                                polygons.append(poly)
                            elif poly.geom_type == "MultiPolygon":
                                polygons.extend(list(poly.geoms))

                    elif stroke != "none" and sw_mm > 0.01:
                        snapped = snap_to_nozzle(sw_mm, nozzle)
                        if snapped != sw_mm:
                            passes = int(round(snapped / nozzle))
                            print(
                                f"  [snap] stroke {sw_mm:.4f}mm -> {snapped:.4f}mm "
                                f"({passes} passes @ {nozzle}mm nozzle)"
                            )
                        line = LineString(pts_array)
                        poly = line.buffer(snapped / 2.0)
                        if poly.is_valid and not poly.is_empty:
                            if poly.geom_type == "Polygon":
                                polygons.append(poly)
                            elif poly.geom_type == "MultiPolygon":
                                polygons.extend(list(poly.geoms))

            except Exception as e:
                print(f"  [warn] Error processing <{tag}>: {e}")

        for child in elem:
            process_element(child, current_transform, current_styles)

    process_element(root)
    polygons = [p for p in polygons if p.area > 1e-7]
    print(f"  -> {len(polygons)} polygon(s) extracted from SVG")
    return polygons


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 – Shapely Polygons → STL
# ─────────────────────────────────────────────────────────────────────────────

def polygons_to_stl(polygons: list, output_file: str,
                    z_height: float = 0.4, scale_factor: float = 1.0) -> bool:
    """Extrude each shapely polygon into a thin 3-D layer and export as STL."""
    meshes = []
    for poly in polygons:
        scaled_poly = shapely_scale(poly, xfact=scale_factor, yfact=scale_factor, origin=(0, 0))
        try:
            try:
                mesh = trimesh.creation.extrude_polygon(scaled_poly, z_height)
            except Exception:
                mesh = trimesh.creation.extrude_polygon(
                    scaled_poly, z_height, triangulation_engine="earcut"
                )
            meshes.append(mesh)
        except Exception as e:
            print(f"  [warn] Skipping polygon: {e}")

    if not meshes:
        print("  [error] No valid meshes — nothing to export.")
        return False

    combined = trimesh.util.concatenate(meshes)
    combined.vertices = combined.vertices.round(5)
    combined.export(output_file)

    bounds = combined.bounds
    w = bounds[1][0] - bounds[0][0]
    h = bounds[1][1] - bounds[0][1]
    d = bounds[1][2] - bounds[0][2]
    print(f"  -> STL saved: {output_file}")
    print(f"     Dimensions: W={w:.3f}mm  H={h:.3f}mm  D={d:.3f}mm")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 – STL → G-code via CuraEngine
# ─────────────────────────────────────────────────────────────────────────────

def _profile_to_args(profile: dict) -> list[str]:
    """Convert a profile dict to CuraEngine -s KEY=VALUE argument pairs."""
    args = []
    for k, v in profile.items():
        if k == "profile_version":
            continue
        if isinstance(v, bool):
            v = str(v).lower()
        elif isinstance(v, list):
            v = json.dumps(v)   # e.g. [90] → "[90]"
        args += ["-s", f"{k}={v}"]
    return args


def stl_to_gcode(
    stl_file: str,
    gcode_file: str,
    cura_path: Path,
    nozzle: float = 0.4,
    speed: int = 1000,
    z_height: float = 0.4,
    profile: dict | None = None,
) -> bool:
    """
    Call CuraEngine to slice the STL and write the G-code file.

    CuraEngine expects machine + extruder definitions from its own resources.
    This function uses the definitions bundled with the installed Cura.
    """
    cura_engine = cura_path / "CuraEngine.exe"
    resources   = cura_path / "share" / "cura" / "resources"

    # Try custom definitions inside Cura's resource directory first (installed by Cura Fixer)
    custom_machine = resources / "definitions" / "specialize_india_500.def.json"
    custom_extruder = resources / "extruders" / "specialize_india_500_extruder_0.def.json"
    
    if custom_machine.exists() and custom_extruder.exists():
        machine_def = custom_machine
        extruder_def = custom_extruder
    else:
        machine_def  = resources / "definitions" / "fdmprinter.def.json"
        extruder_def = resources / "extruders"    / "fdmextruder.def.json"

    # ── Base CuraEngine command ──────────────────────────────────────────────
    cmd = [
        str(cura_engine), "slice", "-v", "-p",
        "-j", str(machine_def),
        "-j", str(extruder_def),

        "-s", "machine_extruder_count=1",

        # Walls: 0 so infill fills everything
        "-s", "wall_line_count=0",
        "-s", "wall_thickness=0",
        "-s", "top_layers=0",
        "-s", "bottom_layers=0",
        "-s", "top_bottom_thickness=0",

        # Infill: 100 % straight lines at nozzle width
        "-s", "infill_sparse_density=100",
        "-s", "infill_pattern=lines",
        "-s", "infill_angles=[0]",
        "-s", f"infill_line_width={nozzle}",
        "-s", f"line_width={nozzle}",
        "-s", "connect_infill_polygons=true",
        "-s", "inset_direction=outside_in",

        # Thin-feature safety net
        "-s", "print_thin_walls=true",
        "-s", "fill_outline_gaps=true",
        "-s", "fill_perimeter_gaps=everywhere",
        "-s", "filter_out_tiny_gaps=false",
        "-s", f"min_wall_line_width={nozzle * 0.25}",

        # Layer height
        "-s", f"layer_height={z_height}",
        "-s", f"layer_height_0={z_height}",

        # Speed (mm/s internally — CuraEngine uses mm/s)
        "-s", f"speed_print={speed}",
        "-s", f"speed_travel={speed}",
        "-s", f"speed_infill={speed}",
        "-s", f"speed_wall={speed}",
        "-s", f"speed_wall_0={speed}",
        "-s", f"speed_wall_x={speed}",
        "-s", f"speed_layer_0={speed}",

        # No temperature / retraction (ink printer)
        "-s", "material_print_temperature=25",
        "-s", "material_bed_temperature=25",
        "-s", "retraction_enable=false",
        "-s", "retraction_amount=0",
        "-s", "retraction_speed=0",
        "-s", "adhesion_type=none",

        # Roof (required when top=0)
        "-s", "roofing_layer_count=0",
        "-s", "roofing_monotonic=true",
    ]

    # ── Overlay with user profile ────────────────────────────────────────────
    if profile:
        cmd.extend(_profile_to_args(profile))

    cmd += ["-l", str(stl_file), "-o", str(gcode_file)]

    print("\n  [CuraEngine] Running slice ...")
    print("  CMD:", " ".join(cmd[:10]), "... (truncated)")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout.strip():
        print("\n  -- CuraEngine STDOUT --")
        print(result.stdout[-3000:])   # last 3 000 chars to keep output tidy

    if result.stderr.strip():
        print("  -- CuraEngine STDERR --")
        print(result.stderr[-2000:])

    if result.returncode != 0:
        print(f"\n  [error] CuraEngine exited with code {result.returncode}")
        return False

    # Post-process: Change ;TYPE:SKIN to ;TYPE:WALL so the 3D preview renders it as a Red wall instead of Yellow skin
    try:
        with open(gcode_file, "r") as f:
            gcode_data = f.read()
        gcode_data = gcode_data.replace(";TYPE:SKIN", ";TYPE:WALL")
        with open(gcode_file, "w") as f:
            f.write(gcode_data)
    except Exception as e:
        print(f"  [warn] Could not post-process G-code colors: {e}")

    print(f"  -> G-code saved: {gcode_file}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 – Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def convert(
    svg_file: str,
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
    Full SVG → G-code conversion (no UI).

    Returns True on success, False on any failure.
    """
    print("=" * 60)
    print(" SVG  ->  G-code  Converter  (Custom Slicer)")
    print("=" * 60)
    print(f"  Input  : {svg_file}")
    print(f"  Output : {gcode_file}")
    print(f"  Scale  : {scale}x   Z-height: {z_height}mm   Speed: {speed}mm/min   Nozzle: {nozzle}mm")

    # ── 1. SVG → polygons ────────────────────────────────────────────────────
    print("\n[Step 1/2] Parsing SVG ...")
    polygons = svg_to_polygons(svg_file, nozzle=nozzle)
    if not polygons:
        print("  [error] No valid polygons found in the SVG.")
        return False

    if scale != 1.0:
        polygons = [shapely_scale(p, xfact=scale, yfact=scale, origin=(0, 0)) for p in polygons]

    # ── 2. Polygons → G-code ──────────────────────────────────────────────────────
    print("\n[Step 2/2] Slicing with Custom 2D Slicer ...")
    
    ok = slice_polygons(
        polygons=polygons, 
        gcode_file=gcode_file, 
        nozzle=nozzle, 
        speed=speed, 
        z_height=z_height,
        wall_line_count=0
    )

    if ok:
        print("\n[OK] Conversion complete!")
    else:
        print("\n[FAIL] Conversion failed.")
    print("=" * 60)
    return ok


def _safe_remove(path: str):
    try:
        os.remove(path)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="svg_to_gcode",
        description="Convert an SVG file to G-code without any GUI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("svg",   help="Path to the input SVG file")
    p.add_argument("gcode", help="Path for the output .gcode file")

    p.add_argument("--scale",    type=float, default=1.0,
                   help="Uniform scale factor applied to SVG geometry (default: 1.0)")
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
        svg_file     = args.svg,
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
