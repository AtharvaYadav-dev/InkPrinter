import math
import numpy as np
from shapely.geometry import Polygon, LineString, Point, MultiLineString
from typing import List, Tuple

def generate_infill_lines(polygon: Polygon, angle_deg: float, spacing: float) -> List[LineString]:
    """
    Generate parallel infill lines for a polygon at a given angle.
    """
    if polygon.is_empty:
        return []

    # Rotate polygon by -angle to make lines horizontal
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(-angle_rad)
    sin_a = math.sin(-angle_rad)
    
    def rotate_coords(coords, c, s):
        return [(x * c - y * s, x * s + y * c) for x, y in coords]

    # Extract all rings
    def rotate_poly(poly):
        ext = rotate_coords(poly.exterior.coords, cos_a, sin_a)
        ints = [rotate_coords(ring.coords, cos_a, sin_a) for ring in poly.interiors]
        return Polygon(ext, ints)

    if polygon.geom_type == 'Polygon':
        rot_poly = rotate_poly(polygon)
    elif polygon.geom_type == 'MultiPolygon':
        from shapely.ops import unary_union
        rot_poly = unary_union([rotate_poly(p) for p in polygon.geoms])
    else:
        return []

    minx, miny, maxx, maxy = rot_poly.bounds
    
    # Generate horizontal lines
    lines = []
    y = miny + spacing / 2.0
    while y <= maxy:
        line = LineString([(minx - 1, y), (maxx + 1, y)])
        lines.append(line)
        y += spacing

    # Intersect with polygon
    multiline = MultiLineString(lines)
    intersection = rot_poly.intersection(multiline)
    
    result_lines = []
    if intersection.geom_type == 'LineString':
        result_lines.append(intersection)
    elif intersection.geom_type == 'MultiLineString':
        result_lines.extend(list(intersection.geoms))
    elif intersection.geom_type == 'GeometryCollection':
        for geom in intersection.geoms:
            if geom.geom_type == 'LineString':
                result_lines.append(geom)
            elif geom.geom_type == 'MultiLineString':
                result_lines.extend(list(geom.geoms))

    # Rotate back
    cos_inv = math.cos(angle_rad)
    sin_inv = math.sin(angle_rad)
    
    final_lines = []
    for line in result_lines:
        rot_back = rotate_coords(line.coords, cos_inv, sin_inv)
        final_lines.append(LineString(rot_back))
        
    return final_lines

def extract_perimeters(polygon: Polygon) -> List[LineString]:
    """
    Extract the exterior and interior rings of a polygon as LineStrings.
    """
    lines = []
    if polygon.geom_type == 'Polygon':
        lines.append(LineString(polygon.exterior.coords))
        for interior in polygon.interiors:
            lines.append(LineString(interior.coords))
    elif polygon.geom_type == 'MultiPolygon':
        for poly in polygon.geoms:
            lines.append(LineString(poly.exterior.coords))
            for interior in poly.interiors:
                lines.append(LineString(interior.coords))
    return lines

