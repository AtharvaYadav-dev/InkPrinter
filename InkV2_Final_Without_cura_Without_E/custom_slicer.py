import math
import numpy as np
from shapely.geometry import Polygon, LineString, Point, MultiLineString
from typing import List, Tuple

def get_optimal_infill_angle(poly: Polygon) -> float:
    """
    Calculate the optimal infill angle based on the polygon's minimum rotated rectangle,
    aligning the infill with the longest dimension of the shape.
    """
    try:
        mrr = poly.minimum_rotated_rectangle
        coords = list(mrr.exterior.coords)
        if len(coords) >= 3:
            p0, p1, p2 = coords[0], coords[1], coords[2]
            dist1 = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            dist2 = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            
            if dist1 > dist2:
                dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            else:
                dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                
            return math.degrees(math.atan2(dy, dx))
    except Exception:
        pass
    return 0.0

def generate_smart_orthogonal_infill(polygon: Polygon, spacing: float, has_walls: bool = True) -> List[LineString]:
    """
    Generates horizontal and vertical lines for infill.
    It restricts the infill to the inside of the polygon so it doesn't overlap the perimeter.
    Longer lines cut shorter lines to prevent corner bulges.
    """
    if has_walls:
        # Offset inward to leave room for the perimeter
        inner_poly = polygon.buffer(-spacing + 1e-4, join_style=2)
        grid_offset = spacing
    else:
        # No perimeter, just stay slightly inside the boundary
        inner_poly = polygon.buffer(-1e-4, join_style=2)
        grid_offset = spacing / 2.0
        
    if inner_poly.is_empty:
        return []
        
    minx, miny, maxx, maxy = polygon.bounds
    
    h_lines = []
    y = miny + grid_offset
    while y <= maxy:
        h_lines.append(LineString([(minx - 1, y), (maxx + 1, y)]))
        y += spacing
        
    v_lines = []
    x = minx + grid_offset
    while x <= maxx:
        v_lines.append(LineString([(x, miny - 1), (x, maxy + 1)]))
        x += spacing

    def extract_segments(geom) -> List[LineString]:
        if geom.is_empty: return []
        if geom.geom_type == 'LineString': return [geom]
        elif geom.geom_type == 'MultiLineString': return list(geom.geoms)
        return []

    h_segments = extract_segments(MultiLineString(h_lines).intersection(inner_poly))
    v_segments = extract_segments(MultiLineString(v_lines).intersection(inner_poly))
    
    # Filter out tiny zig-zags and artifacts
    min_len = spacing * 1.5
    h_long = [seg for seg in h_segments if seg.length >= min_len]
    v_long = [seg for seg in v_segments if seg.length >= min_len]
    
    # To prevent the "trunk" (bus) from being chopped into tiny pieces by the "branches" (fingers),
    # we evaluate both possibilities: H cuts V, or V cuts H.
    # We choose the option that results in the FEWEST total line segments, minimizing travel moves.
    buffer_radius = spacing / 2.0 + 1e-4
    
    h_multi = MultiLineString(h_long)
    v_multi = MultiLineString(v_long)
    
    h_buffer = h_multi.buffer(buffer_radius, cap_style=3)
    v_buffer = v_multi.buffer(buffer_radius, cap_style=3)
    
    v_cut_by_h = extract_segments(v_multi.difference(h_buffer))
    h_cut_by_v = extract_segments(h_multi.difference(v_buffer))
    
    pieces_if_h_wins = len(h_long) + len(v_cut_by_h)
    pieces_if_v_wins = len(v_long) + len(h_cut_by_v)
    
    if pieces_if_h_wins < pieces_if_v_wins:
        final_h = h_long
        final_v = v_cut_by_h
    elif pieces_if_v_wins < pieces_if_h_wins:
        final_h = h_cut_by_v
        final_v = v_long
    else:
        # Tie-breaker: which one has the longer max line?
        max_h = max([h.length for h in h_long] + [0])
        max_v = max([v.length for v in v_long] + [0])
        if max_h >= max_v:
            final_h = h_long
            final_v = v_cut_by_h
        else:
            final_h = h_cut_by_v
            final_v = v_long
            
    kept_lines = [seg for seg in final_h + final_v if seg.length >= spacing * 1.2]
    return kept_lines

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

    current_pt = start_pt
    optimized = []

    # 1. Greedy NN (Optimized)
    unvisited_paths = list(paths)
    unvisited_starts = [p.coords[0] for p in unvisited_paths]
    unvisited_ends = [p.coords[-1] for p in unvisited_paths]
    
    while unvisited_paths:
        best_idx = -1
        best_dist = float('inf')
        best_reverse = False
        
        # Cache current point for faster access in the loop
        cx, cy = current_pt
        
        for i in range(len(unvisited_paths)):
            sx, sy = unvisited_starts[i]
            ex, ey = unvisited_ends[i]
            
            d_start = (cx - sx)**2 + (cy - sy)**2
            d_end = (cx - ex)**2 + (cy - ey)**2
            
            if d_start < best_dist:
                best_dist = d_start
                best_idx = i
                best_reverse = False
            
            if d_end < best_dist:
                best_dist = d_end
                best_idx = i
                best_reverse = True
                
        chosen_path = unvisited_paths.pop(best_idx)
        unvisited_starts.pop(best_idx)
        unvisited_ends.pop(best_idx)
        
        if best_reverse:
            chosen_path = LineString(chosen_path.coords[::-1])
            
        optimized.append(chosen_path)
        current_pt = chosen_path.coords[-1]

    # 2. 2-opt Post-Processing (Windowed & Iteration Bounded)
    def dist(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    improved = True
    passes = 0
    max_passes = 2 # strict limit to prevent UI hanging
    window_size = 60 # only check nearby paths in the greedy tour

    while improved and passes < max_passes:
        improved = False
        passes += 1
        
        # Pre-extract coords for speed
        ends = [p.coords[-1] for p in optimized]
        starts = [p.coords[0] for p in optimized]
        
        for i in range(1, len(optimized) - 1):
            limit = min(len(optimized), i + window_size)
            for j in range(i + 1, limit):
                p_i_minus_1_end = ends[i-1]
                p_i_start = starts[i]
                p_j_end = ends[j]
                
                if j + 1 < len(optimized):
                    p_j_plus_1_start = starts[j+1]
                    d_curr = dist(p_i_minus_1_end, p_i_start) + dist(p_j_end, p_j_plus_1_start)
                    d_new = dist(p_i_minus_1_end, p_j_end) + dist(p_i_start, p_j_plus_1_start)
                else:
                    d_curr = dist(p_i_minus_1_end, p_i_start)
                    d_new = dist(p_i_minus_1_end, p_j_end)
                
                if d_new < d_curr - 1e-4:
                    sub_reversed = []
                    for k in range(j, i - 1, -1):
                        sub_reversed.append(LineString(optimized[k].coords[::-1]))
                    optimized[i:j+1] = sub_reversed
                    
                    # Update cached coords
                    for k in range(i, j + 1):
                        starts[k] = optimized[k].coords[0]
                        ends[k] = optimized[k].coords[-1]
                        
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
    wall_line_count: int = 1,
    infill_angle: str | float = 'smart_xy',
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
                    
                # Determine base angle
                if infill_angle == 'smart' or infill_angle == 'smart_xy':
                    base_angle = None
                else:
                    base_angle = float(infill_angle)
                    
                perimeter_paths = []
                infill_paths = []
                
                from shapely.ops import unary_union
                merged = unary_union(polygons)
                if merged.is_empty:
                    continue
                    
                if merged.geom_type == 'Polygon':
                    merged_polys = [merged]
                elif merged.geom_type == 'MultiPolygon':
                    merged_polys = list(merged.geoms)
                else:
                    merged_polys = []
                
                for poly in merged_polys:
                    if wall_line_count > 0:
                        perimeter_paths.extend(extract_perimeters(poly))
                        
                    if infill_angle == 'smart_xy':
                        infill = generate_smart_orthogonal_infill(poly, nozzle, wall_line_count > 0)
                    else:
                        poly_angle = get_optimal_infill_angle(poly) if base_angle is None else base_angle
                        current_angle = poly_angle if layer_idx % 2 == 0 else poly_angle + 90.0
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
    wall_line_count: int = 1,
    infill_angle: str | float = 'smart_xy',
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

