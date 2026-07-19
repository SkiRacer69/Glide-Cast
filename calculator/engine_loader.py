from __future__ import annotations

"""
Engine loader for the Django app.

Prefers racewax_engine_v10.py (RaceWax Oracle v10, no Streamlit), then caculatordonotchange.py,
then calculator/engine.py (Streamlit stubbed).
"""

import sys
import types
from pathlib import Path


class _StreamlitStub:
    def set_page_config(self, *args, **kwargs):
        pass

    def markdown(self, *args, **kwargs):
        pass

    def cache_data(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    @property
    def sidebar(self):
        return self


def _load_engine():
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    v10 = project_root / "racewax_engine_v10.py"
    if v10.exists() and v10.stat().st_size > 100:
        return __import__("racewax_engine_v10")
    user_engine = project_root / "caculatordonotchange.py"
    if user_engine.exists() and user_engine.stat().st_size > 100:
        return __import__("caculatordonotchange")

    # Fallback: load calculator/engine.py and run only the part before Streamlit UI
    engine_path = Path(__file__).resolve().parent / "engine.py"
    source = engine_path.read_text(encoding="utf-8")
    marker = "\nwith st.sidebar:"
    if marker in source:
        source = source.split(marker, 1)[0]
    # Prevent real Streamlit import so Django doesn't need a Streamlit runtime
    source = source.replace("import streamlit as st\n", "\n").replace("import streamlit as st", "")
    ns = {"st": _StreamlitStub()}
    exec(compile(source, str(engine_path), "exec"), ns, ns)
    return types.SimpleNamespace(**{k: v for k, v in ns.items() if not k.startswith("_")})


ENGINE = _load_engine()


