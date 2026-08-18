
from shapely.geometry import Polygon
import sys
import os
sys.path.append(os.path.abspath("."))
from custom_slicer import generate_smart_orthogonal_infill

# Create a polygon simulating inner_poly with a trunk and fingers
# Trunk: x in [0, 2], y in [0, 20]
# Finger 1 (hit by grid): x in [2, 10], y in [2, 2.5]
# Finger 2 (missed by grid): x in [2, 10], y in [4, 4.2]

outer_poly = Polygon([
    (0, 0), (2.4, 0),
    (2.4, 1.6), (10.4, 1.6), (10.4, 2.9), (2.4, 2.9),
    (2.4, 3.6), (10.4, 3.6), (10.4, 4.6), (2.4, 4.6),
    (2.4, 20), (0, 20)
])

print("Running...")
try:
    res = generate_smart_orthogonal_infill(outer_poly, 0.4, True)
    print(f"Success! Generated {len(res)} lines.")
except Exception as e:
    print(f"Error: {e}")

