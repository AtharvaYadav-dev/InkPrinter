"""
svg_to_gcode.py
===============
Direct SVG to G-code converter (No CuraEngine dependency).

Pipeline
--------
    SVG  ->  svgelements Paths  ->  Shapely Polygons (buffered for strokes)
         ->  Scanline Hatching  ->  G-code generation
"""

import math
import os
import numpy as np
from svgelements import SVG, Path, Shape
from shapely.geometry import Polygon, LineString, MultiPolygon, MultiLineString
from shapely.affinity import rotate as shapely_rotate
from shapely.affinity import scale as shapely_scale
from shapely.ops import unary_union

# ─────────────────────────────────────────────────────────────────────────────
# Configurable Parameters (Defaults)
# ─────────────────────────────────────────────────────────────────────────────

FLIP_Y = True        # CNC systems usually have +Y going up, SVG has +Y going down
EXTRUSION_MULT = 0.033 # Match DXF and BMP

# ─────────────────────────────────────────────────────────────────────────────
# SVG Parsing with svgelements
# ─────────────────────────────────────────────────────────────────────────────

def _parse_to_mm(val) -> float:
    """Convert an SVG unit string to millimetres."""
    if val is None or str(val).strip() == "":
        return None
    import re
    m = re.match(r"([0-9.]+)\s*([a-z%]*)", str(val).strip())
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2).lower()
    mapping = {
        "mm": 1.0, "cm": 10.0, "in": 25.4,
        "pt": 25.4 / 72.0, "px": 25.4 / 96.0, "": 25.4 / 96.0,
    }
    return v * mapping.get(u, 25.4 / 96.0)

def generate_zigzag_infill(poly: Polygon, spacing: float = 0.4, angle_deg: float = 45.0) -> list:
    """
    Generate clean, continuous zigzag scanlines to fill a polygon.
    Adjacent scanlines are connected into continuous strokes to prevent lifting Z / retracting.
    """
    if not poly.is_valid or poly.is_empty or poly.area < 1e-4:
        return []
        
    rotated = shapely_rotate(poly, -angle_deg, origin='centroid')
    minx, miny, maxx, maxy = rotated.bounds
    
    lines = []
    y = miny + spacing / 2.0
    while y < maxy:
        scanline = LineString([(minx - 1, y), (maxx + 1, y)])
        inter = scanline.intersection(rotated)
        if inter.geom_type == 'LineString':
            lines.append(inter)
        elif inter.geom_type == 'MultiLineString':
            lines.extend([g for g in inter.geoms if g.geom_type == 'LineString'])
        y += spacing
        
    rotated_lines = [shapely_rotate(l, angle_deg, origin=poly.centroid) for l in lines]
    
    connected_paths = []
    current_path = []
    
    for i, line in enumerate(rotated_lines):
        coords = list(line.coords)
        if i % 2 == 1:
            coords = coords[::-1]
            
        if not current_path:
            current_path = coords
        else:
            prev_end = current_path[-1]
            curr_start = coords[0]
            dist = math.hypot(curr_start[0] - prev_end[0], curr_start[1] - prev_end[1])
            # If adjacent (distance <= 2.5 * spacing), connect directly!
            if dist <= spacing * 2.5:
                current_path.extend(coords)
            else:
                connected_paths.append(LineString(current_path))
                current_path = coords
                
    if current_path:
        connected_paths.append(LineString(current_path))
        
    return connected_paths

