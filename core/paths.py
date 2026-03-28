import os
import sys

# Base directory adjustment for PyInstaller bundles
# This ensures that external files like .env, config.json, and pos_data.db
# are looked for in the same directory as the executable.
if getattr(sys, 'frozen', False):
    # Running in a bundle (e.g., PyInstaller .exe)
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running in normal Python environment
    # core/paths.py is at project_root/core/paths.py, so we go up two levels
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure logs directory exists at project root
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