def optimize_paths_tsp(paths: List[LineString], start_pt: Tuple[float, float] = (0.0, 0.0)) -> List[LineString]:
    """
    Greedy TSP to minimize travel distance between paths.
    """
    if not paths:
        return []

    unvisited = list(paths)
    current_pt = start_pt
    optimized = []

    while unvisited:
        best_idx = -1
        best_dist = float('inf')
        best_reverse = False
        
        for i, path in enumerate(unvisited):
            p_start = path.coords[0]
            p_end = path.coords[-1]
            
            d_start = (current_pt[0] - p_start[0])**2 + (current_pt[1] - p_start[1])**2
            d_end = (current_pt[0] - p_end[0])**2 + (current_pt[1] - p_end[1])**2
            
            if d_start < best_dist:
                best_dist = d_start
                best_idx = i
                best_reverse = False
            
            if d_end < best_dist:
                best_dist = d_end
                best_idx = i
                best_reverse = True
                
        chosen_path = unvisited.pop(best_idx)
        if best_reverse:
            chosen_path = LineString(chosen_path.coords[::-1])
            
        optimized.append(chosen_path)
        current_pt = chosen_path.coords[-1]

    # 2. 2-opt Post-Processing
    def dist(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    improved = True
    while improved:
        improved = False
        for i in range(1, len(optimized) - 1):
            for j in range(i + 1, len(optimized)):
                p_i_minus_1_end = optimized[i-1].coords[-1]
                p_i_start = optimized[i].coords[0]
                p_j_end = optimized[j].coords[-1]
                
                if j + 1 < len(optimized):
                    p_j_plus_1_start = optimized[j+1].coords[0]
                    d_curr = dist(p_i_minus_1_end, p_i_start) + dist(p_j_end, p_j_plus_1_start)
                    d_new = dist(p_i_minus_1_end, p_j_end) + dist(p_i_start, p_j_plus_1_start)
                else:
                    d_curr = dist(p_i_minus_1_end, p_i_start)
                    d_new = dist(p_i_minus_1_end, p_j_end)
                
                if d_new < d_curr - 1e-5:
                    sub_reversed = []
                    for k in range(j, i - 1, -1):
                        sub_reversed.append(LineString(optimized[k].coords[::-1]))
                    optimized[i:j+1] = sub_reversed
                    improved = True
                    break
            if improved:
                break

    return optimized

def calculate_e(dist: float, line_width: float, layer_height: float, filament_dia: float = 1.75) -> float:
    """
    Calculate E value using Cura's volumetric formula.
    """
    vol = dist * line_width * layer_height
    fil_area = math.pi * (filament_dia / 2.0)**2
    return vol / fil_area

def slice_layers(
    layers_polygons: List[List[Polygon]], 
    gcode_file: str, 
    nozzle: float = 0.4, 
    speed: int = 1000, 
    z_height: float = 0.4,
    wall_line_count: int = 0,
    infill_angle: float = 45.0,
    z_hop: float = 5.0
) -> bool:
    """
    Converts a list of layers (each a list of Shapely Polygons) into a complete 3D G-code.
    """
    try:
        print(f"  -> Generating G-code: {gcode_file}")
        with open(gcode_file, 'w') as f:
            # Header
            f.write("; FLAVOR:Marlin\n")
            f.write("; Generated by Custom 3D Slicer\n")
            f.write("G21 ; set units to millimeters\n")
            f.write("G90 ; use absolute coordinates\n")
            f.write("M82 ; absolute extrusion mode\n")
            f.write("G28 ; Home all axes\n")
            f.write("G92 E0\n")
            
            f.write(f"G0 Z{z_hop:.3f} F{speed}\n")
            
            current_e = 0.0
            current_head_pos = (0.0, 0.0)
            
            for layer_idx, polygons in enumerate(layers_polygons):
                if not polygons:
                    continue
                    
                current_z = (layer_idx + 1) * z_height
                
                # Alternate angle by 90 degrees per layer
                current_angle = infill_angle if layer_idx % 2 == 0 else infill_angle + 90.0
                
                perimeter_paths = []
                infill_paths = []
                for poly in polygons:
                    if wall_line_count > 0:
                        perimeter_paths.extend(extract_perimeters(poly))
                        
                    infill = generate_infill_lines(poly, current_angle, nozzle)
                    infill_paths.extend(infill)
                
                if not perimeter_paths and not infill_paths:
                    continue
                    
                optimized_paths = []
                if perimeter_paths:
                    opt_perim = optimize_paths_tsp(perimeter_paths, current_head_pos)
                    optimized_paths.extend(opt_perim)
                    current_head_pos = opt_perim[-1].coords[-1]
                    
                if infill_paths:
                    opt_infill = optimize_paths_tsp(infill_paths, current_head_pos)
                    optimized_paths.extend(opt_infill)
                    current_head_pos = opt_infill[-1].coords[-1]
                
                # Write layer indicator
                f.write(f";LAYER:{layer_idx}\n")
                
                for path in optimized_paths:
                    coords = list(path.coords)
                    if not coords:
                        continue
                        
                    start_x, start_y = coords[0]
                    f.write(f"G0 X{start_x:.3f} Y{start_y:.3f}\n")
                    f.write(f"G0 Z{current_z:.3f}\n")
                    
                    current_x, current_y = start_x, start_y
                    for i in range(1, len(coords)):
                        nx, ny = coords[i]
                        dist = math.hypot(nx - current_x, ny - current_y)
                        e_step = calculate_e(dist, nozzle, z_height)
                        current_e += e_step
                        f.write(f"G1 X{nx:.3f} Y{ny:.3f} E{current_e:.5f} F{speed}\n")
                        current_x, current_y = nx, ny
                        
                    f.write(f"G0 Z{(current_z + z_hop):.3f}\n")

            # Footer
            f.write("G91 ; relative positioning\n")
            f.write("G0 Z10.000 F3000 ; lift Z 10mm\n")
            f.write("G90 ; absolute positioning\n")
            f.write("G28 X Y ; present print\n")
            f.write("M106 S0 ;Turn-off fan\n")
            f.write("M104 S0 ;Turn-off hotend\n")
            f.write("M140 S0 ;Turn-off bed\n")
            f.write("M84 X Y E ; disable steppers but Z\n")

        return True

    except Exception as e:
        print(f"  [error] Slicing failed: {e}")
        return False

def slice_polygons(
    polygons: List[Polygon], 
    gcode_file: str, 
    nozzle: float = 0.4, 
    speed: int = 1000, 
    z_height: float = 0.4,
    wall_line_count: int = 0,
    infill_angle: float = 45.0,
    z_hop: float = 5.0
) -> bool:
    """
    Wrapper for 2D slicing (single layer).
    """
    return slice_layers(
        [polygons], 
        gcode_file, 
        nozzle, 
        speed, 
        z_height, 
        wall_line_count, 
        infill_angle, 
        z_hop
    )

