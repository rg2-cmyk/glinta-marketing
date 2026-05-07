import streamlit as st

st.set_page_config(
    page_title="Glinta Marketing",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

pg = st.navigation([
    st.Page("pages/0_Performance.py", title="Performance",         icon="📊", default=True),
    st.Page("pages/6_Campaigns.py",   title="Campaign Dashboard",  icon="📌"),
    st.Page("pages/1_Planning.py",    title="Planning",            icon="📅"),
    st.Page("pages/2_Decisioning.py", title="Decisioning",         icon="🎯"),
    st.Page("pages/3_Generation.py",  title="Content Generation",  icon="✍️"),
    st.Page("pages/4_Design.py",      title="Design",              icon="🎨"),
    st.Page("pages/5_Execution.py",   title="QA & Execution",      icon="🚀"),
])
pg.run()
