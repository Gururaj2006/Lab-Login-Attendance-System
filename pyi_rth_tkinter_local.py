import os
import sys
from pathlib import Path


bundle_root = Path(getattr(sys, "_MEIPASS", ""))

if bundle_root:
    tcl_path = bundle_root / "tcl8.6"
    tk_path = bundle_root / "tk8.6"

    if tcl_path.is_dir():
        os.environ.setdefault("TCL_LIBRARY", str(tcl_path))

    if tk_path.is_dir():
        os.environ.setdefault("TK_LIBRARY", str(tk_path))
