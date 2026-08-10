import os
import shutil
import sys
import ctypes
from datetime import datetime
import re
import tempfile
from pathlib import Path

from util import fileWrite, writeLog

# -------------------------------------------------
# FILES
# -------------------------------------------------
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cura_log.txt")
STATUS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status.txt")

# Names of our Cura custom files
CUSTOM_FILES = [
    "specialize_india_500.def.json",
    "specialize_india_500_extruder_0.def.json"
]

# -------------------------------------------------
# RESOLVE LOCAL FOLDER (Fix 2 for EXE)
# -------------------------------------------------
def get_local_folder():
    """
    Returns the folder containing our Cura JSON definition files.
    In EXE mode: extract them from the PyInstaller bundle.
    In Python mode: use script directory.
    """
    # Running as imported EXE
    if getattr(sys, 'frozen', False):
        temp_dir = Path(tempfile.gettempdir()) / "cura_custom_defs"
        temp_dir.mkdir(exist_ok=True)

        bundle_dir = Path(sys._MEIPASS)

        for fname in CUSTOM_FILES:
            src = bundle_dir / fname
            dst = temp_dir / fname
            if src.exists():
                shutil.copy(src, dst)

        return str(temp_dir)

    # Running as normal Python script
    return os.path.dirname(os.path.abspath(__file__))

# -------------------------------------------------
# ADMIN CHECK
# -------------------------------------------------
def runAsAdmin():
    """Relaunch the script as Administrator if not already elevated."""
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False

    if not is_admin:
        writeLog(LOG_FILE, "[INFO] Requesting Administrator privileges...")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)

# -------------------------------------------------
# FIND CURA
# -------------------------------------------------
def findCuraVersions():
    """Finds all Cura installations in Program Files."""
    base_paths = [r"C:\Program Files", r"C:\Program Files (x86)"]
    versions = []

    for base_path in base_paths:
        if os.path.exists(base_path):
            for folder in os.listdir(base_path):
                if "cura" in folder.lower():
                    cura_path = os.path.join(base_path, folder)
                    if os.path.exists(os.path.join(cura_path, "UltiMaker-Cura.exe")):
                        versions.append(cura_path)

    if versions:
        writeLog(LOG_FILE, "[OK] Found Cura installations:")
        for v in versions:
            writeLog(LOG_FILE, f"     - {v}")
    else:
        writeLog(LOG_FILE, "[ERROR] No Cura installations found.")

    return versions

# -------------------------------------------------
# EXTRACT VERSION
# -------------------------------------------------
def getCuraVersions():
    cura_paths = findCuraVersions()
    versions = []

    for path in cura_paths:
        folder = os.path.basename(path)

        match = re.search(r'(\d+\.\d+\.\d+|\d+\.\d+)', folder)
        if match:
            versions.append(match.group(1))

    return versions

# -------------------------------------------------
# VERSION CHECK
# -------------------------------------------------
def isCuraSupported():
    required_version = (5, 9, 1)

    versions = getCuraVersions()

    supported = []
    unsupported = []

    for v in versions:
        parts = tuple(int(p) for p in v.split("."))

        if parts == required_version:
            supported.append(v)
        else:
            unsupported.append(v)

    selected = supported[0] if supported else None

    return selected, unsupported

# -------------------------------------------------
# FILE COPY CHECK
# -------------------------------------------------
def ensureFilesExist(cura_path, local_folder):
    """Ensures your custom files exist inside Cura installation."""
    write = False
    exist = False

    files_to_check = {
        "Extruder": (
            os.path.join(cura_path, r"share\cura\resources\extruders\specialize_india_500_extruder_0.def.json"),
            os.path.join(local_folder, "specialize_india_500_extruder_0.def.json")
        ),
        "Definition": (
            os.path.join(cura_path, r"share\cura\resources\definitions\specialize_india_500.def.json"),
            os.path.join(local_folder, "specialize_india_500.def.json")
        )
    }

    for name, (target, source) in files_to_check.items():
        if not os.path.exists(target):
            if os.path.exists(source):
                try:
                    shutil.copy(source, target)
                    writeLog(LOG_FILE, f"[ADDED] {name} file copied to: {target}")
                    write = True
                except PermissionError:
                    writeLog(LOG_FILE, f"[ERROR] Permission denied while copying {name} file.")
            else:
                writeLog(LOG_FILE, f"[MISSING] Local {name} file missing: {source}")
        else:
            exist = True
            writeLog(LOG_FILE, f"[OK] {name} file already exists: {os.path.basename(cura_path)}")

    return write, exist

# -------------------------------------------------
# ADMIN COPY RUNNER
# -------------------------------------------------
def copyDefFiles():
    msg = " "
    status = []

    runAsAdmin()

    # FIX HERE: use extracted folder if EXE
    local_folder = get_local_folder()
    cura_versions = findCuraVersions()

    if not cura_versions:
        writeLog(LOG_FILE, "No Cura versions found.")
        sys.exit(0)

    all_done = False

    for cura_path in cura_versions:
        writeLog(LOG_FILE, f"\n--- Checking {os.path.basename(cura_path)} ---")
        copied, exists = ensureFilesExist(cura_path, local_folder)
        all_done = copied or exists
        status.append(all_done)

    if all_done:
        msg = "\nAll Cura installations verified successfully."
    else:
        msg = "\nSome Cura installations failed verification."

    writeLog(LOG_FILE, msg)
    writeLog(LOG_FILE, "=== Script Finished ===\n")
    status.append(msg)

    fileWrite(STATUS_FILE, str(status), mode="w")

# -------------------------------------------------
# CHECK ONLY (NO ADMIN)
# -------------------------------------------------
def checkCuraStatus():
    """Check only, no admin, no copy."""
    local_folder = get_local_folder()
    cura_versions = findCuraVersions()
    missing = []

    files_to_check = [
        r"share\cura\resources\extruders\specialize_india_500_extruder_0.def.json",
        r"share\cura\resources\definitions\specialize_india_500.def.json"
    ]

    for cura_path in cura_versions:
        for rel in files_to_check:
            full = os.path.join(cura_path, rel)
            if not os.path.exists(full):
                missing.append(full)

    return missing

# -------------------------------------------------
# EXECUTION
# -------------------------------------------------
if __name__ == "__main__":
    copyDefFiles()
