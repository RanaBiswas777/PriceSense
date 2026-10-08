"""PriceSense Streamlit entry point."""

import streamlit as st

import config
from database import init_db
from ui.analyze_page import render_analyze_page

st.set_page_config(
    page_title=config.APP_NAME,
    page_icon="💰",
    layout="wide",
)

init_db()
render_analyze_page(config.APP_NAME)
