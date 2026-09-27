import sys
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

PROJECT_ROOT = PYTHON_ROOT.parent.parent
if sys.platform == "win32":
    platform_py = PROJECT_ROOT / "windows" / "python"
else:
    platform_py = PROJECT_ROOT / "linux" / "python"

if platform_py.exists() and str(platform_py) not in sys.path:
    sys.path.insert(0, str(platform_py))