def svg_to_polygons(svg_file: str, nozzle: float = 0.4, resolution: float = 0.1, hatching_enable: bool = True) -> list:
    """
    Parse an SVG file using svgelements and return printable geometry elements (LineStrings and Polygons in mm).
    Properly handles:
    1. Strokes vs Fills (strokes are traced smoothly along paths instead of fragmented into tick marks)
    2. Compound paths with multiple subpaths (e.g. IDT electrodes, letters with holes)
    3. Multi-pass concentric/parallel offsets for thick strokes without choppy infill.
    """
    try:
        svg = SVG.parse(svg_file)
    except Exception as e:
        print(f"Error parsing SVG {svg_file}: {e}")
        return []

    # svgelements normalizes to 96 DPI CSS pixels internally.
    unit_to_mm = 25.4 / 96.0
    
    flip_y_limit_mm = _parse_to_mm(svg.height) if svg.height else 0.0
    if not flip_y_limit_mm and svg.viewbox:
        flip_y_limit_mm = svg.viewbox.height * unit_to_mm

    toolpaths = []

    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
            
        path_obj = Path(element)
        if len(path_obj) == 0:
            continue
            
        # Get styles
        stroke_width = 1.0
        try:
            if hasattr(element, "stroke_width") and element.stroke_width is not None:
                stroke_width = float(element.stroke_width)
        except:
            pass
            
        fill = "none"
        if hasattr(element, "fill") and element.fill is not None:
            fill = str(element.fill).lower()
            if fill in ("none", "transparent"):
                fill = "none"
            
        stroke = "none"
        if hasattr(element, "stroke") and element.stroke is not None:
            stroke = str(element.stroke).lower()
            if stroke in ("none", "transparent"):
                stroke = "none"

        sw_mm = stroke_width * unit_to_mm

        # Process each subpath separately so compound paths (M...z M...z) work properly
        for sp in path_obj.as_subpaths():
            path_mm = []
            for seg in sp:
                try:
                    seg_len = seg.length()
                except:
                    continue
                if seg_len <= 0:
                    continue
                    
                num_samples = max(2, int(seg_len / resolution))
                for i in range(num_samples):
                    t = i / (num_samples - 1)
                    pt = seg.point(t)
                    x = pt.real * unit_to_mm
                    y = pt.imag * unit_to_mm
                    if FLIP_Y and flip_y_limit_mm > 0:
                        y = flip_y_limit_mm - y
                    path_mm.append((x, y))
                    
            if not path_mm:
                continue
                
            pts_array = np.array(path_mm)
            is_closed = np.allclose(pts_array[0], pts_array[-1], atol=1e-3)
            
            # --- CASE 1: Solid Fill (with or without stroke) ---
            if is_closed and fill != "none":
                poly = Polygon(pts_array).simplify(0.01, preserve_topology=True)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_valid and not poly.is_empty:
                    if poly.geom_type == "Polygon":
                        toolpaths.append(poly)
                    elif poly.geom_type == "MultiPolygon":
                        toolpaths.extend(list(poly.geoms))
                        
            # --- CASE 2: Pure Stroke (fill is none) ---
            elif stroke != "none":
                center_line = LineString(pts_array).simplify(0.01, preserve_topology=True)
                n_passes = max(1, int(round(sw_mm / nozzle)))
                
                # Single pass for thin strokes (<= 1.25x nozzle)
                if n_passes <= 1:
                    toolpaths.append(center_line)
                elif is_closed:
                    # Multi-pass concentric loops for closed strokes (e.g. circle-test.svg)
                    poly = Polygon(pts_array).simplify(0.01, preserve_topology=True)
                    step = (sw_mm - nozzle) / (n_passes - 1) if n_passes > 1 else 0.0
                    for k in range(n_passes):
                        offset = - (sw_mm - nozzle) / 2.0 + k * step
                        off_poly = poly.buffer(offset, resolution=16).simplify(0.01, preserve_topology=True)
                        if off_poly.is_valid and not off_poly.is_empty and off_poly.exterior:
                            toolpaths.append(LineString(list(off_poly.exterior.coords)))
                else:
                    # Multi-pass parallel lines for open strokes
                    step = (sw_mm - nozzle) / (n_passes - 1) if n_passes > 1 else 0.0
                    for k in range(n_passes):
                        offset = - (sw_mm - nozzle) / 2.0 + k * step
                        if abs(offset) < 1e-4:
                            toolpaths.append(center_line)
                        else:
                            side = 'left' if offset > 0 else 'right'
                            try:
                                off_line = center_line.parallel_offset(abs(offset), side)
                                if off_line.is_valid and not off_line.is_empty:
                                    if off_line.geom_type == 'LineString':
                                        toolpaths.append(off_line)
                                    elif off_line.geom_type == 'MultiLineString':
                                        toolpaths.extend(list(off_line.geoms))
                            except Exception:
                                toolpaths.append(center_line)
                                
    # Merge overlapping polygons (e.g. PCB pads and fills)
    polys_to_merge = [p for p in toolpaths if p.geom_type in ('Polygon', 'MultiPolygon')]
    lines_to_keep = [p for p in toolpaths if p.geom_type in ('LineString', 'MultiLineString')]
    
    final_geoms = []
    if polys_to_merge:
        try:
            merged = unary_union(polys_to_merge)
            if merged.geom_type == "Polygon":
                final_geoms.append(merged)
            elif merged.geom_type in ("MultiPolygon", "GeometryCollection"):
                for g in merged.geoms:
                    if g.geom_type in ("Polygon", "LineString"):
                        final_geoms.append(g)
        except Exception:
            final_geoms.extend(polys_to_merge)
            
    # Filter out any stroke lines that are redundant duplicates of filled polygon boundaries
    if final_geoms and lines_to_keep:
        merged_poly_union = unary_union([p for p in final_geoms if p.geom_type in ('Polygon', 'MultiPolygon')]).buffer(0.05)
        filtered_lines = [l for l in lines_to_keep if not merged_poly_union.contains(l)]
        final_geoms.extend(filtered_lines)
    else:
        final_geoms.extend(lines_to_keep)
        
    return [p for p in final_geoms if (getattr(p, 'area', 0) > 1e-7 or p.geom_type in ('LineString', 'MultiLineString'))]

