import os
import tempfile
import numpy as np
from PIL import Image
from skimage.filters import threshold_otsu
from skimage.measure import find_contours
from shapely.geometry import Polygon
from pathlib import Path

from svg_to_stl import polygons_to_stl
from svg_to_gcode import stl_to_gcode, find_cura_path
import custom_slicer

def _safe_remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except:
        pass

def convert(
    bmp_file: str,
    gcode_file: str,
    mode: str = "threshold",
    threshold: int = -1,
    power: int = 255, # ignored now
    pixel_size: float = 0.1,
    feedrate: int = 1000,
    invert: bool = False
) -> bool:
    """
    Convert a BMP file to vector polygons, then to STL, and slice with CuraEngine.
    Returns True on success, False on any failure.
    """
    try:
        print("=" * 60)
        print(" BMP  ->  G-code  Converter (Vectorized)")
        print("=" * 60)
        print(f"  Input  : {bmp_file}")
        print(f"  Output : {gcode_file}")
        
        print("\n[Step 1/3] Tracing BMP contours...")
        
        import cv2
        from PIL import Image
        import numpy as np
        
        try:
            pil_img = Image.open(bmp_file).convert("L")
            img = np.array(pil_img)
        except Exception as e:
            print(f"[FAIL] Could not read BMP file with PIL: {e}")
            return False
            
        # Resize large images to speed up processing
        max_dim = 1000
        if img.shape[1] > max_dim or img.shape[0] > max_dim:
            scale = max_dim / max(img.shape[1], img.shape[0])
            new_w = int(img.shape[1] * scale)
            new_h = int(img.shape[0] * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        if invert:
            img = 255 - img
            
        # Use Otsu's thresholding, but invert the result so black shapes become white (255)
        # cv2.findContours finds white objects on a black background.
        _, thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # RETR_CCOMP extracts a 2-level hierarchy: level 1 is boundaries, level 2 is holes
        contours, hierarchy = cv2.findContours(thresh, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        
        polygons = []
        if hierarchy is not None:
            hierarchy = hierarchy[0]
            for i, h in enumerate(hierarchy):
                # If parent is -1, this is an external contour
                if h[3] == -1:
                    exterior = contours[i].reshape(-1, 2)
                    if len(exterior) >= 3:
                        exterior_coords = [(pt[0] * pixel_size, pt[1] * pixel_size) for pt in exterior]
                        
                        # Find all holes inside this contour
                        interiors = []
                        child_idx = h[2]
                        while child_idx != -1:
                            hole = contours[child_idx].reshape(-1, 2)
                            if len(hole) >= 3:
                                hole_coords = [(pt[0] * pixel_size, pt[1] * pixel_size) for pt in hole]
                                interiors.append(hole_coords)
                            child_idx = hierarchy[child_idx][0] # Next sibling
                            
                        poly = Polygon(exterior_coords, interiors)
                        if poly.is_valid and not poly.is_empty and poly.area > 1e-7:
                            polygons.append(poly)
                    
        if not polygons:
            print("[FAIL] No valid contours found in the image.")
            return False

        # 2. Slice Polygons (Custom Slicer)
        print("\n[Step 2/3] Custom Slicing ...")
        ok = custom_slicer.slice_polygons(polygons, gcode_file, nozzle=pixel_size, speed=feedrate, z_height=0.4)

        if ok:
            print(f"\n[OK] BMP conversion complete. Saved to {gcode_file}")
        else:
            print("\n[FAIL] BMP conversion failed during slicing.")
        return ok
    
    except Exception as e:
        print(f"[FAIL] BMP conversion failed: {e}")
        return False
