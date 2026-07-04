from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / "material_master" / "build_material_master_browser_data.py"

if __name__ == "__main__":
    runpy.run_path(str(_TARGET), run_name="__main__")
else:
    _spec = importlib.util.spec_from_file_location("_nexterp_script_build_material_master_browser_data", _TARGET)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Cannot load script module: {_TARGET}")
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _module
    _spec.loader.exec_module(_module)
    for _key, _value in vars(_module).items():
        if _key in {"__builtins__", "__cached__", "__file__", "__loader__", "__name__", "__package__", "__spec__"}:
            continue
        globals()[_key] = _value
    __all__ = getattr(_module, "__all__", [k for k in vars(_module) if not k.startswith("_")])
