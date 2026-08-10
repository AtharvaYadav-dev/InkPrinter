import math
import numpy as np
from shapely.geometry import Polygon, LineString, MultiLineString, MultiPolygon
from shapely.ops import unary_union

def generate_hatch_lines(poly, spacing, angle=0):
    """Generate hatch lines for a single polygon or multipolygon."""
    if not poly.is_valid or poly.is_empty:
        return []
    
    # Rotate the polygon to align hatch lines with X axis
    from shapely.affinity import rotate
    rotated_poly = rotate(poly, -angle, origin='centroid')
    
    minx, miny, maxx, maxy = rotated_poly.bounds
    
    y = miny + spacing / 2.0
    lines = []
    while y <= maxy:
        line = LineString([(minx - 1, y), (maxx + 1, y)])
        intersection = rotated_poly.intersection(line)
        if intersection.is_empty:
            pass
        elif intersection.geom_type == 'LineString':
            lines.append(intersection)
        elif intersection.geom_type == 'MultiLineString':
            lines.extend(list(intersection.geoms))
        elif intersection.geom_type == 'GeometryCollection':
            for geom in intersection.geoms:
                if geom.geom_type == 'LineString':
                    lines.append(geom)
        y += spacing
        
    # Rotate lines back
    rotated_lines = [rotate(line, angle, origin=poly.centroid) for line in lines]
    return rotated_lines

def extract_paths(polygons, spacing, angle=0):
    """
    Given a list of Shapely Polygons, return a list of LineStrings
    representing the perimeters and the hatch infills.
    """
    paths = []
    for poly in polygons:
        if poly.geom_type == 'Polygon':
            # Add exterior
            paths.append(LineString(poly.exterior.coords))
            # Add interiors (holes)
            for interior in poly.interiors:
                paths.append(LineString(interior.coords))
            # Add hatch lines
            paths.extend(generate_hatch_lines(poly, spacing, angle))
        elif poly.geom_type == 'MultiPolygon':
            for p in poly.geoms:
                paths.append(LineString(p.exterior.coords))
                for interior in p.interiors:
                    paths.append(LineString(interior.coords))
                paths.extend(generate_hatch_lines(p, spacing, angle))
        elif poly.geom_type == 'LineString':
            paths.append(poly)
        elif poly.geom_type == 'MultiLineString':
            paths.extend(list(poly.geoms))
            
    return paths

def optimize_paths_tsp_numpy(paths):
    """
    Vectorized greedy nearest-neighbor approach to order LineStrings
    and minimize non-extruding travel distance.
    Extremely fast compared to pure Python loops.
    """
    if not paths:
        return []
        
    num_paths = len(paths)
    starts = np.zeros((num_paths, 2))
    ends = np.zeros((num_paths, 2))
    
    for i, path in enumerate(paths):
        coords = list(path.coords)
        starts[i] = coords[0]
        ends[i] = coords[-1]
        
    ordered = []
    visited = np.zeros(num_paths, dtype=bool)
    current_pos = np.array([0.0, 0.0])
    
    for _ in range(num_paths):
        # Distance squared from current_pos to all unvisited starts
        diff_starts = starts - current_pos
        dist_starts = np.sum(diff_starts**2, axis=1)
        dist_starts[visited] = np.inf
        
        # Distance squared from current_pos to all unvisited ends
        diff_ends = ends - current_pos
        dist_ends = np.sum(diff_ends**2, axis=1)
        dist_ends[visited] = np.inf
        
        min_start_idx = np.argmin(dist_starts)
        min_end_idx = np.argmin(dist_ends)
        
        if dist_starts[min_start_idx] < dist_ends[min_end_idx]:
            best_idx = min_start_idx
            reverse = False
        else:
            best_idx = min_end_idx
            reverse = True
            
        visited[best_idx] = True
        
        coords = list(paths[best_idx].coords)
        if reverse:
            coords.reverse()
            
        ordered.append(LineString(coords))
        current_pos = np.array(coords[-1])
        
    return ordered

def merge_close_paths(paths, threshold=0.1):
    """
    Merge paths where the end of one is very close to the start of the next.
    This connects hatch lines into continuous zig-zag paths and avoids tiny Z-hops.
    """
    if not paths:
        return []
    
    merged = []
    current_coords = list(paths[0].coords)
    
    for i in range(1, len(paths)):
        next_coords = list(paths[i].coords)
        
        # Distance from end of current to start of next
        dist = np.linalg.norm(np.array(current_coords[-1]) - np.array(next_coords[0]))
        
        if dist <= threshold:
            if dist > 1e-6:
                current_coords.extend(next_coords)
            else:
                # Exactly the same point, skip duplicate
                current_coords.extend(next_coords[1:])
        else:
            merged.append(LineString(current_coords))
            current_coords = next_coords
            
    merged.append(LineString(current_coords))
    return merged

def generate_gcode(paths, speed=1000, z_height=0.4, z_hop=5.0):
    """
    Generate the G-code string from the optimized paths.
    Uses M106/M107 instead of E values.
    """
    gcode = []
    gcode.append("; Custom Slicer - InkPrinter V2")
    gcode.append("; Extrusion replaced with M106/M107")
    gcode.append("G90 ; Absolute positioning")
    gcode.append("G21 ; Millimeters")
    gcode.append(f"G0 Z{z_hop:.3f} F{speed} ; Initial Z Hop")
    
    for path in paths:
        coords = list(path.coords)
        if len(coords) < 2:
            continue
            
        start_pt = coords[0]
        
        # Travel to start point
        gcode.append(f"G0 X{start_pt[0]:.3f} Y{start_pt[1]:.3f} F{speed}")
        # Lower tool
        gcode.append(f"G0 Z{z_height:.3f}")
        # Pump ON
        gcode.append("M106")
        
        # Trace path
        for pt in coords[1:]:
            gcode.append(f"G1 X{pt[0]:.3f} Y{pt[1]:.3f} F{speed}")
            
        # Pump OFF
        gcode.append("M107")
        # Z Hop
        gcode.append(f"G0 Z{z_hop:.3f}")
        
    gcode.append("; End of print")
    gcode.append(f"G0 Z{z_hop:.3f} F{speed} ; Final Z Hop")
    return "\n".join(gcode)

def slice_polygons(polygons, gcode_file, nozzle=0.4, speed=1000, z_height=0.4, z_hop=5.0):
    """
    Main entry point for external modules.
    """
    print(f"  -> Generating infill (nozzle={nozzle}) and extracting paths...")
    paths = extract_paths(polygons, spacing=nozzle)
    
    print(f"  -> Optimizing shortest path (TSP) for {len(paths)} toolpaths (Fast Vectorized)...")
    optimized_paths = optimize_paths_tsp_numpy(paths)
    
    # Merge paths closer than 1.5x the nozzle width (connects zig-zag hatches and eliminates tiny Z-hops)
    merge_threshold = max(0.1, nozzle * 1.5)
    print(f"  -> Merging paths closer than {merge_threshold:.2f}mm to create continuous strokes...")
    merged_paths = merge_close_paths(optimized_paths, threshold=merge_threshold)
    print(f"  -> Reduced from {len(optimized_paths)} to {len(merged_paths)} continuous paths.")
    
    print(f"  -> Generating G-code (M106/M107, no E value)...")
    gcode_str = generate_gcode(merged_paths, speed=speed, z_height=z_height, z_hop=z_hop)
    
    with open(gcode_file, 'w') as f:
        f.write(gcode_str)
        
    print(f"  -> Saved G-code to {gcode_file}")
    return True
