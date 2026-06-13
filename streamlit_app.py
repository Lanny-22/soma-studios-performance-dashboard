"""Streamlit entry point (local + Streamlit Community Cloud)."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_streamlit_secrets() -> None:
    """Map Streamlit Cloud secrets into env vars for pydantic-settings."""
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            for key in ("DATABASE_URL", "DASHBOARD_PASSWORD", "LOGO_URL"):
                if key not in os.environ and key in st.secrets:
                    os.environ[key] = str(st.secrets[key])
    except Exception:
        pass


_load_streamlit_secrets()

from dashboard.app import main

main()
