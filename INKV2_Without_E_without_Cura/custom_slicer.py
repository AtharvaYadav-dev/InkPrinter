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

def optimize_paths_tsp(paths):
    """
    Greedy nearest-neighbor approach to order LineStrings
    and minimize non-extruding travel distance.
    Also decides whether to reverse a path if it's closer to start at its end.
    """
    if not paths:
        return []

    unvisited = list(paths)
    ordered = []
    
    # Start at (0, 0)
    current_pos = np.array([0.0, 0.0])
    
    while unvisited:
        best_idx = -1
        best_dist = float('inf')
        reverse_best = False
        
        for i, path in enumerate(unvisited):
            coords = list(path.coords)
            if not coords:
                continue
            
            p_start = np.array(coords[0])
            p_end = np.array(coords[-1])
            
            dist_to_start = np.linalg.norm(current_pos - p_start)
            dist_to_end = np.linalg.norm(current_pos - p_end)
            
            if dist_to_start < best_dist:
                best_dist = dist_to_start
                best_idx = i
                reverse_best = False
                
            if dist_to_end < best_dist:
                best_dist = dist_to_end
                best_idx = i
                reverse_best = True
                
        if best_idx == -1:
            break
            
        best_path = unvisited.pop(best_idx)
        coords = list(best_path.coords)
        
        if reverse_best:
            coords.reverse()
            best_path = LineString(coords)
            
        ordered.append(best_path)
        current_pos = np.array(coords[-1])
        
    return ordered

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
    
    print(f"  -> Optimizing shortest path (TSP) for {len(paths)} toolpaths...")
    optimized_paths = optimize_paths_tsp(paths)
    
    print(f"  -> Generating G-code (M106/M107, no E value)...")
    gcode_str = generate_gcode(optimized_paths, speed=speed, z_height=z_height, z_hop=z_hop)
    
    with open(gcode_file, 'w') as f:
        f.write(gcode_str)
        
    print(f"  -> Saved G-code to {gcode_file}")
    return True
