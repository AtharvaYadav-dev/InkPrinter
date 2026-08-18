
from shapely.geometry import Polygon, LineString, MultiLineString
import matplotlib.pyplot as plt

spacing = 0.4
dense_spacing = spacing * 0.85

# Create a polygon simulating inner_poly with a trunk and fingers
# Trunk: x in [0, 2], y in [0, 20]
# Finger 1 (hit by grid): x in [2, 10], y in [2, 2.5]
# Finger 2 (missed by grid): x in [2, 10], y in [4, 4.2]

inner_poly = Polygon([
    (0, 0), (2, 0),
    (2, 2), (10, 2), (10, 2.5), (2, 2.5),
    (2, 4), (10, 4), (10, 4.2), (2, 4.2),
    (2, 20), (0, 20)
])

minx, miny, maxx, maxy = inner_poly.bounds
grid_offset = spacing * 0.5

h_lines = []
y = miny + grid_offset
while y <= maxy:
    h_lines.append(LineString([(minx - 1, y), (maxx + 1, y)]))
    y += dense_spacing

v_lines = []
x = minx + grid_offset
while x <= maxx:
    v_lines.append(LineString([(x, miny - 1), (x, maxy + 1)]))
    x += dense_spacing

def extract_segments(geom):
    if geom.is_empty: return []
    if geom.geom_type == "LineString": return [geom]
    elif geom.geom_type == "MultiLineString": return list(geom.geoms)
    return []

h_segments = extract_segments(MultiLineString(h_lines).intersection(inner_poly))
v_segments = extract_segments(MultiLineString(v_lines).intersection(inner_poly))

open_radius = dense_spacing * 0.6
thick_poly = inner_poly.buffer(-open_radius, join_style=2).buffer(open_radius, join_style=2)
thin_poly = inner_poly.difference(thick_poly)

def extract_polygons(geom):
    if geom.geom_type == "Polygon": return [geom]
    if geom.geom_type == "MultiPolygon": return list(geom.geoms)
    if geom.geom_type == "GeometryCollection": return [g for g in geom.geoms if g.geom_type == "Polygon"]
    return []

print(f"h_segments initially: {len(h_segments)}")

for p in extract_polygons(thin_poly):
    p_minx, p_miny, p_maxx, p_maxy = p.bounds
    w = p_maxx - p_minx
    h = p_maxy - p_miny
    print(f"Thin poly: w={w:.2f}, h={h:.2f}")
    
    if w > h * 1.5 and w > spacing * 1.5:
        has_line = False
        for seg in h_segments:
            if seg.intersects(p) and seg.intersection(p).length > spacing * 0.5:
                has_line = True
                break
        print(f"  has_line: {has_line}")
        if not has_line:
            mid_y = (p_miny + p_maxy) / 2.0
            print(f"  Adding gap-fill line at mid_y={mid_y}")
            full_line = LineString([(minx - 1, mid_y), (maxx + 1, mid_y)])
            for seg in extract_segments(full_line.intersection(inner_poly)):
                if seg.intersects(p) and seg.intersection(p).length > spacing * 0.5:
                    h_segments.append(seg)
                    print(f"    Appended segment of length {seg.length:.2f}")

print(f"h_segments after: {len(h_segments)}")

