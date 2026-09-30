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

def svg_to_polygons(svg_file: str, nozzle: float = 0.4, resolution: float = 0.1, hatching_enable: bool = True) -> list:
    """
    Parse an SVG file using svgelements and return a list of shapely Polygon objects (in mm).
    """
    try:
        svg = SVG.parse(svg_file)
    except Exception as e:
        print(f"Error parsing SVG {svg_file}: {e}")
        return []

    # svgelements normalizes to 96 DPI CSS pixels internally.
    # To convert these pixel coordinates to mm, we multiply by 25.4 / 96.0.
    unit_to_mm = 25.4 / 96.0
    
    flip_y_limit_mm = _parse_to_mm(svg.height) if svg.height else 0.0
    if not flip_y_limit_mm and svg.viewbox:
        # If no explicit height but viewbox exists, fallback
        flip_y_limit_mm = svg.viewbox.height * unit_to_mm

    polygons = []

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
            
        stroke = "none"
        if hasattr(element, "stroke") and element.stroke is not None:
            stroke = str(element.stroke).lower()

        # Discretize path into points
        path_mm = []
        
        for seg in path_obj:
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
                x, y = pt.real, pt.imag
                
                # Apply unit scale
                x *= unit_to_mm
                y *= unit_to_mm
                
                # Flip Y
                if FLIP_Y and flip_y_limit_mm > 0:
                    y = flip_y_limit_mm - y
                    
                path_mm.append((x, y))
                
        if not path_mm:
            continue
            
        pts_array = np.array(path_mm)
        sub_closed = np.allclose(pts_array[0], pts_array[-1], atol=1e-3)
        
        sw_mm = stroke_width * unit_to_mm
        
        if sub_closed and fill != "none":
            # Solid fill
            if not np.array_equal(pts_array[0], pts_array[-1]):
                pts_array = np.vstack([pts_array, pts_array[0]])
            poly = Polygon(pts_array).simplify(0.01, preserve_topology=True)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_valid and not poly.is_empty:
                if poly.geom_type == "Polygon":
                    polygons.append(poly)
                elif poly.geom_type == "MultiPolygon":
                    polygons.extend(list(poly.geoms))
                    
        elif stroke != "none" and sw_mm > 0.01:
            # Stroke
            line = LineString(pts_array).simplify(0.01, preserve_topology=True)
            
            # If the stroke width is significant (e.g. Gerber thick track), we buffer it into a polygon.
            # If it's a very thin line (like a contour in ide2.svg), we keep it as a simple line.
            if sw_mm > nozzle * 0.5 or (hatching_enable and sw_mm > 0.15):
                poly = line.buffer(sw_mm/2.0, cap_style=1, join_style=1).simplify(0.01, preserve_topology=True)
                if poly.is_valid and not poly.is_empty:
                    if poly.geom_type == "Polygon":
                        polygons.append(poly)
                    elif poly.geom_type == "MultiPolygon":
                        polygons.extend(list(poly.geoms))
            else:
                if line.is_valid and not line.is_empty:
                    if line.geom_type == "LineString":
                        polygons.append(line)
                    elif line.geom_type == "MultiLineString":
                        polygons.extend(list(line.geoms))
                        
    # Filter out empty geometry
    valid_geoms = [p for p in polygons if (p.area > 1e-7 or p.geom_type == 'LineString')]
    
    # Merge overlapping polygons (e.g. PCB tracks and pads from Gerber) into a single clean outline
    polys_to_merge = [p for p in valid_geoms if p.geom_type in ('Polygon', 'MultiPolygon')]
    lines_to_keep = [p for p in valid_geoms if p.geom_type in ('LineString', 'MultiLineString')]
    
    final_geoms = []
    merged_poly = None
    if polys_to_merge:
        try:
            merged_poly = unary_union(polys_to_merge)
            if merged_poly.geom_type in ("Polygon", "LineString"):
                final_geoms.append(merged_poly)
            elif merged_poly.geom_type in ("MultiPolygon", "MultiLineString", "GeometryCollection"):
                for geom in merged_poly.geoms:
                    if geom.geom_type in ("Polygon", "LineString"):
                        final_geoms.append(geom)
        except Exception:
            final_geoms.extend(polys_to_merge)
            
    # Filter out redundant lines that are already covered by the filled polygons
    if merged_poly is not None and not merged_poly.is_empty:
        # Buffer slightly to account for lines exactly on the boundary
        covered_area = merged_poly.buffer(0.05)
        filtered_lines = []
        for line in lines_to_keep:
            if not covered_area.contains(line):
                filtered_lines.append(line)
        lines_to_keep = filtered_lines
            
    final_geoms.extend(lines_to_keep)
    
    return [p for p in final_geoms if p.area > 1e-7 or p.geom_type == 'LineString']

# ─────────────────────────────────────────────────────────────────────────────
# Hatching Algorithm
# ─────────────────────────────────────────────────────────────────────────────

def _generate_scanlines(poly: Polygon, angle_deg: float, spacing: float) -> list:
    """Helper to generate parallel scanlines at a specific angle."""
    rotated = shapely_rotate(poly, -angle_deg, origin='centroid')
    minx, miny, maxx, maxy = rotated.bounds
    
    lines = []
    y = miny + spacing/2
    while y < maxy:
        scanline = LineString([(minx - 1, y), (maxx + 1, y)])
        intersection = scanline.intersection(rotated)
        if intersection.geom_type == 'LineString':
            lines.append(intersection)
        elif intersection.geom_type == 'MultiLineString':
            lines.extend([geom for geom in intersection.geoms if geom.geom_type == 'LineString'])
        y += spacing
        
    return [shapely_rotate(line, angle_deg, origin=poly.centroid) for line in lines]

