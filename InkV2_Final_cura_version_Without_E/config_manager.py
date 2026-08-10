import json
import os
from pathlib import Path
import sys


# -----------------------------
# Locate Application Directory
# -----------------------------
def get_app_dir():
    """
    Returns the directory where the EXE or Python script is located.
    Works correctly for PyInstaller builds.
    """
    if getattr(sys, 'frozen', False):      # Running as EXE
        return Path(sys.executable).parent
    return Path(__file__).parent           # Running as .py script


APP_DIR = get_app_dir()
PROFILE_PATH = APP_DIR / "profile.json"


# -----------------------------
# Default Profile
# -----------------------------
DEFAULT_PROFILE = {
    "profile_version": 1,

    # Walls
    "wall_line_count": 1,
    "wall_thickness": 0.4,
    "inset_direction": "outside_in",

    # Top/Bottom
    "top_layers": 0,
    "bottom_layers": 0,
    "top_bottom_thickness": 0,

    # Infill
    "infill_sparse_density": 100,
    "infill_pattern": "lines",
    "infill_angles": [90],
    "connect_infill_polygons": True,

    # Layer height
    "layer_height": 0.4,
    "layer_height_0": 0.4,

    # Speeds
    "speed_infill": 10,
    "speed_print": 10,
    "speed_travel": 10,
    "speed_wall": 10,
    "speed_wall_0": 10,
    "speed_wall_x": 10,
    "speed_layer_0": 10,

    # Temperature
    "material_print_temperature": 25,
    "material_bed_temperature": 25,

    # Retraction OFF (ink printing)
    "retraction_enable": False,
    "retraction_amount": 0,
    "retraction_speed": 0,

    # Adhesion
    "adhesion_type": "none",

    # Smooth walls
    "optimize_wall_printing_order": True,

    # Z seam
    "z_seam_corner": "z_seam_corner_weighted"
}


# -----------------------------
# Create profile.json if missing
# -----------------------------
def ensure_profile_exists():
    if not PROFILE_PATH.exists():
        print(f"[Config] Creating default profile.json at: {PROFILE_PATH}")
        with PROFILE_PATH.open("w") as f:
            json.dump(DEFAULT_PROFILE, f, indent=4)
    else:
        print("[Config] profile.json already exists.")
    return PROFILE_PATH


# -----------------------------
# Load profile.json
# -----------------------------
def load_profile():
    ensure_profile_exists()
    with PROFILE_PATH.open("r") as f:
        return json.load(f)


# -----------------------------
# Save profile.json
# -----------------------------
def save_profile(data: dict):
    with PROFILE_PATH.open("w") as f:
        json.dump(data, f, indent=4)
    print("[Config] Saved profile.json")


# -----------------------------
# Reset to default profile
# -----------------------------
def reset_profile():
    save_profile(DEFAULT_PROFILE)
    print("[Config] Reset profile.json to default settings.")
