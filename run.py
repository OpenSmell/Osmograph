#!/usr/bin/env python3
import sys, os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "opensmell"))

from Osmograph.app import main
main()
