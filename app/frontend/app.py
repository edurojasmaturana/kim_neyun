"""
KIM-NEYÜN — Entry Point
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PAGE_CONFIG

st.set_page_config(**PAGE_CONFIG)

if "token" not in st.session_state:
    st.session_state.token = None

if st.session_state.token:
    st.switch_page("pages/1_Dashboard.py")
else:
    st.switch_page("pages/login.py")
