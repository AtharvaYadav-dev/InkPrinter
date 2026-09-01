import cv2
import math
import os
import numpy as np
from PIL import Image

def calculate_distance(p1, p2):
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def convert(bmp_file: str, gcode_file: str, nozzle: float = 0.4, layer_height: float = 0.4, pixel_size: float = 0.1, invert: bool = False) -> bool:
    """
    Parses a BMP file and generates G-code mimicking a single layer 3D print using OpenCV contours.
    """
    try:
        # 1. Read the image using PIL (for better format support) then convert to numpy
        try:
            pil_img = Image.open(bmp_file).convert("L")
            img = np.array(pil_img)
        except Exception as e:
            print(f"Failed to read BMP with PIL: {e}")
            return False

        # Resize if image is unreasonably massive to prevent freezing
        max_dim = 1500
        if img.shape[1] > max_dim or img.shape[0] > max_dim:
            scale = max_dim / max(img.shape[1], img.shape[0])
            new_w = int(img.shape[1] * scale)
            new_h = int(img.shape[0] * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        if invert:
            img = 255 - img
            
        # 2. Raster Scan Extraction (Mimics 100% Infill)
        # cv2.THRESH_BINARY_INV means dark shapes become white (255) for OpenCV to find.
        # cv2.THRESH_OTSU auto-calculates the best threshold level.
        _, thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        height, width = thresh.shape

        # 3. Generate G-code
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
        e_factor = 0.033
        current_pos = None

        def pt_to_mm(x, y):
            # Flip Y so the image doesn't print upside down
            return (x * pixel_size, (height - y) * pixel_size)

        for y in range(height):
            row = thresh[y, :]
            
            # Find continuous blocks of 255s (black pixels to print)
            in_block = False
            start_x = 0
            blocks = []
            
            for x in range(width):
                if row[x] == 255 and not in_block:
                    in_block = True
                    start_x = x
                elif row[x] == 0 and in_block:
                    in_block = False
                    blocks.append((start_x, x - 1, y))
            
            if in_block:
                blocks.append((start_x, width - 1, y))
                
            if not blocks:
                continue
                
            # Zig-Zag routing: odd rows print right-to-left
            if y % 2 != 0:
                blocks.reverse()
                blocks = [(b[1], b[0], b[2]) for b in blocks]
                
            for blk in blocks:
                start_x, end_x, py = blk
                start_mm = pt_to_mm(start_x, py)
                end_mm = pt_to_mm(end_x, py)
                
                # Travel to start if disconnected
                if current_pos is None or calculate_distance(current_pos, start_mm) > 0.05:
                    gcode.append(f"G0 X{start_mm[0]:.3f} Y{start_mm[1]:.3f} Z{z_hop:.3f} F{travel_speed}")
                    gcode.append(f"G1 Z{layer_height:.3f} F{print_speed}")
                
                # Draw the line segment
                dist = calculate_distance(start_mm, end_mm)
                
                if dist == 0:
                    # Single pixel dot, extrude slightly
                    e_pos += pixel_size * e_factor
                    gcode.append(f"G1 X{end_mm[0]:.3f} Y{end_mm[1]:.3f} E{e_pos:.5f}")
                else:
                    e_pos += dist * e_factor
                    gcode.append(f"G1 X{end_mm[0]:.3f} Y{end_mm[1]:.3f} E{e_pos:.5f}")
                    
                current_pos = end_mm
                        
        gcode.append("G0 Z5.000 ; lift at end")
        gcode.append("M104 S0 ; turn off temperature")
        gcode.append("M140 S0 ; turn off heatbed")
        gcode.append("M84 ; disable motors")
        
        with open(gcode_file, 'w') as f:
            f.write('\n'.join(gcode))
            
        return os.path.exists(gcode_file)
        
    except Exception as e:
        print(f"Failed to convert BMP to G-code: {e}")
        return False
