import ezdxf
import math
from collections import defaultdict
import configparser

class DXFParser():
    def __init__(self, filepath, config_file=None):
        self.filepath = filepath
        self.doc = ezdxf.readfile(filepath)
        self.msp = self.doc.modelspace()

        # --- Load config ---
        self.config = configparser.ConfigParser()
        if config_file:
            self.config.read(config_file)

        # DXF G-code boundaries
        self.gcode_xmin = 0
        self.gcode_xmax = 0
        self.gcode_ymin = 0
        self.gcode_ymax = 0
        self.gcode_width = 0
        self.gcode_height = 0
        self.gcode_xcenter = 0
        self.gcode_ycenter = 0

        # Bed area
        self.bed_x0 = 0
        self.bed_y0 = 0
        self.bed_width = 0
        self.bed_height = 0

        # --- Z handling from config ---
        self.zpos_safe = 20
        if config_file and "bed" in self.config and "draw_z" in self.config["bed"]:
            self.zpos = float(self.config["bed"]["draw_z"])
        else:
            self.zpos = 0.0  # fallback

        # Feedrate (default from config if available)
        if config_file and "feed" in self.config and "feed" in self.config["feed"]:
            self.feed = int(self.config["feed"]["feed"])
        else:
            self.feed = 1000

        # Translation
        self.tx = 0
        self.ty = 0


    # --- Extract entities ---
    def extractEntities(self):
        entities = defaultdict(list)
        for e in self.msp:
            layer = e.dxf.layer if e.dxf.hasattr('layer') else 'default'
            dxftype = e.dxftype()

            if dxftype == 'LINE':
                entities[layer].append(('LINE', (e.dxf.start.x, e.dxf.start.y, e.dxf.end.x, e.dxf.end.y)))
            elif dxftype == 'CIRCLE':
                entities[layer].append(('CIRCLE', (e.dxf.center.x, e.dxf.center.y, e.dxf.radius)))
            elif dxftype == 'ARC':
                entities[layer].append(('ARC', (e.dxf.center.x, e.dxf.center.y, e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle)))
            elif dxftype in ['LWPOLYLINE', 'POLYLINE']:
                try:
                    if dxftype == 'LWPOLYLINE':
                        points = [(v[0], v[1]) for v in e.get_points()]
                    elif dxftype == 'POLYLINE':
                        points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    entities[layer].append(('POLYLINE', points))
                except Exception as ex:
                    print(f"Warning: Skipped invalid {dxftype} in layer {layer} -> {ex}")


            elif dxftype == 'SPLINE':
                spline_points = list(e.flattening(0.1))
                entities[layer].append(('SPLINE', [(p[0], p[1]) for p in spline_points]))
            elif dxftype == 'ELLIPSE':
                ellipse_points = list(e.flattening(0.1))
                entities[layer].append(('ELLIPSE', [(p[0], p[1]) for p in ellipse_points]))
        return entities
    
    # --- Compute bounding box ---
    def computeBoundary(self, entities):
        all_points = []
        for items in entities.values():
            for etype, data in items:
                if etype == 'LINE':
                    all_points.extend([(data[0], data[1]), (data[2], data[3])])
                elif etype in ['POLYLINE', 'SPLINE', 'ELLIPSE']:
                    all_points.extend(data)
                elif etype == 'CIRCLE':
                    cx, cy, r = data
                    all_points.extend([(cx - r, cy - r), (cx + r, cy + r)])
                elif etype == 'ARC':
                    cx, cy, r, _, _ = data
                    all_points.extend([(cx - r, cy - r), (cx + r, cy + r)])
        xcords = [pt[0] for pt in all_points]
        ycords = [pt[1] for pt in all_points]
        return min(xcords), max(xcords), min(ycords), max(ycords)
    
    # --- Shift entire drawing to 1st quadrant (positive X, Y) ---
    def shiftToFirstQuadrant(self, entities):
        xmin, xmax, ymin, ymax = self.computeBoundary(entities)
        shift_x = -xmin if xmin < 0 else 0
        shift_y = -ymin if ymin < 0 else 0

        if shift_x != 0 or shift_y != 0:
            print(f"Shifting drawing by X={shift_x:.3f}, Y={shift_y:.3f} to move into 1st quadrant")

        shifted = defaultdict(list)
        for layer, items in entities.items():
            for etype, data in items:
                if etype == 'LINE':
                    x0, y0, x1, y1 = data
                    shifted[layer].append(('LINE', (x0 + shift_x, y0 + shift_y, x1 + shift_x, y1 + shift_y)))
                elif etype == 'CIRCLE':
                    cx, cy, r = data
                    shifted[layer].append(('CIRCLE', (cx + shift_x, cy + shift_y, r)))
                elif etype == 'ARC':
                    cx, cy, r, a1, a2 = data
                    shifted[layer].append(('ARC', (cx + shift_x, cy + shift_y, r, a1, a2)))
                elif etype in ['POLYLINE', 'SPLINE', 'ELLIPSE']:
                    pts = [(x + shift_x, y + shift_y) for x, y in data]
                    shifted[layer].append((etype, pts))
        return shifted


    # --- Store G-code dimensions ---
    def getGcodeSize(self, xmin, xmax, ymin, ymax):
        self.gcode_xmin = xmin
        self.gcode_xmax = xmax
        self.gcode_ymin = ymin
        self.gcode_ymax = ymax
        self.gcode_width = self.gcode_xmax - self.gcode_xmin
        self.gcode_height = self.gcode_ymax - self.gcode_ymin
        self.gcode_xcenter = self.gcode_width / 2
        self.gcode_ycenter = self.gcode_height / 2

    # --- Set bed corners ---
    def setBedCorners(self, p1, p2, p3, p4):
        self.bed_x0 = min(p1[0], p2[0], p3[0], p4[0])
        self.bed_y0 = min(p1[1], p2[1], p3[1], p4[1])
        bed_xmax = max(p1[0], p2[0], p3[0], p4[0])
        bed_ymax = max(p1[1], p2[1], p3[1], p4[1])
        self.bed_width = bed_xmax - self.bed_x0
        self.bed_height = bed_ymax - self.bed_y0

    # --- Translate into bed ---
    def translateToBed(self):
        # shift drawing so its lower-left corner aligns with bed corner
        self.tx = self.bed_x0 - self.gcode_xmin
        self.ty = self.bed_y0 - self.gcode_ymin

    # --- Validate if DXF fits in bed ---
    def validateFit(self, tx=0, ty=0):
        xmin = self.gcode_xmin + tx
        xmax = self.gcode_xmax + tx
        ymin = self.gcode_ymin + ty
        ymax = self.gcode_ymax + ty

        bed_xmin = self.bed_x0
        bed_xmax = self.bed_x0 + self.bed_width
        bed_ymin = self.bed_y0
        bed_ymax = self.bed_y0 + self.bed_height

        return xmin >= bed_xmin and xmax <= bed_xmax and ymin >= bed_ymin and ymax <= bed_ymax


    # --- Z height ---
    def setZvalue(self, value):
        self.zpos = value

    def getZvalue(self):
        if self.zpos is None or self.zpos == 0:
            self.zpos = float(self.zpos_safe)

    # --- Feedrate ---
    def setFeedRate(self, feedrate):
        self.feed = int(feedrate)

    # --- Generate G-code ---
    def generateGcode(self, xoffset=None, yoffset=None):
        entities = self.extractEntities()
        entities = self.shiftToFirstQuadrant(entities)
        
        xmin, xmax, ymin, ymax = self.computeBoundary(entities)
        self.getGcodeSize(xmin, xmax, ymin, ymax)

        self.tx = xoffset - self.gcode_xmin
        self.ty = yoffset - self.gcode_ymin

        if not self.validateFit(self.tx, self.ty):
            raise IndexError(f"DXF with offset (X={xoffset}, Y={yoffset}) does not fit in bed area.")

        self.getZvalue()
        travel_z = self.zpos + getattr(self, "travel_z_lift", 5.0)

        glist = ["G90", "M5"]

        for layer, item in entities.items():
            for etype, data in item:
                if etype == "LINE":
                    x0, y0 = data[0] + self.tx, data[1] + self.ty
                    x1, y1 = data[2] + self.tx, data[3] + self.ty

                    # --- travel to start ---
                    glist.append("M5")  # laser off
                    glist.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{travel_z:.3f} F{self.feed}")  # lift
                    glist.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{self.zpos:.3f} F{self.feed}")  # lower

                    # --- cutting move ---
                    glist.append("M3")  # laser on
                    glist.append(f"G1 X{x1:.3f} Y{y1:.3f} Z{self.zpos:.3f} F{self.feed}")

                elif etype == "CIRCLE":
                    cx, cy, r = data
                    x0, y0 = cx + r + self.tx, cy + r + self.ty
                    i = -r

                    glist.append("M5")
                    glist.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{travel_z:.3f} F{self.feed}")
                    glist.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{self.zpos:.3f} F{self.feed}")
                    glist.append("M3")
                    glist.append(f"G2 X{x0:.3f} Y{y0:.3f} I{i:.3f} J0.00 F{self.feed}")

                elif etype == "ARC":
                    cx, cy, r, a1, a2 = data
                    a1, a2 = -a1, -a2
                    x0 = cx + r * math.cos(math.radians(a1)) + self.tx
                    y0 = cy + r * math.sin(math.radians(a1)) + self.ty
                    x1 = cx + r * math.cos(math.radians(a2)) + self.tx
                    y1 = cy + r * math.sin(math.radians(a2)) + self.ty
                    i = (cx + self.tx) - x0
                    j = (cy + self.ty) - y0

                    glist.append("M5")
                    glist.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{travel_z:.3f} F{self.feed}")
                    glist.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{self.zpos:.3f} F{self.feed}")
                    glist.append("M3")
                    glist.append(f"G2 X{x1:.3f} Y{y1:.3f} I{i:.3f} J{j:.3f} F{self.feed}")

                elif etype in ['POLYLINE', 'SPLINE', 'ELLIPSE']:
                    points = [(x + self.tx, y + self.ty) for x, y in data]
                    if points:
                        x0, y0 = points[0]
                        glist.append("M5")
                        glist.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{travel_z:.3f} F{self.feed}")
                        glist.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{self.zpos:.3f} F{self.feed}")
                        glist.append("M3")
                        for x, y in points[1:]:
                            glist.append(f"G1 X{x:.3f} Y{y:.3f} Z{self.zpos:.3f} F{self.feed}")

        glist.extend(["M5", "G28 X Y"])
        return glist



# --- Example usage ---
if __name__ == "__main__":
    bed_corners = [(31, 28), (155, 28), (155, 110), (31, 110)]
    dxf_file = "C:/Users/exp/Desktop/FTO_P1_scribing_5x5cm.dxf"
    config_file = "config.ini"

    parser = DXFParser(dxf_file, config_file=config_file)
    parser.setBedCorners(*bed_corners)

    try:
        gcode = parser.generateGcode(xoffset=50, yoffset=20)  # apply user offsets
        print("\n".join(gcode))
    except IndexError as e:
        print(f"Error: {e}")
