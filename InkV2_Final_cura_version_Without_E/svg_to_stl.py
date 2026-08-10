import argparse
import re
import os
import xml.etree.ElementTree as ET
from svgpathtools import Path, Line
from shapely.geometry import Polygon
from shapely.affinity import scale
import trimesh
import numpy as np

def svg_to_polygons(svg_file):
    """Convert SVG elements to list of shapely polygons with style inheritance and correct scaling."""
    from svgpathtools import parse_path
    from svgpathtools.parser import parse_transform
    import numpy as np

    tree = ET.parse(svg_file)
    root = tree.getroot()
    
    # 1. Calculate document-wide scaling (user units to mm)
    width_attr = root.get("width")
    viewbox_attr = root.get("viewBox")
    
    def parse_to_mm(val):
        if val is None: return None
        m = re.match(r"([0-9.]+)\s*([a-z%]*)", str(val).strip())
        if not m: return None
        v, u = float(m.group(1)), m.group(2).lower()
        mapping = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4/72.0, "px": 25.4/96.0, "": 25.4/96.0}
        return v * mapping.get(u, 25.4/96.0)

    doc_width_mm = parse_to_mm(width_attr)
    doc_height_mm = parse_to_mm(root.get("height"))
    unit_to_mm = 25.4 / 96.0 # Default fallback
    
    flip_y_limit_mm = 0
    if viewbox_attr:
        vb = [float(x) for x in viewbox_attr.replace(',', ' ').split()]
        if len(vb) == 4:
            if doc_width_mm:
                unit_to_mm = doc_width_mm / vb[2]
            else:
                # No physical width, assume 1 unit = 1 pixel at 96 DPI
                unit_to_mm = 25.4 / 96.0
            
            # Calculate total height in mm for flipping
            flip_y_limit_mm = (vb[1] + vb[3]) * unit_to_mm
            
    elif doc_width_mm:
        if doc_height_mm:
            flip_y_limit_mm = doc_height_mm
        pass

    def clean_tag(tag):
        return tag.split('}')[-1] if '}' in tag else tag

    def get_styles(elem, inherited=None):
        styles = inherited.copy() if inherited else {"fill": "black", "stroke": "none", "stroke-width": "1"}
        
        # Helper to parse style string
        s_attr = elem.get('style', '')
        style_dict = {}
        for part in s_attr.split(';'):
            if ':' in part:
                try:
                    k, v = part.split(':', 1)
                    style_dict[k.strip()] = v.strip()
                except: continue
        
        for name in ["fill", "stroke", "stroke-width"]:
            val = elem.get(name)
            if val is not None:
                styles[name] = val
            elif name in style_dict:
                styles[name] = style_dict[name]
        return styles

    polygons = []

    def process_element(elem, parent_transform=None, inherited_styles=None):
        tag = clean_tag(elem.tag)
        if tag in ["defs", "metadata", "title", "desc"]: return

        current_styles = get_styles(elem, inherited_styles)
        
        local_transform = None
        t_str = elem.get('transform', '')
        if t_str:
            try: local_transform = parse_transform(t_str)
            except: pass
        
        current_transform = parent_transform
        if local_transform is not None:
            if current_transform is not None:
                current_transform = np.dot(current_transform, local_transform)
            else:
                current_transform = local_transform

        path_d = ""
        is_closed = False

        if tag == 'path':
            path_d = elem.get('d', '')
            if path_d.lower().strip().endswith('z'): is_closed = True
        elif tag == 'rect':
            x, y = float(elem.get('x', 0)), float(elem.get('y', 0))
            w, h = float(elem.get('width', 0)), float(elem.get('height', 0))
            path_d = f"M {x},{y} L {x+w},{y} L {x+w},{y+h} L {x},{y+h} Z"
            is_closed = True
        elif tag == 'circle':
            cx, cy = float(elem.get('cx', 0)), float(elem.get('cy', 0))
            r = float(elem.get('r', 0))
            path_d = f"M {cx-r},{cy} A {r},{r} 0 1,0 {cx+r},{cy} A {r},{r} 0 1,0 {cx-r},{cy} Z"
            is_closed = True
        elif tag == 'ellipse':
            cx, cy = float(elem.get('cx', 0)), float(elem.get('cy', 0))
            rx, ry = float(elem.get('rx', 0)), float(elem.get('ry', 0))
            path_d = f"M {cx-rx},{cy} A {rx},{ry} 0 1,0 {cx+rx},{cy} A {rx},{ry} 0 1,0 {cx-rx},{cy} Z"
            is_closed = True
        elif tag in ['polygon', 'polyline']:
            pts = elem.get('points', '').strip().replace(',', ' ').split()
            if len(pts) >= 4:
                path_d = f"M {pts[0]},{pts[1]}"
                for i in range(2, len(pts), 2):
                    path_d += f" L {pts[i]},{pts[i+1]}"
                if tag == 'polygon':
                    path_d += " Z"
                    is_closed = True

        if path_d:
            try:
                path = parse_path(path_d)
                sub_paths = []
                if len(path) > 0:
                    current_sub = [path[0]]
                    for i in range(1, len(path)):
                        if np.isclose(path[i-1].end.real, path[i].start.real) and \
                           np.isclose(path[i-1].end.imag, path[i].start.imag):
                            current_sub.append(path[i])
                        else:
                            sub_paths.append(current_sub)
                            current_sub = [path[i]]
                    sub_paths.append(current_sub)

                for sub in sub_paths:
                    points = []
                    for seg in sub:
                        samples = 2 if isinstance(seg, Line) else 20
                        for t in np.linspace(0, 1, samples, endpoint=False):
                            p = seg.point(t)
                            points.append([p.real, p.imag])
                    if sub:
                        p_end = sub[-1].end
                        points.append([p_end.real, p_end.imag])

                    if len(points) > 1:
                        pts_array = np.array(points)
                        effective_scale = 1.0
                        if current_transform is not None:
                            pts_h = np.hstack([pts_array, np.ones((pts_array.shape[0], 1))])
                            pts_transformed = np.dot(pts_h, current_transform.T)
                            pts_array = pts_transformed[:, :2]
                            a, c, e = current_transform[0]
                            b, d, f = current_transform[1]
                            effective_scale = (np.sqrt(a*a+b*b) + np.sqrt(c*c+d*d)) / 2.0

                        # Apply document-wide units to mm scale
                        pts_array *= unit_to_mm

                        # Flip Y coordinate to match standard CNC/3D printing (bottom-left origin)
                        # SVG is top-left origin (Y-down)
                        if flip_y_limit_mm > 0:
                            pts_array[:, 1] = flip_y_limit_mm - pts_array[:, 1]

                        sub_closed = is_closed or np.allclose(pts_array[0], pts_array[-1], atol=1e-3)
                        fill = current_styles["fill"].lower()
                        stroke = current_styles["stroke"].lower()
                        sw_str = current_styles["stroke-width"]
                        
                        try:
                            sw = float(re.findall(r"[-+]?\d*\.\d+|\d+", str(sw_str))[0])
                        except:
                            sw = 1.0
                        
                        # Convert sw to mm: sw is in user-units, so sw * effective_scale * unit_to_mm
                        sw_mm = sw * effective_scale * unit_to_mm

                        if sub_closed and fill != 'none':
                            if not np.array_equal(pts_array[0], pts_array[-1]):
                                pts_array = np.vstack([pts_array, pts_array[0]])
                            poly = Polygon(pts_array)
                            if poly.is_valid and not poly.is_empty: polygons.append(poly)
                            elif not poly.is_valid:
                                poly = poly.buffer(0)
                                if poly.is_valid and not poly.is_empty:
                                    if poly.geom_type == 'Polygon': polygons.append(poly)
                                    elif poly.geom_type == 'MultiPolygon': polygons.extend(list(poly.geoms))
                        elif stroke != 'none' and sw_mm > 0.01:
                            # Use LineString buffer to create a path of specific width
                            from shapely.geometry import LineString
                            line = LineString(pts_array)
                            poly = line.buffer(sw_mm / 2.0)
                            if poly.is_valid and not poly.is_empty:
                                if poly.geom_type == 'Polygon': polygons.append(poly)
                                elif poly.geom_type == 'MultiPolygon': polygons.extend(list(poly.geoms))
            except Exception as e:
                print(f"Error processing {tag}: {e}")

        for child in elem:
            process_element(child, current_transform, current_styles)

    process_element(root)
    polygons = [p for p in polygons if p.area > 1e-7]
    return polygons


