"""PyInstaller entrypoint. Also works from the unpacked source tree."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from docflow.gui import main

raise SystemExit(main())

