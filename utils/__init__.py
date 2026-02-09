
"""Compatibility shim so `from utils import ...` works while keeping a utils.py
module at project root.

This module dynamically loads the sibling `utils.py` and re-exports its symbols
so existing imports continue to function even if a `utils/` directory exists.
"""
import importlib.util
import os
import sys

# load the sibling utils.py as a module named _utils_module
_parent_utils_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "utils/utils.py"))
_spec = importlib.util.spec_from_file_location("_utils_module", _parent_utils_path)
_utils_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_utils_mod)

# re-export public symbols
for _name in getattr(_utils_mod, "__all__", [n for n in dir(_utils_mod) if not n.startswith("__")]):
	globals()[_name] = getattr(_utils_mod, _name)

__all__ = [n for n in dir() if not n.startswith("__")]