def polygons_to_stl(polygons, output_file, z_height=1.0, scale_factor=1.0):
    """Convert shapely polygons into 3D STL mesh. Polygons are assumed to be in mm units already."""
    meshes = []

    for poly in polygons:
        # Only apply user-specified scale_factor now, as unit_to_mm is already applied
        corrected_poly = scale(poly, xfact=scale_factor, yfact=scale_factor, origin=(0, 0))

        try:
            try:
                mesh = trimesh.creation.extrude_polygon(corrected_poly, z_height)
            except:
                mesh = trimesh.creation.extrude_polygon(corrected_poly, z_height, triangulation_engine="earcut")
            meshes.append(mesh)
        except Exception as e:
            print(f" Skipping polygon due to error: {e}")

    if meshes:
        combined = trimesh.util.concatenate(meshes)
        combined.vertices = combined.vertices.round(5)
        combined.export(output_file)

        minx, miny, minz = combined.bounds[0]
        maxx, maxy, maxz = combined.bounds[1]
        width = maxx - minx
        height = maxy - miny
        depth = maxz - minz

        print(f" STL file saved: {output_file}")
        print(f" STL Dimensions (mm): width={width:.3f}, height={height:.3f}, depth={depth:.3f}")
        return combined
    else:
        print(" No valid meshes generated.")
        return None


def main():
    parser = argparse.ArgumentParser(description="Convert SVG to STL with accurate unit scaling.")
    parser.add_argument("svg_file", help="Input SVG file path")
    parser.add_argument("output_file", help="Output STL file path")
    parser.add_argument("--scale", type=float, default=1.0, help="Additional scaling factor (default: 1.0)")
    parser.add_argument("--zheight", type=float, default=0.4, help="Extrusion height in mm (default: 0.4)")
    args = parser.parse_args()

    print(f" Processing: {os.path.basename(args.svg_file)}")

    polygons = svg_to_polygons(args.svg_file)
    if not polygons:
        print(" No valid polygons found in SVG file.")
        return

    polygons_to_stl(polygons, args.output_file, args.zheight, args.scale)


if __name__ == "__main__":
    main()
