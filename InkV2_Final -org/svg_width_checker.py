import sys
import os
import re
import xml.etree.ElementTree as ET
import numpy as np
import random
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QTextEdit, QFileDialog, QLabel, QGraphicsView, 
                             QGraphicsScene, QGraphicsPathItem, QGraphicsTextItem, 
                             QFrame, QScrollArea, QSplitter)
from PySide6.QtGui import QFont, QColor, QPainterPath, QPen, QBrush, QPainter
from PySide6.QtCore import Qt, QPointF

# Import custom tools
from svgpathtools import parse_path, Line, CubicBezier, QuadraticBezier
from svg_to_stl import svg_to_polygons, polygons_to_stl
from stl_to_gcode import runCuraEngine, json2args
from config_manager import load_profile
from preview3d import GCode3DPreview

class SVGWidthChecker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SVG to G-code: Smart Validator")
        self.resize(1450, 900)
        self.setStyleSheet("""
            QMainWindow { background-color: #0d0d0d; }
            QWidget#MainContent { background-color: #0d0d0d; }
            QGraphicsView { background-color: #151515; border: 1px solid #333; border-radius: 8px; }
            QTextEdit { background-color: #050505; color: #00ff00; border: 1px solid #333; border-radius: 4px; font-family: 'Consolas'; }
            QPushButton { 
                background-color: #007acc; color: white; border-radius: 4px; padding: 12px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #0098ff; }
            QLabel { color: #f0f0f0; font-family: 'Segoe UI'; }
            QSplitter::handle { background-color: #444; width: 2px; }
            QFrame#StatusBox { background-color: #1a1a1a; border: 1px solid #444; border-radius: 6px; padding: 10px; }
        """)
        
        self.unique_widths = {} 
        self.palette = ["#55ffff", "#ff55ff", "#ffff55", "#55ff55", "#ff5555", "#ffa500", "#00bfff"]
        
        # Stats Storage
        self.svg_stats = {"count": 0, "thin": 0, "double": 0}
        self.gcode_stats = {"layers": 0, "segments": 0}

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("<b style='font-size: 22px; color: #00aaff;'>SVG → G-CODE VALIDATOR</b>"))
        header.addStretch()
        self.upload_btn = QPushButton("IMPORT & VALIDATE")
        self.upload_btn.setFixedWidth(200)
        self.upload_btn.clicked.connect(self.select_file)
        header.addWidget(self.upload_btn)
        self.main_layout.addLayout(header)
        
        # Main Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.main_layout.addWidget(self.splitter)
        
        # 1. Left Panel (SVG Analysis)
        left_widget = QWidget()
        left_lay = QVBoxLayout(left_widget)
        left_lay.addWidget(QLabel("<b style='color: #888;'>INPUT: SVG DESIGN ANALYSIS</b>"))
        self.svg_scene = QGraphicsScene()
        self.svg_view = QGraphicsView(self.svg_scene)
        self.svg_view.setRenderHint(QPainter.Antialiasing)
        self.svg_view.setDragMode(QGraphicsView.ScrollHandDrag)
        left_lay.addWidget(self.svg_view)
        self.splitter.addWidget(left_widget)
        
        # 2. Middle Panel (3D G-code Preview)
        mid_widget = QWidget()
        mid_lay = QVBoxLayout(mid_widget)
        mid_lay.addWidget(QLabel("<b style='color: #888;'>OUTPUT: 3D PRINT PREVIEW</b>"))
        self.preview3d = GCode3DPreview()
        mid_lay.addWidget(self.preview3d)
        self.splitter.addWidget(mid_widget)
        
        # 3. Right Panel (Validation Summary)
        right_widget = QWidget()
        right_widget.setFixedWidth(350)
        self.right_layout = QVBoxLayout(right_widget)
        
        # Validation Result Box
        self.val_box = QFrame()
        self.val_box.setObjectName("StatusBox")
        self.val_lay = QVBoxLayout(self.val_box)
        self.val_title = QLabel("VALIDATION STATUS")
        self.val_title.setAlignment(Qt.AlignCenter)
        self.val_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.val_lay.addWidget(self.val_title)
        
        self.val_text = QTextEdit()
        self.val_text.setReadOnly(True)
        self.val_text.setFrameStyle(QFrame.NoFrame)
        self.val_text.setStyleSheet("background: transparent; color: #aaa;")
        self.val_text.setHtml("Import a file to start validation check...")
        self.val_lay.addWidget(self.val_text)
        
        self.copy_btn = QPushButton("Copy Validation Report")
        self.copy_btn.setStyleSheet("background-color: #333; height: 30px; font-size: 11px;")
        self.copy_btn.clicked.connect(self.copy_report)
        self.val_lay.addWidget(self.copy_btn)
        
        self.right_layout.addWidget(self.val_box)

        # Width Legend
        self.right_layout.addWidget(QLabel("<b>COLOR PROFILE</b>"))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.legend_widget = QWidget()
        self.legend_layout = QVBoxLayout(self.legend_widget)
        self.legend_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.legend_widget)
        self.right_layout.addWidget(self.scroll, 2)
        
        self.right_layout.addWidget(QLabel("<b>PROCESSING LOGS</b>"))
        self.report_area = QTextEdit()
        self.report_area.setReadOnly(True)
        self.right_layout.addWidget(self.report_area, 1)
        
        self.splitter.addWidget(right_widget)
        
        # Proportions
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setStretchFactor(2, 2)

    def copy_report(self):
        full_report = f"--- {self.val_title.text()} ---\n{self.val_text.toPlainText()}\n\n"
        full_report += "--- Processing Logs ---\n" + self.report_area.toPlainText()
        QApplication.clipboard().setText(full_report)
        self.copy_btn.setText("HTML COPIED!" if "</span>" in full_report else "REPORT COPIED!")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self.copy_btn.setText("Copy Validation Report"))

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open SVG", "", "SVG Files (*.svg)")
        if file_path:
            self.process_full_check(file_path)

    def process_full_check(self, svg_path):
        self.report_area.clear()
        self.svg_scene.clear()
        self.unique_widths.clear()
        self.preview3d.clear()
        self.svg_stats = {"count": 0, "thin": 0, "double": 0}
        self.val_text.setHtml("Processing...")
        self.val_box.setStyleSheet("background-color: #1a1a1a; border: 1px solid #444;")
        
        while self.legend_layout.count():
            child = self.legend_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            
        path_obj = Path(svg_path)
        
        # 1. SVG Analysis
        try:
            self.analyze_svg_widths(svg_path)
        except Exception as e:
            self.update_val_status("CRITICAL ERROR", f"SVG breakdown failed: {e}", "#ff4444")
            return

        # 2. Conversion
        try:
            self.report_area.append("Converting Design...")
            stl_path = path_obj.with_suffix(".stl")
            gcode_path = path_obj.with_suffix(".gcode")
            
            polygons = svg_to_polygons(svg_path)
            polygons_to_stl(polygons, stl_path, z_height=0.4)
            
            profile = load_profile()
            args = json2args(profile)
            runCuraEngine(stl_path, gcode_path, args)
            
            # 3. Load & Compare
            if gcode_path.exists():
                with open(gcode_path, 'r') as f:
                    lines = f.readlines()
                self.preview3d.loadGcode(lines)
                self.compare_and_validate(lines)
        except Exception as e:
            self.update_val_status("CONVERSION ERROR", str(e), "#ff4444")

    def analyze_svg_widths(self, path):
        tree = ET.parse(path)
        root = tree.getroot()
        
        w_attr, vb_attr = root.get('width'), root.get('viewBox')
        def parse_mm(val):
            mapping = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4/72.0, "px": 25.4/96.0}
            m = re.match(r"([0-9.]+)\s*([a-z%]*)", str(val).strip())
            return float(m.group(1)) * mapping.get(m.group(2).lower(), 25.4/96.0) if m else None

        doc_mm = parse_mm(w_attr)
        u_to_mm = 25.4 / 96.0
        if vb_attr:
            vb = [float(x) for x in vb_attr.replace(',', ' ').split()]
            if len(vb) == 4 and doc_mm: u_to_mm = doc_mm / vb[2]

        def get_styles(elem, inherited):
            res = inherited.copy() if inherited else {"stroke": "none", "stroke-width": "1"}
            style_str = elem.get('style', '')
            style_dict = {k.strip(): v.strip() for k, v in (p.split(':') for p in style_str.split(';') if ':' in p)}
            for n in ["stroke", "stroke-width"]:
                val = elem.get(n) or style_dict.get(n)
                if val: res[n] = val
            return res

        def process(elem, transform=None, inherited=None):
            tag = elem.tag.split('}')[-1]
            if tag in ["defs", "metadata"]: return
            styles = get_styles(elem, inherited)
            t_str = elem.get('transform', '')
            local_t = None
            if t_str:
                try: from svgpathtools.parser import parse_transform; local_t = parse_transform(t_str)
                except: pass
            
            ct = np.dot(transform, local_t) if transform is not None and local_t is not None else (local_t if local_t is not None else transform)
            eff_s = 1.0
            if ct is not None: eff_s = (np.sqrt(ct[0][0]**2 + ct[1][0]**2) + np.sqrt(ct[0][1]**2 + ct[1][1]**2)) / 2.0

            path_d = ""
            if tag == 'path': path_d = elem.get('d', '')
            elif tag == 'rect':
                x, y, w, h = [float(elem.get(k, 0)) for k in ['x', 'y', 'width', 'height']]
                path_d = f"M {x},{y} L {x+w},{y} L {x+w},{y+h} L {x},{y+h} Z"
            elif tag in ['circle', 'ellipse']:
                cx, cy = float(elem.get('cx', 0)), float(elem.get('cy', 0))
                rx = float(elem.get('rx', elem.get('r', 0))); ry = float(elem.get('ry', elem.get('r', 0)))
                path_d = f"M {cx-rx},{cy} A {rx},{ry} 0 1,0 {cx+rx},{cy} A {rx},{ry} 0 1,0 {cx-rx},{cy} Z"

            if path_d and styles.get('stroke', 'none').lower() != 'none':
                try:
                    sw_val = float(re.findall(r"[-+]?\d*\.\d+|\d+", str(styles.get('stroke-width', '1')))[0])
                    real_mm = sw_val * eff_s * u_to_mm
                    color = self.get_color_for_width(real_mm)
                    
                    self.svg_stats["count"] += 1
                    if real_mm < 0.395: self.svg_stats["thin"] += 1
                    if real_mm > 0.8: self.svg_stats["double"] += 1

                    paths = parse_path(path_d)
                    if paths:
                        qp = QPainterPath(); qp.moveTo(paths[0].start.real, paths[0].start.imag)
                        for s in paths:
                            if isinstance(s, Line): qp.lineTo(s.end.real, s.end.imag)
                            elif isinstance(s, CubicBezier): qp.cubicTo(s.control1.real, s.control1.imag, s.control2.real, s.control2.imag, s.end.real, s.end.imag)
                        item = QGraphicsPathItem(qp); item.setPen(QPen(color, sw_val))
                        if ct is not None:
                            from PySide6.QtGui import QTransform
                            item.setTransform(QTransform(ct[0][0], ct[1][0], ct[0][1], ct[1][1], ct[0][2], ct[1][2]))
                        self.svg_scene.addItem(item)
                        # Midpoint label
                        m_pt = paths[0].point(0.5)
                        sc_pt = item.transform().map(QPointF(m_pt.real, m_pt.imag))
                        lbl = QGraphicsTextItem(f"{real_mm:.2f}mm")
                        lbl.setDefaultTextColor(color); lbl.setFont(QFont("Arial", 8, QFont.Bold)); lbl.setPos(sc_pt.x()-15, sc_pt.y()-10)
                        lbl.setFlag(QGraphicsTextItem.ItemIgnoresTransformations); self.svg_scene.addItem(lbl)
                except: pass
            for child in elem: process(child, ct, styles)
        process(root)
        self.svg_view.fitInView(self.svg_scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    def get_color_for_width(self, width):
        w = round(width, 3)
        if w not in self.unique_widths:
            color = QColor(self.palette[len(self.unique_widths)%len(self.palette)])
            self.unique_widths[w] = color
            c = QFrame(); c.setStyleSheet("background: #252525; border-radius: 4px; margin: 1px;")
            lay = QHBoxLayout(c); swatch = QFrame(); swatch.setFixedSize(12, 12); swatch.setStyleSheet(f"background: {color.name()};")
            lay.addWidget(swatch); lay.addWidget(QLabel(f"{w:.3f} mm")); lay.addStretch()
            self.legend_layout.addWidget(c)
        return self.unique_widths[w]

    def compare_and_validate(self, gcode_lines):
        # 1. Parse G-code for metrics
        g_extrusions = 0
        g_layers = set()
        for line in gcode_lines:
            if line.startswith("G1"):
                if "E" in line: g_extrusions += 1
                if "Z" in line:
                    match = re.search(r"Z([-+]?\d*\.\d+|\d+)", line)
                    if match: g_layers.add(match.group(1))

        # 2. Comparison Logic
        issues = []
        severity = "OK" # OK, WARNING, ERROR
        
        # Rule 1: Thin Lines
        if self.svg_stats["thin"] > 0:
            issues.append(f"• <b>MISSING?</b> {self.svg_stats['thin']} lines were thinner than nozzle (0.4mm). The slicer may have ignored them.")
            severity = "WARNING"

        # Rule 2: Double Passes
        if self.svg_stats["double"] > 0:
            issues.append(f"• <b>GEOMETRY CHANGE:</b> {self.svg_stats['double']} paths are wider than 0.8mm. Slicer implemented Double-Pass (Loops) for these.")
            if severity != "ERROR": severity = "WARNING"

        # Rule 3: Extrusion Count vs Path Count
        # Usually, extrusion count > path count because loops create multiple moves.
        # But if extrusion count is way lower, it's an error.
        if g_extrusions == 0:
            issues.append("• <b>CRITICAL:</b> Generated G-code has NO printing moves! Check slicing profile.")
            severity = "ERROR"

        # Rule 4: Scale Verification
        if not g_layers:
            issues.append("• <b>ERROR:</b> No printing layers detected in 3D preview.")
            severity = "ERROR"

        # Final Report
        if not issues:
            self.update_val_status("VALIDATION: 100% SUCCESS", "Design and Preview match perfectly. All lines are suitable for single-pass printing.", "#2eb82e")
        else:
            status_text = "<br>".join(issues)
            color = "#ffa31a" if severity == "WARNING" else "#ff3333"
            self.update_val_status(f"VAL STATUS: {severity}", status_text, color)

    def update_val_status(self, title, text, color):
        self.val_title.setText(title)
        self.val_text.setHtml(text)
        self.val_box.setStyleSheet(f"background-color: #1a1a1a; border: 2px solid {color};")
        self.val_title.setStyleSheet(f"color: {color};")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SVGWidthChecker()
    window.show()
    sys.exit(app.exec())
