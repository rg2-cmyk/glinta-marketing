import streamlit as st

COLORS = {
    "yellow":   "#f5f000",
    "lavender": "#e8c5ff",
    "lime":     "#caf30b",
    "black":    "#000000",
    "white":    "#FFFFFF",
    "offwhite": "#F7F7F7",
    "border":   "#E4E4E4",
    "muted":    "#888888",
    "email":    "#000000",
    "sms":      "#e8c5ff",
    "danger":   "#C0392B",
    "warn":     "#E67E22",
    "good":     "#27AE60",
}

CMAP = {
    "email": "#1a1a1a",
    "sms":   "#BBBBBB",
    "EMAIL": "#1a1a1a",
    "SMS":   "#BBBBBB",
}

PHASE_META = {
    "planning":    {"label": "1. Planning",    "icon": ""},
    "decisioning": {"label": "2. Decisioning", "icon": ""},
    "generation":  {"label": "3. Generation",  "icon": ""},
    "design":      {"label": "4. Design",      "icon": ""},
    "execution":   {"label": "5. Execution",   "icon": ""},
}

PHASE_PAGES = {
    "planning":    "pages/1_Planning.py",
    "decisioning": "pages/2_Decisioning.py",
    "generation":  "pages/3_Generation.py",
    "design":      "pages/4_Design.py",
    "execution":   "pages/5_Execution.py",
}


