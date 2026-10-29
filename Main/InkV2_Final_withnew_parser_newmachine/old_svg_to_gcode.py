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

def svg_to_polygons(svg_file: str, nozzle: float = 0.4, resolution: float = 0.1) -> list:
    """
    Parse an SVG file using svgelements and return a list of shapely Polygon objects (in mm).
    """
    try:
        svg = SVG.parse(svg_file)
    except Exception as e:
        print(f"Error parsing SVG {svg_file}: {e}")
        return []

    # Get document scale
    unit_to_mm = 25.4 / 96.0
    doc_width_mm = _parse_to_mm(svg.width)
    if svg.viewbox:
        vb = svg.viewbox
        if doc_width_mm:
            unit_to_mm = doc_width_mm / vb.width
    
    flip_y_limit_mm = _parse_to_mm(svg.height) if svg.height else 0.0
    if svg.viewbox:
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
            # Buffer the stroke to a polygon
            poly = line.buffer(max(nozzle/2, sw_mm/2.0)).simplify(0.01, preserve_topology=True)
            if poly.is_valid and not poly.is_empty:
                if poly.geom_type == "Polygon":
                    polygons.append(poly)
                elif poly.geom_type == "MultiPolygon":
                    polygons.extend(list(poly.geoms))

    polygons = [p for p in polygons if p.area > 1e-7]
    return polygons

# ─────────────────────────────────────────────────────────────────────────────
# Hatching Algorithm
# ─────────────────────────────────────────────────────────────────────────────

def hatch_polygon(poly: Polygon, angle_deg: float, spacing: float) -> list:
    """Fills a polygon with parallel lines at a given angle and spacing."""
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
        
    hatched_lines = [shapely_rotate(line, angle_deg, origin=poly.centroid) for line in lines]
    
    # Alternate directions to avoid long travels (zigzag)
    for i in range(1, len(hatched_lines), 2):
        coords = list(hatched_lines[i].coords)
        hatched_lines[i] = LineString(coords[::-1])
        
    return hatched_lines

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
        # 1. Fill the polygon (if enabled)
        if do_hatching:
            hatch_lines = hatch_polygon(poly, angle_deg=45.0, spacing=hatching_linewidth)
            lines_to_print.extend(hatch_lines)
        
        # 2. Outline the polygon
        if poly.exterior:
            lines_to_print.append(LineString(list(poly.exterior.coords)))
        for interior in poly.interiors:
            lines_to_print.append(LineString(list(interior.coords)))
            
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
    polygons = svg_to_polygons(svg_file, nozzle=nozzle)
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
