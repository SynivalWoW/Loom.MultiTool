"""Ensure the repo root (where the retroport modules live) is importable under pytest."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