def inject_css():
    st.markdown(f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Barlow:wght@400;500;600&display=swap');

      html, body, [class*="css"] {{
        font-family: 'Barlow', -apple-system, sans-serif;
        background-color: {COLORS['white']};
        color: {COLORS['black']};
      }}
      #MainMenu, footer, header {{ visibility: hidden; }}
      .block-container {{ padding: 1.75rem 2.5rem 4rem; max-width: 1500px; }}

      /* ── Page title ── */
      h1 {{
        font-family: 'Barlow Condensed', sans-serif !important;
        font-size: 1.9rem !important;
        font-weight: 800 !important;
        letter-spacing: 0.03em !important;
        text-transform: uppercase !important;
        line-height: 1.1 !important;
        color: {COLORS['black']} !important;
        margin-bottom: 0.25rem !important;
      }}

      /* ── Section headers ── */
      h2 {{
        font-family: 'Barlow Condensed', sans-serif !important;
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.04em !important;
        text-transform: uppercase !important;
        color: {COLORS['black']} !important;
        margin-top: 1.5rem !important;
        margin-bottom: 0.4rem !important;
      }}

      /* ── Sub-headers ── */
      h3 {{
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.65rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.07em !important;
        text-transform: uppercase !important;
        color: {COLORS['muted']} !important;
        margin-top: 1rem !important;
        margin-bottom: 0.3rem !important;
      }}

      /* ── Tabs ── */
      [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        gap: 2px;
        background: {COLORS['offwhite']};
        padding: 4px;
        border-radius: 8px;
        border: 1px solid {COLORS['border']};
        width: fit-content;
      }}
      [data-testid="stTabs"] [data-baseweb="tab"] {{
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.02em !important;
        color: {COLORS['muted']} !important;
        padding: 0.35rem 1rem !important;
        border-radius: 6px !important;
        border: none !important;
        background: transparent !important;
      }}
      [data-testid="stTabs"] [aria-selected="true"] {{
        color: {COLORS['black']} !important;
        background: {COLORS['yellow']} !important;
        font-weight: 600 !important;
      }}

      /* ── Metric cards ── */
      [data-testid="metric-container"] {{
        background: {COLORS['white']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        padding: 1rem 1.25rem !important;
      }}
      [data-testid="metric-container"] label {{
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.65rem !important;
        letter-spacing: 0.07em !important;
        text-transform: uppercase !important;
        color: {COLORS['muted']} !important;
        font-weight: 500 !important;
      }}
      [data-testid="metric-container"] [data-testid="stMetricValue"] {{
        font-family: 'Barlow Condensed', sans-serif !important;
        font-size: 1.65rem !important;
        font-weight: 700 !important;
        color: {COLORS['black']} !important;
        letter-spacing: 0.01em;
      }}
      [data-testid="stMetricDelta"] {{
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.72rem !important;
      }}

      /* ── Selects ── */
      [data-baseweb="select"] > div {{
        border: 1px solid {COLORS['border']} !important;
        border-radius: 6px !important;
        background: {COLORS['white']} !important;
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.85rem !important;
      }}
      label[data-testid="stWidgetLabel"] p {{
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.63rem !important;
        letter-spacing: 0.07em !important;
        text-transform: uppercase !important;
        color: {COLORS['muted']} !important;
        font-weight: 500 !important;
      }}

      /* ── Divider ── */
      hr {{
        border: none !important;
        border-top: 1px solid {COLORS['border']} !important;
        margin: 1.5rem 0 !important;
      }}

      /* ── Buttons ── */
      [data-testid="stButton"] button[kind="primary"] {{
        background: {COLORS['black']} !important;
        color: {COLORS['white']} !important;
        border: none !important;
        border-radius: 6px !important;
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
        padding: 0.4rem 1rem !important;
      }}
      [data-testid="stButton"] button[kind="primary"]:hover {{
        background: #222222 !important;
      }}
      [data-testid="stButton"] button[kind="secondary"] {{
        background: {COLORS['white']} !important;
        color: {COLORS['black']} !important;
        border: 1px solid {COLORS['border']} !important;
        border-radius: 6px !important;
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.02em !important;
        padding: 0.4rem 1rem !important;
      }}
      [data-testid="stButton"] button[kind="secondary"]:hover {{
        border-color: {COLORS['black']} !important;
      }}

      /* ── Expander ── */
      [data-testid="stExpander"] {{
        border: 1px solid {COLORS['border']} !important;
        border-radius: 8px !important;
      }}

      /* ── Text area ── */
      [data-testid="stTextArea"] textarea {{
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.85rem !important;
        border: 1px solid {COLORS['border']} !important;
        border-radius: 6px !important;
        line-height: 1.5 !important;
      }}

      /* ── Checkbox ── */
      [data-testid="stCheckbox"] label p {{
        font-size: 0.85rem !important;
        font-family: 'Barlow', sans-serif !important;
      }}

      /* ── Page links ── */
      [data-testid="stPageLink"] a {{
        font-family: 'Barlow', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.01em !important;
        color: {COLORS['muted']} !important;
      }}
      [data-testid="stPageLink"] a:hover {{
        color: {COLORS['black']} !important;
      }}
    </style>
    """, unsafe_allow_html=True)


def plot_theme(**overrides):
    base = dict(
        paper_bgcolor=COLORS["white"],
        plot_bgcolor=COLORS["white"],
        font=dict(family="Barlow, sans-serif", color="#555555", size=11),
        title_font=dict(family="Barlow, sans-serif", size=11, color=COLORS["black"]),
        title_text="",
        title_x=0,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=10, family="Barlow, sans-serif"),
                    bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0, r=0, t=36, b=0),
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=10),
                   linecolor=COLORS["border"], showline=False),
        yaxis=dict(showgrid=True, gridcolor=COLORS["border"], gridwidth=1,
                   zeroline=False, tickfont=dict(size=10), showline=False),
        colorway=["#1a1a1a", "#BBBBBB", COLORS["yellow"], "#CCCCCC"],
    )
    base.update(overrides)
    return base


def top_nav(current_page):
    """Horizontal phase navigation bar shown at the top of every page."""
    pages = [
        ("pages/0_Performance.py",  "Performance"),
        ("pages/6_Campaigns.py",    "Campaign Dashboard"),
        ("pages/1_Planning.py",     "Planning"),
        ("pages/2_Decisioning.py",  "Decisioning"),
        ("pages/3_Generation.py",   "Content Generation"),
        ("pages/4_Design.py",       "Design"),
        ("pages/5_Execution.py",    "QA Review"),
    ]
    cols = st.columns(len(pages))
    for col, (path, label) in zip(cols, pages):
        is_current = (label.lower() == current_page.lower())
        with col:
            if is_current:
                st.markdown(
                    f'<div style="text-align:center;padding:6px 0;'
                    f'border-bottom:2px solid {COLORS["black"]};'
                    f'font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
                    f'font-weight:700;color:{COLORS["black"]};">{label}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.page_link(path, label=label, use_container_width=True)
    st.markdown(
        f'<div style="border-bottom:1px solid {COLORS["border"]};margin-bottom:1.5rem;"></div>',
        unsafe_allow_html=True,
    )


def phase_stepper(current_phase):
    phases = ["planning", "decisioning", "generation", "design", "execution"]
    labels = ["1. Planning", "2. Decisioning", "3. Content Generation", "4. Design", "5. QA Review"]
    parts = []
    for ph, lb in zip(phases, labels):
        is_current = (ph == current_phase)
        is_done = phases.index(ph) < phases.index(current_phase)
        if is_current:
            style = (f"font-family:'Barlow',sans-serif;font-size:0.78rem;font-weight:600;"
                     f"color:{COLORS['black']};border-bottom:2px solid {COLORS['black']};"
                     f"padding-bottom:2px;")
        elif is_done:
            style = (f"font-family:'Barlow',sans-serif;font-size:0.78rem;font-weight:400;"
                     f"color:{COLORS['muted']};")
        else:
            style = (f"font-family:'Barlow',sans-serif;font-size:0.78rem;font-weight:400;"
                     f"color:#CCCCCC;")
        parts.append(f'<span style="{style}">{lb}</span>')

    sep = f'<span style="color:{COLORS["border"]};font-size:0.78rem;margin:0 10px;">·</span>'
    html = (f'<div style="display:flex;align-items:center;margin-bottom:1.25rem;">'
            + sep.join(parts) + "</div>")
    st.markdown(html, unsafe_allow_html=True)


def campaign_context_card(camp):
    ch = camp["channel"].upper()
    ch_bg  = "#1a1a1a" if camp["channel"] == "email" else "#f0f0f0"
    ch_txt = "#ffffff"  if camp["channel"] == "email" else COLORS["black"]
    pri_colors = {"High": COLORS["danger"], "Medium": COLORS["warn"], "Low": COLORS["muted"]}
    pri_color = pri_colors.get(camp["priority"], COLORS["muted"])

    send_str = camp["send_date"].strftime("%b %d, %Y")
    aud = f"{camp['audience_est']:,}"
    rev = (f"${camp['revenue_est']/1e6:.1f}M" if camp['revenue_est'] >= 1_000_000
           else f"${camp['revenue_est']/1e3:.1f}K")

    st.markdown(f"""
    <div style="background:{COLORS['offwhite']};border:1px solid {COLORS['border']};
                border-radius:8px;padding:12px 20px;display:flex;
                align-items:center;gap:20px;flex-wrap:wrap;margin-bottom:1.25rem;">
      <div>
        <div style="font-family:'Barlow',sans-serif;font-size:0.6rem;letter-spacing:0.08em;
                    text-transform:uppercase;color:{COLORS['muted']};font-weight:500;
                    margin-bottom:3px;">Active Campaign</div>
        <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.2rem;
                    font-weight:700;color:{COLORS['black']};">{camp['name']}</div>
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-left:auto;align-items:center;">
        <span style="background:{ch_bg};color:{ch_txt};padding:3px 10px;
                     border-radius:4px;font-size:0.65rem;font-weight:600;
                     font-family:'Barlow',sans-serif;">{ch}</span>
        <span style="color:{pri_color};font-size:0.72rem;font-weight:600;
                     font-family:'Barlow',sans-serif;">{camp['priority']} Priority</span>
        <span style="color:{COLORS['border']};font-size:0.75rem;">|</span>
        <span style="font-size:0.78rem;color:{COLORS['muted']};
                     font-family:'Barlow',sans-serif;">{send_str}</span>
        <span style="color:{COLORS['border']};font-size:0.75rem;">|</span>
        <span style="font-size:0.78rem;color:{COLORS['muted']};
                     font-family:'Barlow',sans-serif;">{aud} recipients</span>
        <span style="color:{COLORS['border']};font-size:0.75rem;">|</span>
        <span style="font-size:0.78rem;color:{COLORS['muted']};
                     font-family:'Barlow',sans-serif;">{rev} est. revenue</span>
        <span style="color:{COLORS['border']};font-size:0.75rem;">|</span>
        <span style="font-size:0.78rem;color:{COLORS['muted']};
                     font-family:'Barlow',sans-serif;">{camp['assigned_to']}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)