# ─────────────────────────────────────────────────────────────────────────────
# G-code Generation
# ─────────────────────────────────────────────────────────────────────────────

def polygons_to_gcode(
    polygons: list, 
    gcode_file: str, 
    speed: int, 
    nozzle: float,
    layer_height: float,
    do_hatching: bool,
    hatching_linewidth: float,
    travel_speed: int = 3000
) -> bool:
    sections_to_print = [] # list of (feature_type, LineString)
    e_multiplier = EXTRUSION_MULT
    
    for geom in polygons:
        if geom.geom_type in ('LineString', 'MultiLineString'):
            if geom.geom_type == 'LineString':
                sections_to_print.append(('WALL', geom))
            else:
                for sub_line in geom.geoms:
                    sections_to_print.append(('WALL', sub_line))
            continue
            
        # For Polygons (solid filled shapes):
        # 1. Wall 1: Outer perimeter
        if geom.exterior:
            sections_to_print.append(('WALL', LineString(list(geom.exterior.coords))))
        for hole in geom.interiors:
            sections_to_print.append(('WALL', LineString(list(hole.coords))))
            
        # 2. Wall 2: Inner perimeter (inset by 1 nozzle diameter, mitre join).
        # Smooth continuous fill along length of narrow traces.
        w2 = geom.buffer(-nozzle, join_style='mitre').simplify(0.01, preserve_topology=True)
        if w2.is_valid and not w2.is_empty:
            w2_geoms = [w2] if w2.geom_type == 'Polygon' else list(w2.geoms)
            for g in w2_geoms:
                if g.exterior:
                    sections_to_print.append(('WALL', LineString(list(g.exterior.coords))))
                for hole in g.interiors:
                    sections_to_print.append(('WALL', LineString(list(hole.coords))))

        # 3. Wall 3: Inset by 2 nozzle diameters (mitre join).
        # Fills medium channels (like 2.4mm rails or busbars) longitudinally with continuous straight passes
        # instead of choppy crosswise zig-zag chatter.
        w3 = geom.buffer(-2.0 * nozzle, join_style='mitre').simplify(0.01, preserve_topology=True)
        if w3.is_valid and not w3.is_empty:
            w3_geoms = [w3] if w3.geom_type == 'Polygon' else list(w3.geoms)
            for g in w3_geoms:
                if g.exterior:
                    sections_to_print.append(('WALL', LineString(list(g.exterior.coords))))
                for hole in g.interiors:
                    sections_to_print.append(('WALL', LineString(list(hole.coords))))

        # 4. Core Infill (if enabled): Inset by 3 nozzle diameters.
        # Thin fingers, rails, and narrow loops are 100% solidly filled by concentric walls.
        # Zig-zag hatching only activates in genuinely wide areas (like contact pads).
        if do_hatching:
            core = geom.buffer(-3.0 * nozzle, join_style='mitre').simplify(0.01, preserve_topology=True)
            if core.is_valid and not core.is_empty:
                islands = [core] if core.geom_type == 'Polygon' else list(core.geoms)
                for island in islands:
                    if island.area > 0.01:
                        # If island is a narrow channel (width < 2*nozzle), fill with centerline wall pass
                        test_inner = island.buffer(-0.25, join_style='mitre')
                        if test_inner.is_empty or test_inner.area < 1.0:
                            if island.exterior:
                                sections_to_print.append(('WALL', LineString(list(island.exterior.coords))))
                        else:
                            # Solid wide pad: clean continuous zigzag infill
                            hatch_lines = generate_zigzag_infill(island, spacing=hatching_linewidth, angle_deg=45.0)
                            for h in hatch_lines:
                                sections_to_print.append(('FILL', h))
                            
    if not sections_to_print:
        print("No valid lines to print.")
        return False

    # 4. Write G-code
    gcode = []
    gcode.append("G21 ; Set units to millimeters")
    gcode.append("G90 ; Absolute positioning")
    gcode.append("M82 ; Absolute extrusion mode")
    gcode.append("G92 E0 ; Reset extruder")
    
    current_e = 0.0
    prev_end = None
    current_type = None
    
    for ftype, line in sections_to_print:
        coords = list(line.coords)
        if not coords or len(coords) < 2:
            continue
            
        if ftype != current_type:
            gcode.append(f";TYPE:{ftype}")
            current_type = ftype
            
        start = coords[0]
        # Only travel if not already at the start point
        if prev_end is None or math.hypot(start[0] - prev_end[0], start[1] - prev_end[1]) > 0.02:
            gcode.append(f"G0 X{start[0]:.3f} Y{start[1]:.3f} F{travel_speed}")
            
        # Print segments
        for i in range(1, len(coords)):
            pt = coords[i]
            prev = coords[i-1]
            dist = math.hypot(pt[0] - prev[0], pt[1] - prev[1])
            if dist <= 1e-4:
                continue
            current_e += dist * e_multiplier
            gcode.append(f"G1 X{pt[0]:.3f} Y{pt[1]:.3f} E{current_e:.5f} F{speed}")
            
        prev_end = coords[-1]
        
    gcode.append("G0 Z5.000 ; lift at end")
    gcode.append("M104 S0 ; turn off temperature")
    gcode.append("M140 S0 ; turn off heatbed")
    gcode.append("M84 ; disable motors")
    
    with open(gcode_file, 'w') as f:
        f.write("\n".join(gcode) + "\n")
        
    return True

# ─────────────────────────────────────────────────────────────────────────────
# Main Entry
# ─────────────────────────────────────────────────────────────────────────────

def convert(
    svg_file: str,
    gcode_file: str,
    nozzle: float = 0.4,
    layer_height: float = 0.4,
    hatching_enable: bool = True,
    hatching_linewidth: float = 0.4
) -> bool:
    """
    Full SVG -> G-code conversion (no Cura UI/CLI needed).
    """
    polygons = svg_to_polygons(svg_file, nozzle=nozzle, hatching_enable=hatching_enable)
    if not polygons:
        return False
        
    ok = polygons_to_gcode(
        polygons=polygons,
        gcode_file=gcode_file,
        speed=1500,
        nozzle=nozzle,
        layer_height=layer_height,
        do_hatching=hatching_enable,
        hatching_linewidth=hatching_linewidth
    )
    
    return ok
