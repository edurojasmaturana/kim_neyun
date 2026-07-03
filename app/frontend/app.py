"""
KIM-NEYÜN — Entry Point
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

login_page     = st.Page("pages/login.py",                title="Iniciar sesión",        url_path="login")
dashboard_page = st.Page("pages/1_Estimacion_Demanda.py", title="Estimación de Demanda", url_path="dashboard", default=True)
admin_page     = st.Page("pages/2_Admin.py",              title="Administración",         url_path="admin")

_token = st.session_state.get("token")
_role  = st.session_state.get("user_role")

if not _token:
    pg = st.navigation([login_page], position="hidden")
elif _role == "admin":
    pg = st.navigation([dashboard_page, admin_page])
else:
    pg = st.navigation([dashboard_page], position="hidden")

pg.run()
