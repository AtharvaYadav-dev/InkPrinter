import re

class GcodeParser:

    # --------------------------------------------
    # Constructor
    # --------------------------------------------
    def __init__(self):
        self.motion_cmds = ('G0', 'G1', 'G2', 'G3')
        self.supported_mcodes = ('M3', 'M4', 'M5', 'M106', 'M107',
                                 'M114', 'M400', 'M302')

        # Precompiled regex
        self.axis_pat = re.compile(r'([XYZEF])([-+]?\d*\.?\d+)', re.IGNORECASE)
        self.xy_pat   = re.compile(r'([XY])([-+]?\d*\.?\d+)', re.IGNORECASE)
        self.xyzef_pat = re.compile(r'[XYZEFT][-+]?\d*\.?\d+')

    # -----------------------------------------------------------------------
    def is_executable(self, line: str) -> bool:
        line = line.strip()
        if not line or line.startswith(';') or line.startswith('('):
            return False

        parts = line.split()
        if not parts:
            return False

        cmd = parts[0].upper()
        return cmd.startswith(self.motion_cmds) or cmd in self.supported_mcodes

    def parse_file(self, filepath: str) -> list[str]:
        with open(filepath, 'r') as f:
            return [line.rstrip() for line in f.readlines()]

    # -----------------------------------------------------------------------
    def is_wipe_line(self, line: str) -> bool:
        up = line.upper().strip()
        comment = up.split(";", 1)[1].strip() if ";" in up else ""
        return ("WIPE OUT" in comment) or comment.startswith("WIPE")

    # -----------------------------------------------------------------------
    def extract_coords(self, line: str) -> dict:
        return {m.group(1).upper(): float(m.group(2))
                for m in self.axis_pat.finditer(line)}

    # -----------------------------------------------------------------------
    def extract_anchor(self, glines: list[str]):
        """
        Find the first G1 that contains X or Y in the provided lines.
        Returns (firstX, firstY, index) where index is the line index in glines.
        """
        abs_mode = True
        firstX = firstY = None

        for idx, ln in enumerate(glines):
            up = ln.strip().upper()

            if up.startswith("G90"):
                abs_mode = True
                continue
            elif up.startswith("G91"):
                abs_mode = False
                continue

            # only consider absolute-mode motions for anchor detection
            if not abs_mode:
                continue
            if not up.startswith("G1"):
                continue

            coords = self.extract_coords(ln)
            if not coords:
                continue

            if "X" in coords and firstX is None:
                firstX = coords["X"]
            if "Y" in coords and firstY is None:
                firstY = coords["Y"]

            if firstX is not None or firstY is not None:
                return firstX, firstY, idx

        return None, None, None

    # -----------------------------------------------------------------------
    # TRANSFORM MOTION LINES (No sample height)
    # -----------------------------------------------------------------------
    def transform_motion(self, raw: str,
                         shiftX: float, shiftY: float,
                         draw_z: float,
                         feedrate: float,
                         abs_mode: bool,
                         draw_z_user: bool,
                         layer_height: float | None = None):

        up = raw.strip().upper()

        if not up.startswith(("G0", "G1", "G2", "G3")):
            return raw

        def repl(m):
            axis = m.group(1).upper()
            try:
                num = float(m.group(2))
            except:
                return m.group(0)

            # XY shift in absolute mode
            if abs_mode:
                if axis == "X":
                    return f"X{num + shiftX:.3f}"
                if axis == "Y":
                    return f"Y{num + shiftY:.3f}"

            # Z override logic (draw_z only)
            if axis == "Z" and draw_z_user:
                return f"Z{draw_z:.3f}"

            # Feed override
            if axis == "F" and feedrate:
                return f"F{feedrate:.3f}"

            return m.group(0)

        return self.axis_pat.sub(repl, raw)

    # -----------------------------------------------------------------------
    def preprocess_lines(self, glines: list[str]) -> tuple[list[str], float | None]:
        """
        Remove all full-line comments.
        Remove inline comments (keep command).
        Extract layer height if present.
        """
        adjusted = []
        abs_mode = True
        layer_height = None

        for ln in glines:
            raw = ln.strip()

            # ---------- FULL LINE COMMENT ----------
            if raw.startswith(";"):
                # Extract layer height if present
                if raw.upper().startswith(";LAYER HEIGHT:"):
                    try:
                        layer_height = float(raw.split(":")[1].strip())
                    except:
                        layer_height = None
                
                # Keep structure type comments for preview
                if raw.upper().startswith(";TYPE:"):
                    adjusted.append(raw)
                    continue

                # Do NOT keep other comments
                continue

            # ---------- REMOVE INLINE COMMENTS ----------
            # M82 ;absolute extrusion mode  → M82
            if ";" in raw:
                raw = raw.split(";", 1)[0].strip()

            # remove comments in ( ... ) format
            if "(" in raw:
                raw = raw.split("(", 1)[0].strip()

            # skip now-empty lines
            if not raw:
                continue

            up = raw.upper()

            # drop long temp/wait lines
            if re.match(r'^(M104|M109|M140|M190|M105|M141|M191)\b', up):
                continue

            # track absolute/relative mode
            if up.startswith("G90"):
                abs_mode = True
            elif up.startswith("G91"):
                abs_mode = False

            # skip wipe lines
            if self.is_wipe_line(raw):
                continue

            adjusted.append(raw)

        return adjusted, layer_height

    # -----------------------------------------------------------------------
    # APPLY FULL TRANSFORM PASS (SLICER-LIKE Z-HOP BEHAVIOR)
    # -----------------------------------------------------------------------
    def apply_full_transform(self, glines_clean: list[str],
                         shiftX: float, shiftY: float,
                         draw_z: float,
                         feedrate: float,
                         draw_z_user: bool,
                         layer_height: float | None = None,
                         uv_time_ms: int = 0) -> list[str]:

        final = []
        abs_mode = True

        # PRINT Z calculation
        if draw_z_user:
            printZ = draw_z
        else:
            printZ = layer_height if layer_height is not None else 0.0

        hopDelta = -2.0        # Z-hop amount (+2 / -2)
        # travelF = (feedrate * 2) if feedrate else 1800.0
        travelF = 1800.0
        printF = feedrate if feedrate else 1000.0

        # Detect first print move (anchor)
        anchorX, anchorY, anchor_idx = self.extract_anchor(glines_clean)

        # Motion labels
        motions = []
        for ln in glines_clean:
            up = ln.upper().strip()
            if up.startswith("G0"): motions.append("G0")
            elif up.startswith("G1"): motions.append("G1")
            else: motions.append(None)

        at_hop = False
        first_g28_seen = False

        # Helpers
        def remove_Z(line):
            return re.sub(r"Z[-+]?\d*\.?\d+", "", line, flags=re.IGNORECASE).strip()

        def set_feed(line, f):
            if "F" in line.upper():
                return re.sub(r"F[-+]?\d*\.?\d+", f"F{f:.3f}", line, flags=re.IGNORECASE)
            return f"{line} F{f:.3f}"

        for i, ln in enumerate(glines_clean):
            raw = ln.rstrip()
            up = raw.upper().strip()
            motion = motions[i]

            # Mode commands
            if up.startswith("G90"):
                abs_mode = True
                final.append(raw)
                continue
            if up.startswith("G91"):
                abs_mode = False
                final.append(raw)
                continue

            # FIRST G28 → absolute hop to safe height
            if up.startswith("G28") and not first_g28_seen:

                # draw_z_UP before G28 (half of printZ)
                final.append(f"G0 Z{printZ / 2.0:.3f}")

                final.append("G28")

                # safe Z hop after homing
                final.append(f"G0 Z{printZ + hopDelta:.3f}")

                # INSERT M302 S0 HERE
                final.append("M302 S0")

                # ensure absolute mode for future operations
                final.append("G90")

                at_hop = True
                first_g28_seen = True
                continue


            # Non-motion
            if motion not in ("G0", "G1"):
                final.append(raw)
                continue

            # Apply XY shift, but DO NOT touch Z here
            newline = self.transform_motion(raw, shiftX, shiftY, draw_z, feedrate, abs_mode, False, layer_height)
            newline = self._strip_negative_E(newline)  # remove E-..

            # BEFORE ANCHOR → ALWAYS stay at HOP
            if anchor_idx is None or i < anchor_idx:
                if not at_hop:
                    # Prevent redundant G0 Z line if current line is already G0 Z
                    if not (up.startswith("G0") and "Z" in up and "X" not in up and "Y" not in up):
                        final.append(f"G0 Z{printZ + hopDelta:.3f} F{travelF}")
                        at_hop = True
                    else:
                        at_hop = True # Mark as at_hop but dont print double

                newline = remove_Z(newline)
                newline = set_feed(newline, travelF)
                final.append(newline)
                continue

            # AT ANCHOR → DROP BEFORE PRINT
            if i == anchor_idx:
                if at_hop:
                    final.append(f"G0 Z{printZ:.3f} F{travelF}")
                    at_hop = False


                newline = remove_Z(newline)       # NO Z in print moves
                newline = set_feed(newline, printF)
                final.append(newline)
                continue

            # AFTER ANCHOR
            prev_motion = motions[i-1] if i > 0 else None

            # PRINT MOVES
            if motion == "G1":
                if at_hop:
                    final.append(f"G0 Z{printZ:.3f} F{travelF}")
                    at_hop = False

                newline = remove_Z(newline)
                newline = set_feed(newline, printF)
                final.append(newline)
                continue

            # TRAVEL MOVES (G0)
            if motion == "G0":
                if not at_hop:
                    final.append(f"G0 Z{printZ + hopDelta:.3f} F{travelF}")
                    at_hop = True

                newline = remove_Z(newline)
                newline = set_feed(newline, travelF)
                final.append(newline)
                continue

        # Add layer comment
        final.insert(0, f";Layer height: {(layer_height or 0.0):.3f}")

        # Add hop before FINAL G28
        for i in range(len(final)-1, -1, -1):
            if final[i].upper().startswith("G28"):
                if uv_time_ms > 0:
                    final.insert(i, "M118 A1 P2 UO")
                    final.insert(i, f"G4 P{uv_time_ms}")
                    final.insert(i, "M118 A1 P2 UR")
                final.insert(i, f"G0 Z{printZ + hopDelta:.3f} F{travelF}")
                break

        # --------------------------------------
        # ADD BOUNDS COMMENTS
        # --------------------------------------
        bounds = self.get_bounds(final)
        bound_comments = self.bounds_to_comments(bounds)

        # Insert after layer height
        if final and final[0].startswith(";Layer height"):
            final = [final[0]] + bound_comments + final[1:]
        else:
            final = bound_comments + final

        return final


    # -----------------------------------------------------------------------
    def get_bounds(self, lines_or_path) -> dict:
        xmin = ymin = zmin = float('inf')
        xmax = ymax = zmax = float('-inf')
        first_g0_included = False

        if isinstance(lines_or_path, (str, bytes)):
            try:
                with open(lines_or_path, 'r') as f:
                    lines = f.readlines()
            except:
                return {}
        else:
            lines = lines_or_path

        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue

            up = ln.upper()
            cmd = up.split()[0] if up else ""

            if cmd not in ("G0", "G1"):
                continue

            if cmd == "G0" and not first_g0_included:
                coords = {tok[0]: float(tok[1:]) for tok in self.xyzef_pat.findall(ln)}
                if coords:
                    first_g0_included = True
                else:
                    continue

            elif cmd == "G1":
                coords = {tok[0]: float(tok[1:]) for tok in self.xyzef_pat.findall(ln)}
            else:
                continue

            if "X" in coords:
                xmin = min(xmin, coords["X"])
                xmax = max(xmax, coords["X"])
            if "Y" in coords:
                ymin = min(ymin, coords["Y"])
                ymax = max(ymax, coords["Y"])
            if "Z" in coords:
                zmin = min(zmin, coords["Z"])
                zmax = max(zmax, coords["Z"])

        if xmin == float('inf'):
            return {}

        return {
            'MINX': round(xmin, 3),
            'MAXX': round(xmax, 3),
            'MINY': round(ymin, 3),
            'MAXY': round(ymax, 3),
            'MINZ': round(zmin, 3),
            'MAXZ': round(zmax, 3),
        }

    # -----------------------------------------------------------------------
    def clean_line(self, line: str) -> str | None:
        if not line:
            return None

        raw = line.strip()

        # Remove full-line comments
        if raw.startswith(";") or raw.startswith("("):
            return None

        # Remove inline comments after commands
        # Example: "M82 ;absolute extrusion mode"  -> "M82"
        if ";" in raw:
            raw = raw.split(";", 1)[0].strip()

        if "(" in raw:
            raw = raw.split("(", 1)[0].strip()

        return raw if raw else None


    # -----------------------------------------------------------------------
    def get_base_code(self, line: str) -> str | None:
        if not line:
            return None
        return line.strip().split()[0].upper()


    def _strip_negative_E(self, line: str) -> str:
        """
        Remove negative extrusion fields like E-2 or E-0.123 while keeping rest of line untouched.
        """
        if not line:
            return line

        # Remove: space + E + negative number
        line = re.sub(r"\s*E-\d*\.?\d+", "", line, flags=re.IGNORECASE)

        return line.strip()
    

    def bounds_to_comments(self, bounds: dict) -> list[str]:
        """
        Convert bounds dict {MINX, MAXX, ...} into comment lines.
        """
        if not bounds:
            return []

        out = []
        for key, val in bounds.items():
            out.append(f";{key}: {val:.3f}")
        return out

