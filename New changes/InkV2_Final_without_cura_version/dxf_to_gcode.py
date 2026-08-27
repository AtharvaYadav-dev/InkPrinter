import ezdxf
from ezdxf import path
import math
import os

def calculate_distance(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def convert(dxf_file: str, gcode_file: str, nozzle: float = 0.4, layer_height: float = 0.4) -> bool:
    """
    Parses a DXF file and generates G-code mimicking a single layer 3D print.
    """
    try:
        doc = ezdxf.readfile(dxf_file)
        msp = doc.modelspace()
        
        gcode = []
        gcode.append("G21 ; Set units to millimeters")
        gcode.append("G90 ; Absolute positioning")
        gcode.append("M82 ; Absolute extrusion mode")
        gcode.append("G92 E0 ; Reset extruder")
        
        # Slicing parameters
        travel_speed = 3000
        print_speed = 1500
        z_hop = 2.0
        
        e_pos = 0.0
        # Extrusion multiplier approximation
        e_factor = 0.033
        
        current_pos = None
        for entity in msp:
            if entity.dxftype() in {'LINE', 'LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'SPLINE'}:
                try:
                    p = path.make_path(entity)
                    # Flatten the path into line segments
                    vertices = list(p.flattening(distance=0.05))
                    
                    if not vertices:
                        continue
                        
                    start = vertices[0]
                    
                    # Travel to start only if it's disconnected from the last position
                    if current_pos is None or calculate_distance((current_pos.x, current_pos.y), (start.x, start.y)) > 0.05:
                        gcode.append(f"G0 X{start.x:.3f} Y{start.y:.3f} Z{z_hop:.3f} F{travel_speed}")
                        gcode.append(f"G1 Z{layer_height:.3f} F{print_speed}")
                    
                    # Draw
                    prev_pt = start
                    for pt in vertices[1:]:
                        dist = calculate_distance((prev_pt.x, prev_pt.y), (pt.x, pt.y))
                        e_pos += dist * e_factor
                        gcode.append(f"G1 X{pt.x:.3f} Y{pt.y:.3f} E{e_pos:.5f}")
                        prev_pt = pt
                        
                    current_pos = vertices[-1]
                        
                except Exception as e:
                    print(f"Skipping entity {entity.dxftype()}: {e}")
        
        gcode.append("G0 Z5.000 ; lift at end")
        gcode.append("M104 S0 ; turn off temperature")
        gcode.append("M140 S0 ; turn off heatbed")
        gcode.append("M84 ; disable motors")
        
        with open(gcode_file, 'w') as f:
            f.write('\n'.join(gcode))
            
        return os.path.exists(gcode_file)
    except Exception as e:
        print(f"Failed to convert DXF to G-code: {e}")
        return False