def hatch_polygon(poly: Polygon, angle_deg: float, spacing: float) -> list:
    """Fills a polygon smartly with both horizontal and vertical lines to minimize travel."""
    # 1. Generate both horizontal and vertical lines
    h_lines = _generate_scanlines(poly, 0.0, spacing)
    v_lines = _generate_scanlines(poly, 90.0, spacing)
    
    # 2. Sort all lines by length (longest first)
    all_lines = h_lines + v_lines
    all_lines.sort(key=lambda l: l.length, reverse=True)
    
    hatched_lines = []
    covered_area = Polygon()
    
    # Buffer by slightly less than spacing so perpendicular lines leave a tiny gap (prevents ink smudging)
    buffer_radius = spacing * 0.99
    
    for line in all_lines:
        if covered_area.is_empty:
            uncovered = line
        else:
            uncovered = line.difference(covered_area)
            
        if uncovered.is_empty:
            continue
            
        segments = []
        if uncovered.geom_type == 'LineString':
            segments.append(uncovered)
        elif uncovered.geom_type == 'MultiLineString':
            segments.extend(list(uncovered.geoms))
            
        for seg in segments:
            # Only keep segments that are decently long to avoid tiny dots
            if seg.length > spacing * 0.5:
                hatched_lines.append(seg)
                # cap_style=2 is flat caps (butt). Ensures buffer doesn't extend beyond endpoints
                seg_buffer = seg.buffer(buffer_radius, cap_style=2)
                if covered_area.is_empty:
                    covered_area = seg_buffer
                else:
                    covered_area = covered_area.union(seg_buffer)
                    
    # Greedy pathing to minimize travel distance between segments
    if not hatched_lines:
        return []
        
    optimized_lines = []
    unvisited = hatched_lines
    
    current_line = unvisited.pop(0)
    optimized_lines.append(current_line)
    current_point = current_line.coords[-1]
    
    while unvisited:
        best_idx = -1
        best_dist = float('inf')
        best_reverse = False
        
        for i, line in enumerate(unvisited):
            p_start = line.coords[0]
            dist_start = (p_start[0] - current_point[0])**2 + (p_start[1] - current_point[1])**2
            
            p_end = line.coords[-1]
            dist_end = (p_end[0] - current_point[0])**2 + (p_end[1] - current_point[1])**2
            
            if dist_start < best_dist:
                best_dist = dist_start
                best_idx = i
                best_reverse = False
                
            if dist_end < best_dist:
                best_dist = dist_end
                best_idx = i
                best_reverse = True
                
        next_line = unvisited.pop(best_idx)
        if best_reverse:
            next_line = LineString(list(next_line.coords)[::-1])
            
        optimized_lines.append(next_line)
        current_point = next_line.coords[-1]
        
    return optimized_lines

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
    
    lines_to_print = []
    
    # Standard heights mimicking DXF and BMP parsers
    travel_z = 2.0
    print_z = layer_height
    e_multiplier = EXTRUSION_MULT
    
    for poly in polygons:
        if getattr(poly, 'geom_type', '') == 'LineString':
            lines_to_print.append(poly)
            continue
            
        # 1. Outline the polygon FIRST
        if poly.exterior:
            lines_to_print.append(LineString(list(poly.exterior.coords)))
        for interior in poly.interiors:
            lines_to_print.append(LineString(list(interior.coords)))

        # 2. Fill the polygon (if enabled) AFTER outline
        if do_hatching:
            # Add padding so hatching lines don't touch the outline border
            padding_size = hatching_linewidth / 2.0
            padded_poly = poly.buffer(-padding_size)
            
            if padded_poly.is_valid and not padded_poly.is_empty:
                if padded_poly.geom_type == "Polygon":
                    hatch_lines = hatch_polygon(padded_poly, angle_deg=0.0, spacing=hatching_linewidth)
                    lines_to_print.extend(hatch_lines)
                elif padded_poly.geom_type == "MultiPolygon":
                    for p in padded_poly.geoms:
                        if p.geom_type == "Polygon":
                            hatch_lines = hatch_polygon(p, angle_deg=0.0, spacing=hatching_linewidth)
                            lines_to_print.extend(hatch_lines)
            
    if not lines_to_print:
        print("No valid lines to print.")
        return False

    # 3. Write G-code
    gcode = []
    gcode.append("G21 ; Set units to millimeters")
    gcode.append("G90 ; Absolute positioning")
    gcode.append("M82 ; Absolute extrusion mode")
    gcode.append("G92 E0 ; Reset extruder")
    
    current_e = 0.0
    for line in lines_to_print:
        coords = list(line.coords)
        if not coords:
            continue
            
        start = coords[0]
        # Travel to start of line (Optimized combined XYZ move)
        gcode.append(f"G0 X{start[0]:.3f} Y{start[1]:.3f} Z{travel_z:.3f} F{travel_speed}")
        gcode.append(f"G1 Z{print_z:.3f} F{speed}")
        
        # Print segments
        for i in range(1, len(coords)):
            pt = coords[i]
            prev = coords[i-1]
            dist = math.dist(pt, prev)
            current_e += dist * e_multiplier
            gcode.append(f"G1 X{pt[0]:.3f} Y{pt[1]:.3f} E{current_e:.5f} F{speed}")
            
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
