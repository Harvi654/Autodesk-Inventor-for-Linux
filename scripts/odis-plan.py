#!/usr/bin/env python3
"""Print the install plan of an Autodesk ODIS image (see scripts/lib/odis.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))
import odis  # noqa: E402

odis.main()
