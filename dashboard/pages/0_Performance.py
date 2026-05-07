import sys, re as _re
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from shared.styles import COLORS, CMAP, inject_css, plot_theme, top_nav
import numpy as np
from collections import Counter
from shared.data import load_data, load_product_studio, load_list_growth, fmt_revenue

inject_css()
top_nav("Performance")

st.markdown(f"""
<style>
  .kpi-group-wrap {{
    display: flex;
    gap: 0;
    align-items: stretch;
  }}
  .kpi-group {{
    display: flex;
    flex-direction: column;
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    overflow: hidden;
    flex: 1;
  }}
  .kpi-group-label {{
    font-family: 'Barlow', sans-serif;
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {COLORS['muted']};
    background: {COLORS['offwhite']};
    border-bottom: 1px solid {COLORS['border']};
    padding: 5px 12px;
  }}
  .kpi-group-cells {{
    display: flex;
    flex: 1;
  }}
  .kpi-cell {{
    flex: 1;
    padding: 10px 14px;
    border-right: 1px solid {COLORS['border']};
    background: {COLORS['white']};
  }}
  .kpi-cell:last-child {{ border-right: none; }}
  .kpi-label {{
    font-family: 'Barlow', sans-serif;
    font-size: 0.6rem;
    font-weight: 500;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: {COLORS['muted']};
    margin-bottom: 4px;
    white-space: nowrap;
  }}
  .kpi-value {{
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: {COLORS['black']};
    line-height: 1;
    white-space: nowrap;
    letter-spacing: 0.01em;
  }}
  .kpi-value.issues {{ color: {COLORS['danger']}; }}
  .kpi-group-divider {{ width: 12px; flex-shrink: 0; }}
</style>
""", unsafe_allow_html=True)

st.markdown("<h1>Performance</h1>", unsafe_allow_html=True)

campaigns_df, flow_monthly, flow_msgs, benchmarks = load_data()

tab_camp, tab_flow, tab_ps, tab_channels, tab_track = st.tabs(
    ["Campaigns", "Flows", "Products & Studios", "Channels", "Tracking"]
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def kpi_cell(label, value, issue=False):
    cls = "kpi-value issues" if issue else "kpi-value"
    return (f'<div class="kpi-cell"><div class="kpi-label">{label}</div>'
            f'<div class="{cls}">{value}</div></div>')

def kpi_group(group_label, cells_html):
    return (f'<div class="kpi-group"><div class="kpi-group-label">{group_label}</div>'
            f'<div class="kpi-group-cells">{cells_html}</div></div>')

def fmt_pct(val, decimals=1):
    return "—" if pd.isna(val) else f"{val * 100:.{decimals}f}%"

def fmt_rev_consistent(vals):
    mx = vals.max() if hasattr(vals, "max") else vals
    if mx >= 1_000_000:
        return lambda v: f"${v/1e6:.1f}M"
    return lambda v: f"${v/1e3:.1f}K"

def _bg(val, ind, good, great, lower_better=False):
    """4-tier: red=below industry / yellow=ind→good / light-green=good→great / dark-green=above great"""
    if pd.isna(val) or ind is None or good is None or great is None:
        return ""
    if lower_better:
        if val <= great: return "#81C784"
        if val <= good:  return "#C8F7C5"
        if val <= ind:   return "#FFF9C4"
        return "#FFCDD2"
    else:
        if val >= great: return "#81C784"
        if val >= good:  return "#C8F7C5"
        if val >= ind:   return "#FFF9C4"
        return "#FFCDD2"

def _sent_fmt(n):
    return f"{n/1e6:.1f}M" if n >= 1e6 else f"{n/1e3:.0f}K"

def _pill(ch):
    if ch == "email":
        return ('<span style="background:#1a1a1a;color:#ffffff;padding:2px 8px;'
                'border-radius:4px;font-size:0.63rem;font-weight:600;'
                'font-family:\'Barlow\',sans-serif;">EMAIL</span>')
    return ('<span style="background:#f0f0f0;color:#444;padding:2px 8px;'
            'border-radius:4px;font-size:0.63rem;font-weight:600;'
            'border:1px solid #ddd;font-family:\'Barlow\',sans-serif;">SMS</span>')

THEME_PATTERNS = [
    ("Urgency",          r'today only|flash|\d+\s*hr\b|ends |last chance|tmrw|tonight'),
    ("Discount/Promo",   r'\d+\s*%\s*off|save|sale\b|markdowns|free '),
    ("New / Launch",     r'new drop|now open|opens soon|launch|introducing|just dropped'),
    ("Restock",          r'back in stock|it.s back|back:'),
    ("FOMO / Winback",   r'forget|forgot|skip|miss|you didn|you clicked|left behind|really skip'),
    ("Question",         r'\?'),
    ("Has Emoji",        r'[\U0001F300-\U0001FAFF\u2600-\u27BF]'),
    ("Product-Specific", r'flatback|hoop|huggi|clicker|pearl|opal|diamond|stud|earring'),
    ("Studio / Appt",    r'appt|appointment|studio|piercing at|free.*pierc|pierc.*free'),
    ("Editorial",        r'trend|the edit|wellness|101|anatomy|guide|how to'),
]

def detect_themes(text):
    t = str(text)
    tags = [name for name, pat in THEME_PATTERNS
            if _re.search(pat, t, flags=_re.IGNORECASE)]
    return tags if tags else ["Other"]

CAT_PALETTE = [
    "#1a1a1a","#555555","#888888","#AAAAAA","#CCCCCC",
    "#4A7FA5","#7BAFD4","#A8C8E0","#6B8F71","#9BBE9F",
    "#C4956A","#E2B48A","#B87D6B","#D4A999",
]

# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGNS TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_camp:
    df = campaigns_df.copy()

    # ── Filters ─────────────────────────────────────────────────────────────
    f1, f2, f3, _ = st.columns([1.5, 1.5, 1.5, 5])
    years     = sorted(df["Send Date"].dt.year.dropna().unique().astype(int).tolist(), reverse=True)
    ch_opts   = ["All Channels", "Email", "SMS"]
    cat_opts  = ["All Categories"] + sorted(df["Category"].dropna().unique().tolist())

    with f1: sel_year = st.selectbox("Year", ["All Years"] + [str(y) for y in years], key="pc_yr")
    with f2: sel_ch   = st.selectbox("Channel", ch_opts, key="pc_ch")
    with f3: sel_cat  = st.selectbox("Category", cat_opts, key="pc_cat")

    filt = df.copy()
    if sel_year != "All Years":           filt = filt[filt["Send Date"].dt.year == int(sel_year)]
    if sel_ch == "Email":                 filt = filt[filt["Channel"] == "email"]
    elif sel_ch == "SMS":                 filt = filt[filt["Channel"] == "sms"]
    if sel_cat != "All Categories":       filt = filt[filt["Category"] == sel_cat]

    # ── Pull benchmark values ─────────────────────────────────────────────────
    def _bval(metric, col):
        row = benchmarks[benchmarks["Metric"] == metric]
        return float(row[col].iloc[0]) if not row.empty else None

    BM = {
        "open":   {"ind": _bval("Open Rate (Campaign)",       "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Open Rate (Campaign)",      "Good"),
                   "great": _bval("Open Rate (Campaign)",     "Great")},
        "click":  {"ind": _bval("Click Rate (Campaign)",      "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Click Rate (Campaign)",     "Good"),
                   "great": _bval("Click Rate (Campaign)",    "Great")},
        "ctor":   {"ind": _bval("CTOR (Campaign)",            "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("CTOR (Campaign)",           "Good"),
                   "great": _bval("CTOR (Campaign)",          "Great")},
        "conv":   {"ind": _bval("Conversion Rate (Campaign)", "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Conversion Rate (Campaign)","Good"),
                   "great": _bval("Conversion Rate (Campaign)","Great")},
        "rpr":    {"ind": _bval("RPR (Campaign)",             "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("RPR (Campaign)",            "Good"),
                   "great": _bval("RPR (Campaign)",           "Great")},
        "del":    {"ind": _bval("Delivery Rate",              "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Delivery Rate",             "Good"),
                   "great": _bval("Delivery Rate",            "Great")},
        "unsub":  {"ind": _bval("Unsub Rate (Campaign)",      "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Unsub Rate (Campaign)",     "Good"),
                   "great": _bval("Unsub Rate (Campaign)",    "Great")},
        "spam":   {"ind": _bval("Spam Rate (Campaign)",       "Industry Median (DTC Jewelry/Beauty)"),
                   "good": _bval("Spam Rate (Campaign)",      "Good"),
                   "great": _bval("Spam Rate (Campaign)",     "Great")},
    }

    # SMS-specific benchmarks (fall back to email benchmarks where no SMS value)
    BM_SMS = {
        "open":  None,  # not tracked for SMS
        "click": {"ind": _bval("SMS Click Rate", "Industry Median (DTC Jewelry/Beauty)"),
                  "good": _bval("SMS Click Rate", "Good"),
                  "great": _bval("SMS Click Rate", "Great")},
        "ctor":  None,  # not tracked for SMS
        "conv":  {"ind": _bval("SMS Conv Rate",  "Industry Median (DTC Jewelry/Beauty)"),
                  "good": _bval("SMS Conv Rate",  "Good"),
                  "great": _bval("SMS Conv Rate",  "Great")},
        "rpr":   BM["rpr"],
        "del":   BM["del"],
        "unsub": {"ind": _bval("SMS Unsub Rate", "Industry Median (DTC Jewelry/Beauty)"),
                  "good": _bval("SMS Unsub Rate", "Good"),
                  "great": _bval("SMS Unsub Rate", "Great")},
        "spam":  None,  # not tracked for SMS
    }

    # ── KPI computations (weighted averages: sum numerator / sum denominator) ─
    total_camps   = len(filt)
    months_span   = filt["Send Date"].dt.to_period("M").nunique()
    avg_per_month = total_camps / months_span if months_span else 0
    total_rev     = filt["Revenue"].sum()
    avg_camp_rev  = total_rev / total_camps if total_camps else 0

    _sent_sum  = filt["Recipients"].sum()
    _del_sum   = filt["Delivered"].sum()
    _opens_sum = filt["Unique Opens"].sum()
    _clicks_sum= filt["Unique Clicks"].sum()
    _conv_sum  = filt["Unique Conversions"].sum()
    _unsub_sum = filt["Unsubscribes"].sum()

    avg_rpr   = total_rev    / _del_sum    if _del_sum   else 0
    avg_aov   = total_rev    / _conv_sum   if _conv_sum  else 0
    avg_open  = _opens_sum   / _del_sum    if _del_sum   else 0
    avg_click = _clicks_sum  / _del_sum    if _del_sum   else 0
    avg_conv  = _conv_sum    / _del_sum    if _del_sum   else 0
    avg_unsub = _unsub_sum   / _del_sum    if _del_sum   else 0

    rfmt = fmt_rev_consistent(pd.Series([total_rev, avg_camp_rev]))

    # ── KPI Strip ────────────────────────────────────────────────────────────
    strip_html = (
        '<div class="kpi-group-wrap">'
        + kpi_group("Volume",
            kpi_cell("Campaigns", f"{total_camps:,}") +
            kpi_cell("Avg / Month", f"{avg_per_month:.1f}"))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Financials",
            kpi_cell("Revenue", rfmt(total_rev)) +
            kpi_cell("Avg Campaign Rev", rfmt(avg_camp_rev)) +
            kpi_cell("Avg RPR", f"${avg_rpr:.2f}") +
            kpi_cell("AOV", f"${avg_aov:,.0f}"))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Performance",
            kpi_cell("Open Rate", "—" if sel_ch == "SMS" else fmt_pct(avg_open)) +
            kpi_cell("Click Rate", fmt_pct(avg_click)) +
            kpi_cell("Conv. Rate", fmt_pct(avg_conv)))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Issues", kpi_cell("Unsub Rate", fmt_pct(avg_unsub), issue=True))
        + '</div>'
    )
    st.markdown(strip_html, unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Benchmarks banner ────────────────────────────────────────────────────
    # benchmark tier helper — used inside the table row below
    def _bm_tier(ind, good, great, fmt_fn):
        s = "font-family:'Barlow',sans-serif;font-size:0.6rem;display:block;line-height:1.55;"
        return (
            f'<span style="{s}color:#999;">{fmt_fn(ind)}</span>'
            f'<span style="{s}color:#E07B00;">{fmt_fn(good)}</span>'
            f'<span style="{s}color:#1a9e3f;">{fmt_fn(great)}</span>'
        )
    def _pct(v):  return f"{v*100:.1f}%"
    def _pct2(v): return f"{v*100:.2f}%"
    def _dollar(v): return f"${v:.2f}"

    # ── Click rate by category + Revenue pie ─────────────────────────────────
    st.markdown("<h2>Revenue by Category</h2>", unsafe_allow_html=True)

    filt_dated = filt.dropna(subset=["Send Date", "Revenue"]).copy()
    filt_dated["Month"] = filt_dated["Send Date"].dt.to_period("M").dt.to_timestamp()

    cat_rev_total = filt_dated.groupby("Category")["Revenue"].sum().sort_values(ascending=False)
    cat_order_rev = cat_rev_total.index.tolist()
    cat_color_map = {cat: CAT_PALETTE[i % len(CAT_PALETTE)] for i, cat in enumerate(cat_order_rev)}

    # Monthly revenue per category — used for anomaly detection
    monthly_cat = filt_dated.groupby(["Month", "Category"])["Revenue"].sum().reset_index()

    # Click rate by category (weighted average: sum unique clicks / sum delivered)
    click_cat = (
        filt.dropna(subset=["Category"])
        .groupby("Category").agg(
            Campaigns  = ("Campaign Name", "count"),
            _Clicks    = ("Unique Clicks", "sum"),
            _Delivered = ("Delivered",     "sum"),
        ).reset_index()
    )
    click_cat["Click_Rate"] = click_cat["_Clicks"] / click_cat["_Delivered"].replace(0, pd.NA)
    click_cat = click_cat.dropna(subset=["Click_Rate"]).sort_values("Click_Rate", ascending=False)

    rv1, rv2 = st.columns([3, 2])
    with rv1:
        fig_cat = px.bar(
            click_cat,
            x="Click_Rate", y="Category", orientation="h",
            color="Click_Rate",
            color_continuous_scale=[[0,"#FFCDD2"],[0.4,"#FFF9C4"],[1,"#C8F7C5"]],
            title="AVG CLICK RATE BY CATEGORY",
            height=380,
            text=click_cat["Click_Rate"].apply(lambda v: f"{v:.2%}"),
            labels={"Click_Rate": "Avg Click Rate", "Category": ""},
            hover_data={"Campaigns": True, "Click_Rate": ":.2%",
                        "_Clicks": False, "_Delivered": False},
        )
        fig_cat.update_layout(**plot_theme(
            yaxis=dict(autorange="reversed", tickfont=dict(size=10),
                       showgrid=False, zeroline=False),
            xaxis=dict(showgrid=True, gridcolor=COLORS["border"],
                       zeroline=False, tickformat=".1%", tickfont=dict(size=10)),
            coloraxis_showscale=False,
        ))
        fig_cat.update_traces(textposition="outside",
                              textfont=dict(size=10, family="Barlow, sans-serif"),
                              marker_line_width=1, marker_line_color=COLORS["black"])
        st.plotly_chart(fig_cat, use_container_width=True)

    with rv2:
        pie_df = cat_rev_total.reset_index()
        pie_df.columns = ["Category", "Revenue"]
        fig_pie = px.pie(
            pie_df, values="Revenue", names="Category",
            color="Category", color_discrete_map=cat_color_map,
            title="REVENUE SHARE BY CATEGORY", height=300, hole=0.38,
        )
        fig_pie.update_layout(
            paper_bgcolor=COLORS["white"],
            font=dict(family="Barlow, sans-serif", size=11),
            title_font=dict(family="Barlow Condensed, sans-serif", size=13, color=COLORS["black"]),
            title_x=0, margin=dict(l=0, r=0, t=40, b=0),
            legend=dict(font=dict(size=9), orientation="v",
                        yanchor="middle", y=0.5, xanchor="left", x=1.01),
            showlegend=True,
        )
        fig_pie.update_traces(
            textposition="inside", textinfo="percent",
            textfont=dict(size=9, family="Barlow, sans-serif"),
            marker=dict(line=dict(color=COLORS["white"], width=1.5)),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        # ── Revenue spike / anomaly detection ────────────────────────────────
        _SEASONAL = {
            2: "likely Valentine's Day",  5: "likely Mother's Day",
            6: "likely Father's Day",    11: "likely BFCM",
            12: "likely holiday gifting",
        }
        anomalies = []
        for cat, grp in monthly_cat.groupby("Category"):
            if len(grp) < 3:
                continue
            mean_rev = grp["Revenue"].mean()
            std_rev  = grp["Revenue"].std()
            if not std_rev or pd.isna(std_rev):
                continue
            spike_mask = (grp["Revenue"] > mean_rev + 1.5 * std_rev) &                          (grp["Revenue"] > mean_rev * 1.5)
            for _, s in grp[spike_mask].iterrows():
                label = _SEASONAL.get(s["Month"].month, "likely seasonal event")
                anomalies.append((cat, s["Month"], s["Revenue"], s["Revenue"] / mean_rev, label))

        if anomalies:
            anomalies.sort(key=lambda x: x[3], reverse=True)
            items_html = ""
            for cat, month_ts, rev, mult, label in anomalies[:6]:
                mstr = month_ts.strftime("%b %Y")
                items_html += (
                    f"<div style=\"padding:5px 0;border-bottom:1px solid #f0f0f0;line-height:1.4;\">"
                    f"<span style=\"font-family:'Barlow',sans-serif;font-size:0.73rem;"
                    f"font-weight:600;color:#333;\">{mstr} · {cat}</span>&nbsp;"
                    f"<span style=\"font-family:'Barlow',sans-serif;font-size:0.7rem;color:#666;\">"
                    f"${rev/1e3:.0f}K ({mult:.1f}× avg)</span><br>"
                    f"<span style=\"font-family:'Barlow',sans-serif;font-size:0.62rem;"
                    f"color:#999;font-style:italic;\">{label} — discount when benchmarking</span>"
                    f"</div>"
                )
            st.markdown(
                f"<div style=\"margin-top:2px;\">"
                f"<div style=\"font-family:'Barlow Condensed',sans-serif;font-size:0.6rem;"
                f"letter-spacing:0.09em;text-transform:uppercase;color:#888;margin-bottom:5px;\">"
                f"⚠ Revenue spikes to discount</div>{items_html}</div>",
                unsafe_allow_html=True,
            )

    # ── Performance & Issues by Category ─────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h2>Performance & Issues by Category</h2>", unsafe_allow_html=True)

    perf_df = filt.copy()

    # Sum raw count columns per Category+Channel, then derive rates (weighted averages)
    perf_tbl = (
        perf_df.groupby(["Category", "Channel"]).agg(
            Campaigns    = ("Campaign Name",      "count"),
            Sent         = ("Recipients",         "sum"),
            _Delivered   = ("Delivered",          "sum"),
            _UniqueOpens = ("Unique Opens",       "sum"),
            _UniqueClicks= ("Unique Clicks",      "sum"),
            _UniqueConv  = ("Unique Conversions", "sum"),
            Revenue      = ("Revenue",            "sum"),
            _Unsubs      = ("Unsubscribes",       "sum"),
            _Spam        = ("Spam Complaints",    "sum"),
        ).reset_index().sort_values(["Category", "Channel"])
    )
    _D  = perf_tbl["_Delivered"].replace(0, pd.NA)
    _S  = perf_tbl["Sent"].replace(0, pd.NA)
    _O  = perf_tbl["_UniqueOpens"].replace(0, pd.NA)
    perf_tbl["Del_Rate"]   = perf_tbl["_Delivered"]    / _S
    perf_tbl["Open_Rate"]  = perf_tbl["_UniqueOpens"]  / _D
    perf_tbl["Click_Rate"] = perf_tbl["_UniqueClicks"] / _D
    perf_tbl["CTOR"]       = perf_tbl["_UniqueClicks"] / _O
    perf_tbl["Conv_Rate"]  = perf_tbl["_UniqueConv"]   / _D
    perf_tbl["RPR"]        = perf_tbl["Revenue"]       / _D
    perf_tbl["Unsub_Rate"] = perf_tbl["_Unsubs"]       / _D
    perf_tbl["Spam_Rate"]  = perf_tbl["_Spam"]         / _D
    # Email rows first, then SMS; alphabetical within each channel
    perf_tbl["_ch_ord"] = perf_tbl["Channel"].map({"email": 0, "sms": 1})
    perf_tbl = perf_tbl.sort_values(["_ch_ord", "Category"]).drop(columns="_ch_ord").reset_index(drop=True)

    # 13 cols: Category(11%) | Channel(7%) | 11 equal numeric cols (no Bounce Rate)
    GCOLS = "11% 7% " + " ".join(["7.5%"] * 10) + " auto"

    def _cell(val, bg="", align="center", bold=False, sep=False):
        b = "font-weight:600;" if bold else ""
        s = "border-right:3px solid rgba(0,0,0,0.12);" if sep else ""
        bg_s = f"background:{bg};" if bg else ""
        return (f'<div style="padding:7px 5px;text-align:{align};display:flex;align-items:center;'
                f'{"justify-content:center;" if align=="center" else ""}'
                f'{bg_s}{b}{s}">{val}</div>')

    def _campaign_rows(cat, ch, bm_set):
        def _b(key, level):
            d = bm_set.get(key)
            return d.get(level) if d else None
        sub = filt[(filt["Category"] == cat) & (filt["Channel"] == ch)]\
              .dropna(subset=["Click Rate", "Subject Line"]).copy()
        if sub.empty:
            return "<p style='padding:8px;font-size:0.75rem;color:#888'>No campaigns</p>"

        # Sum raw counts per subject line, derive rates (weighted averages)
        grp = (
            sub.groupby("Subject Line").agg(
                Uses         = ("Campaign Name",      "count"),
                Sent         = ("Recipients",         "sum"),
                _Delivered   = ("Delivered",          "sum"),
                _UniqueOpens = ("Unique Opens",       "sum"),
                _UniqueClicks= ("Unique Clicks",      "sum"),
                _UniqueConv  = ("Unique Conversions", "sum"),
                Revenue      = ("Revenue",            "sum"),
                _Unsubs      = ("Unsubscribes",       "sum"),
                _Spam        = ("Spam Complaints",    "sum"),
            ).reset_index()
        )
        _D  = grp["_Delivered"].replace(0, pd.NA)
        _S  = grp["Sent"].replace(0, pd.NA)
        _O  = grp["_UniqueOpens"].replace(0, pd.NA)
        grp["Del_Rate"]   = grp["_Delivered"]    / _S
        grp["Open_Rate"]  = grp["_UniqueOpens"]  / _D
        grp["Click_Rate"] = grp["_UniqueClicks"] / _D
        grp["CTOR"]       = grp["_UniqueClicks"] / _O
        grp["Conv_Rate"]  = grp["_UniqueConv"]   / _D
        grp["RPR"]        = grp["Revenue"]       / _D
        grp["Unsub_Rate"] = grp["_Unsubs"]       / _D
        grp["Spam_Rate"]  = grp["_Spam"]         / _D
        grp = grp.sort_values("Click_Rate", ascending=False)
        cat_avg = grp["Click_Rate"].mean()

        # shared grid style — same GCOLS as parent so columns align exactly
        grid_style = f"display:grid;grid-template-columns:{GCOLS};align-items:center;"

        # map bg color → text color for the inner rows (colored text, neutral bg)
        _BG_TO_TEXT = {
            "#FFCDD2": "#C0392B",  # red
            "#FFF9C4": "#9A7D00",  # dark yellow
            "#C8F7C5": "#1e7e34",  # light green
            "#81C784": "#145a23",  # dark green
        }

        def _dc(val, bg="", bold=False, sep=False):
            """Inner data cell — colored text on neutral bg instead of colored bg."""
            txt_color = _BG_TO_TEXT.get(bg, "#222")
            fw  = "font-weight:700;" if (bg or bold) else "font-weight:400;"
            br  = "border-right:3px solid rgba(0,0,0,0.08);" if sep else ""
            return (f'<div style="padding:5px 4px;text-align:center;font-size:0.73rem;'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'color:{txt_color};{fw}{br}">{val}</div>')

        # column-header row (inherits same grid)
        lbl = ("font-family:'Barlow Condensed',sans-serif;font-size:0.6rem;"
               "letter-spacing:0.08em;text-transform:uppercase;color:#999;padding:4px 4px;text-align:center;")
        _inner_tips = {
            "Sent":     "Total recipients (sends)",
            "Revenue":  "Sum of revenue attributed ($K)",
            "RPR":      "Revenue ÷ Delivered",
            "Del.":     "Delivered ÷ Recipients",
            "Open":     "Unique Opens ÷ Delivered",
            "Click ★":  "Unique Clicks ÷ Delivered",
            "CTOR":     "Unique Clicks ÷ Unique Opens",
            "Conv":     "Unique Conversions ÷ Delivered",
            "Unsub":    "Unsubscribes ÷ Delivered",
            "Spam":     "Spam Complaints ÷ Delivered",
        }
        hdr = (
            f'<div style="{grid_style}background:#f0f0f0;border-bottom:1px solid #ddd;">'
            f'<div style="{lbl}text-align:left;padding-left:8px;grid-column:span 2;">Subject Line</div>'
            f'<div title="Number of times this subject line was used" style="{lbl}border-right:3px solid #ddd;cursor:help;"># Uses</div>'
            + "".join(f'<div title="{_inner_tips.get(h,"")}" style="{lbl}cursor:help;">{h}</div>'
                      for h in ["Sent","Revenue","RPR","Del.","Open","Click ★","CTOR","Conv","Unsub","Spam"])
            + '</div>'
        )

        rows_html = ""
        for _, c in grp.iterrows():
            themes = detect_themes(c["Subject Line"])
            theme_html = " ".join(
                f'<span style="background:#f0f0f0;color:#666;padding:1px 4px;border-radius:3px;'
                f'font-size:0.56rem;font-weight:500;">{t}</span>'
                for t in themes if t != "Other"
            )
            # adaptive font size: shrink long subject lines, clamp to 2 lines
            sl_len  = len(c["Subject Line"])
            sl_fs   = "0.65rem" if sl_len > 45 else "0.72rem"
            sl_html = (
                f'<div style="padding:5px 6px 5px 8px;font-size:{sl_fs};line-height:1.3;'
                f'overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;'
                f'-webkit-box-orient:vertical;word-break:break-word;grid-column:span 2;">'
                f'{c["Subject Line"]}'
                f'<span style="display:block;margin-top:2px;">{theme_html}</span></div>'
            )
            click_bg  = _bg(c["Click_Rate"], _b("click","ind"), _b("click","good"), _b("click","great"))
            open_cell = _dc("—") if ch == "sms" else \
                        _dc(f'{c["Open_Rate"]:.1%}', bg=_bg(c["Open_Rate"], _b("open","ind"), _b("open","good"), _b("open","great")))

            rows_html += (
                f'<div style="{grid_style}border-bottom:1px solid #eee;">'
                + sl_html
                + _dc(int(c["Uses"]), bold=True, sep=True)
                + _dc(f'{c["Sent"]/1e3:.0f}K')
                + _dc(f'${c["Revenue"]/1e3:.1f}K')
                + _dc(f'${c["RPR"]:.2f}',       bg=_bg(c["RPR"],        _b("rpr","ind"),   _b("rpr","good"),   _b("rpr","great")),  sep=True)
                + _dc(f'{c["Del_Rate"]:.1%}',   bg=_bg(c["Del_Rate"],   _b("del","ind"),   _b("del","good"),   _b("del","great")))
                + open_cell
                + _dc(f'{c["Click_Rate"]:.2%}', bg=click_bg, bold=True)
                + (_dc("—") if ch == "sms" else _dc(f'{c["CTOR"]:.1%}', bg=_bg(c["CTOR"], _b("ctor","ind"), _b("ctor","good"), _b("ctor","great"))))
                + _dc(f'{c["Conv_Rate"]:.2%}',  bg=_bg(c["Conv_Rate"],  _b("conv","ind"),  _b("conv","good"),  _b("conv","great")),  sep=True)
                + _dc(f'{c["Unsub_Rate"]:.2%}', bg=_bg(c["Unsub_Rate"], _b("unsub","ind"), _b("unsub","good"), _b("unsub","great"), True))
                + (_dc("—") if ch == "sms" else _dc(f'{c["Spam_Rate"]:.2%}', bg=_bg(c["Spam_Rate"], _b("spam","ind"), _b("spam","good"), _b("spam","great"), True)))
                + '</div>'
            )

        return hdr + rows_html

    # ── SMS benchmark row (injected above first SMS data row) ────────────────
    _dash_bm = ('<div style="padding:7px 5px;text-align:center;font-family:\'Barlow\',sans-serif;'
                'color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>')
    def _sms_bm_cell(key, fmt_fn, lower_better=False, sep=False):
        d = BM_SMS.get(key)
        sep_s = "border-right:3px solid #4a90d9;" if sep else ""
        if not d or d.get("ind") is None:
            return f'<div style="padding:7px 5px;text-align:center;{sep_s}font-family:\'Barlow\',sans-serif;color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>'
        if lower_better:
            content = _bm_tier(d["ind"], d["good"], d["great"], fmt_fn)
        else:
            content = _bm_tier(d["ind"], d["good"], d["great"], fmt_fn)
        return f'<div style="padding:7px 5px;text-align:center;{sep_s}">{content}</div>'

    sms_bm_html = f"""
    <div style="display:grid;grid-template-columns:{GCOLS};
                background:#f0f5ff;border-bottom:2px solid #4a90d9;
                border-left:4px solid #4a90d9;">
      <div style="padding:7px 9px;font-family:'Barlow Condensed',sans-serif;font-size:0.68rem;
                  font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:#2a5090;
                  display:flex;align-items:center;">SMS BENCHMARK</div>
      <div style="padding:7px 8px;font-family:'Barlow',sans-serif;font-size:0.6rem;
                  color:#999;border-right:3px solid #4a90d9;display:flex;flex-direction:column;
                  justify-content:center;line-height:1.55;">
        <span style="color:#999;">Industry</span>
        <span style="color:#E07B00;">Good</span>
        <span style="color:#1a9e3f;">Great</span>
      </div>
      {_dash_bm}{_dash_bm}{_dash_bm}
      <div style="padding:7px 5px;text-align:center;border-right:3px solid #4a90d9;">{_bm_tier(BM["rpr"]["ind"], BM["rpr"]["good"], BM["rpr"]["great"], _dollar)}<span style="display:block;font-size:0.52rem;color:#aaa;font-style:italic;margin-top:1px;">email</span></div>
      <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["del"]["ind"], BM["del"]["good"], BM["del"]["great"], _pct)}<span style="display:block;font-size:0.52rem;color:#aaa;font-style:italic;margin-top:1px;">email</span></div>
      {_dash_bm}
      {_sms_bm_cell("click", _pct2)}
      {_dash_bm}
      <div style="padding:7px 5px;text-align:center;border-right:3px solid #4a90d9;">{_bm_tier(BM_SMS["conv"]["ind"], BM_SMS["conv"]["good"], BM_SMS["conv"]["great"], _pct2) if BM_SMS["conv"] and BM_SMS["conv"].get("ind") else "—"}</div>
      {_sms_bm_cell("unsub", _pct2, lower_better=True)}
      {_dash_bm}
    </div>"""

    detail_rows_html = ""
    sms_bm_injected  = False
    for _, r in perf_tbl.iterrows():
        is_sms  = r["Channel"] == "sms"
        bm_set  = BM_SMS if is_sms else BM
        def _br(key, level, _bm=bm_set):
            d = _bm.get(key)
            return d.get(level) if d else None

        # Inject SMS benchmark row once, before first SMS data row
        if is_sms and not sms_bm_injected:
            detail_rows_html += sms_bm_html
            sms_bm_injected = True

        detail_rows_html += f"""
        <details class="perf-row" style="border-bottom:1px solid #e8e8e8;">
          <summary style="cursor:pointer;display:block;">
            <div class="row-grid" style="display:grid;grid-template-columns:{GCOLS};
                        align-items:stretch;font-size:0.8rem;min-height:40px;">
              {_cell('<span class="toggle-icon"></span>' + r["Category"], align="left", bold=True)}
              {_cell(_pill(r["Channel"]), align="left", sep=True)}
              {_cell(str(int(r["Campaigns"])))}
              {_cell(f'{r["Sent"]/1e6:.1f}M')}
              {_cell(f'${r["Revenue"]/1e6:.1f}M')}
              {_cell(f'${r["RPR"]:.2f}',       bg=_bg(r["RPR"],        _br("rpr","ind"),   _br("rpr","good"),   _br("rpr","great")),  sep=True)}
              {_cell(f'{r["Del_Rate"]:.1%}',   bg=_bg(r["Del_Rate"],   _br("del","ind"),   _br("del","good"),   _br("del","great")))}
              {_cell("—") if is_sms else _cell(f'{r["Open_Rate"]:.1%}', bg=_bg(r["Open_Rate"], _br("open","ind"), _br("open","good"), _br("open","great")))}
              {_cell(f'{r["Click_Rate"]:.2%}', bg=_bg(r["Click_Rate"], _br("click","ind"), _br("click","good"), _br("click","great")))}
              {_cell("—") if is_sms else _cell(f'{r["CTOR"]:.1%}', bg=_bg(r["CTOR"], _br("ctor","ind"), _br("ctor","good"), _br("ctor","great")))}
              {_cell(f'{r["Conv_Rate"]:.2%}',  bg=_bg(r["Conv_Rate"],  _br("conv","ind"),  _br("conv","good"),  _br("conv","great")),  sep=True)}
              {_cell(f'{r["Unsub_Rate"]:.2%}', bg=_bg(r["Unsub_Rate"], _br("unsub","ind"), _br("unsub","good"), _br("unsub","great"), True))}
              {_cell("—") if is_sms else _cell(f'{r["Spam_Rate"]:.2%}', bg=_bg(r["Spam_Rate"], _br("spam","ind"), _br("spam","good"), _br("spam","great"), True))}
            </div>
          </summary>
          <div style="background:#f8f8f8;padding:10px 16px 14px;border-top:1px solid #ddd;">
            <p style="font-family:'Barlow Condensed',sans-serif;font-size:0.67rem;
                      letter-spacing:0.1em;text-transform:uppercase;color:#888;margin:0 0 8px;">
              {r["Category"].upper()} &mdash; {r["Channel"].upper()}
              &nbsp;&middot;&nbsp; &#9733; click rate colour vs. category average
            </p>
            {_campaign_rows(r["Category"], r["Channel"], bm_set)}
          </div>
        </details>"""

    n_rows = len(perf_tbl)
    perf_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800;900&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
      *, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0; }}
      body {{ font-family:'Barlow',sans-serif; background:#fff; font-size:0.82rem; }}
      details summary {{ list-style:none; }}
      details summary::-webkit-details-marker {{ display:none; }}
      .perf-row summary:hover .row-grid {{ background:#fffde0; }}
      .perf-row[open] summary .row-grid {{ background:#fffde0; }}
      .perf-row[open] summary .toggle-icon::before {{ content:"▼"; }}
      .toggle-icon::before {{ content:"▶"; color:#aaa; font-size:0.6rem; margin-right:5px; }}
    </style></head><body>
    <div style="border:2px solid #000;border-radius:12px;overflow:hidden;">
      <div style="padding:6px 12px;background:#fafafa;border-bottom:1px solid #e8e8e8;
                  display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
        <span style="font-family:'Barlow',sans-serif;font-size:0.6rem;font-weight:700;
                     letter-spacing:0.08em;text-transform:uppercase;color:#888;">Color key</span>
        <span style="background:#FFCDD2;padding:2px 10px;border-radius:3px;font-family:'Barlow',sans-serif;font-size:0.62rem;color:#333;">&#9679; Below industry</span>
        <span style="background:#FFF9C4;padding:2px 10px;border-radius:3px;font-family:'Barlow',sans-serif;font-size:0.62rem;color:#333;">&#9679; Industry → Good</span>
        <span style="background:#C8F7C5;padding:2px 10px;border-radius:3px;font-family:'Barlow',sans-serif;font-size:0.62rem;color:#333;">&#9679; Good → Great</span>
        <span style="background:#81C784;padding:2px 10px;border-radius:3px;font-family:'Barlow',sans-serif;font-size:0.62rem;color:#fff;">&#9679; Above great</span>
      </div>
      <div style="display:grid;grid-template-columns:18% 30% 37.5% auto;background:#000;color:#feee35;">
        <div style="padding:9px 10px;font-family:'Barlow Condensed',sans-serif;font-size:0.72rem;
                    letter-spacing:0.1em;text-transform:uppercase;border-right:3px solid #333;">
          &#9660; Click any row to expand
        </div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;
                    border-right:3px solid #333;">&#x24; Financials</div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;
                    border-right:3px solid #feee35;">&#9650; Performance</div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;">&#9888; Issues</div>
      </div>
      <div style="display:grid;grid-template-columns:{GCOLS};background:#222;color:#fff;font-size:0.67rem;">
        <div style="padding:6px 9px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;">Category</div>
        <div style="padding:6px 8px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;border-right:3px solid #444;">Channel</div>
        <div title="Number of campaigns in this group" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;"># Camp</div>
        <div title="Total recipients (sends)" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Sent</div>
        <div title="Sum of revenue attributed to campaigns" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Revenue</div>
        <div title="Revenue ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #555;cursor:help;">RPR</div>
        <div title="Delivered ÷ Recipients" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Del. Rate</div>
        <div title="Unique Opens ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Open Rate</div>
        <div title="Unique Clicks ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Click Rate</div>
        <div title="Unique Clicks ÷ Unique Opens" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">CTOR</div>
        <div title="Unique Conversions ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #555;cursor:help;">Conv. Rate</div>
        <div title="Unsubscribes ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Unsub Rate</div>
        <div title="Spam Complaints ÷ Delivered" style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;cursor:help;">Spam Rate</div>
      </div>
      <div style="display:grid;grid-template-columns:{GCOLS};
                  background:#fffff0;border-bottom:2px solid #e8d800;
                  border-left:4px solid #f5f000;">
        <div style="padding:7px 9px;font-family:'Barlow Condensed',sans-serif;font-size:0.68rem;
                    font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:#7a6e00;
                    display:flex;align-items:center;">Campaign Benchmarks</div>
        <div style="padding:7px 8px;font-family:'Barlow',sans-serif;font-size:0.6rem;
                    color:#999;border-right:3px solid #e8d800;display:flex;flex-direction:column;
                    justify-content:center;line-height:1.55;">
          <span style="color:#999;">Industry</span>
          <span style="color:#E07B00;">Good</span>
          <span style="color:#1a9e3f;">Great</span>
        </div>
        <div style="padding:7px 5px;text-align:center;font-family:'Barlow',sans-serif;color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>
        <div style="padding:7px 5px;text-align:center;font-family:'Barlow',sans-serif;color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>
        <div style="padding:7px 5px;text-align:center;font-family:'Barlow',sans-serif;color:#bbb;font-size:0.7rem;display:flex;align-items:center;justify-content:center;">—</div>
        <div style="padding:7px 5px;text-align:center;border-right:3px solid #e8d800;">{_bm_tier(BM["rpr"]["ind"],   BM["rpr"]["good"],   BM["rpr"]["great"],   _dollar)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["del"]["ind"],   BM["del"]["good"],   BM["del"]["great"],   _pct)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["open"]["ind"],  BM["open"]["good"],  BM["open"]["great"],  _pct)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["click"]["ind"], BM["click"]["good"], BM["click"]["great"], _pct2)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["ctor"]["ind"],  BM["ctor"]["good"],  BM["ctor"]["great"],  _pct)}</div>
        <div style="padding:7px 5px;text-align:center;border-right:3px solid #e8d800;">{_bm_tier(BM["conv"]["ind"],  BM["conv"]["good"],  BM["conv"]["great"],  _pct2)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["unsub"]["ind"],  BM["unsub"]["good"],  BM["unsub"]["great"], _pct2)}</div>
        <div style="padding:7px 5px;text-align:center;">{_bm_tier(BM["spam"]["ind"],   BM["spam"]["good"],   BM["spam"]["great"],  _pct2)}</div>
      </div>
      {detail_rows_html}
    </div></body></html>"""
    components.html(perf_html, height=n_rows * 44 + 210, scrolling=True)

    # ── Subject Line Themes ───────────────────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h2>Subject Line Themes</h2>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;color:#666;'
        'margin:-0.5rem 0 1rem;">What subject line approaches work across all categories</p>',
        unsafe_allow_html=True,
    )

    theme_df = filt.dropna(subset=["Subject Line", "Click Rate"]).copy()
    theme_df["Themes"] = theme_df["Subject Line"].apply(detect_themes)
    theme_rows_exp = theme_df.explode("Themes")
    theme_agg = (
        theme_rows_exp.groupby("Themes").agg(
            Count      = ("Campaign Name",   "count"),
            Click_Rate = ("Click Rate",      "mean"),
            Conv_Rate  = ("Conversion Rate", "mean"),
            Revenue    = ("Revenue",         "mean"),
            Open_Rate  = ("Open Rate",       "mean"),
        ).reset_index().sort_values("Click_Rate", ascending=False)
    )

    th1, th2 = st.columns([3, 2])
    with th1:
        fig_themes = px.bar(
            theme_agg, x="Click_Rate", y="Themes", orientation="h",
            color="Click_Rate",
            color_continuous_scale=[[0,"#FFCDD2"],[0.4,"#FFF9C4"],[1,"#C8F7C5"]],
            title="AVG CLICK RATE BY SUBJECT LINE THEME", height=360,
            text=theme_agg["Click_Rate"].apply(lambda v: f"{v:.1%}"),
            labels={"Click_Rate":"Avg Click Rate","Themes":""},
            hover_data={"Count":True,"Conv_Rate":":.2%","Revenue":":$,.0f","Click_Rate":":.2%"},
        )
        fig_themes.update_layout(**plot_theme(
            yaxis=dict(autorange="reversed", tickfont=dict(size=10), showgrid=False, zeroline=False),
            xaxis=dict(showgrid=True, gridcolor=COLORS["border"], zeroline=False,
                       tickformat=".1%", tickfont=dict(size=10)),
            coloraxis_showscale=False,
        ))
        fig_themes.update_traces(textposition="outside",
                                  textfont=dict(size=10, family="Barlow, sans-serif"),
                                  marker_line_width=1, marker_line_color=COLORS["black"])
        st.plotly_chart(fig_themes, use_container_width=True)

    with th2:
        st.markdown(
            '<p style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.75rem;'
            'letter-spacing:0.1em;text-transform:uppercase;color:#666;margin-bottom:0.5rem;">'
            'Theme performance summary</p>',
            unsafe_allow_html=True,
        )
        theme_display = theme_agg.rename(columns={
            "Click_Rate":"Click Rate","Conv_Rate":"Conv Rate",
            "Open_Rate":"Open Rate","Revenue":"Avg Revenue",
        })

        def _style_theme_row(row):
            cr = row["Click Rate"]
            if cr >= theme_agg["Click_Rate"].quantile(0.66): bg = "background-color:#C8F7C5"
            elif cr >= theme_agg["Click_Rate"].quantile(0.33): bg = "background-color:#FFF9C4"
            else: bg = "background-color:#FFCDD2"
            return [bg] * len(row)

        st.dataframe(
            theme_display[["Themes","Count","Click Rate","Conv Rate","Avg Revenue"]]
            .style.apply(_style_theme_row, axis=1)
            .format({"Click Rate":"{:.2%}","Conv Rate":"{:.2%}","Avg Revenue":"${:,.0f}"}),
            use_container_width=True, hide_index=True, height=360,
        )


# ────────────────────────────────────────────────────────────────────────────
# EMAIL FREQUENCY & LIST HEALTH  (appended to Campaigns tab)
# ────────────────────────────────────────────────────────────────────────────
with tab_camp:
    st.markdown("---")
    st.markdown("### Email Frequency & List Health")
    st.caption("Weeks where ≥1 audience segment received 2+ campaigns · weighted averages")

    # ── 1. Build weekly campaign metrics ──────────────────────────────────
    _camp = campaigns_df.copy()
    _camp = _camp[_camp["Channel"].str.lower() == "email"].copy()   # email only
    _camp["Week"] = _camp["Send Date"].dt.to_period("W").dt.start_time

    # Parse Audiences column into a list per row
    def _parse_audiences(val):
        if pd.isna(val) or str(val).strip() == "":
            return []
        return [a.strip() for a in str(val).split(",") if a.strip()]

    _camp["_auds"] = _camp["Audiences"].apply(_parse_audiences) \
        if "Audiences" in _camp.columns \
        else pd.Series([[] for _ in range(len(_camp))], index=_camp.index)

    # For each week, find segments that received 2+ campaigns ("overlapping segments")
    def _overlapping_segs(rows):
        cnt = Counter(aud for auds in rows for aud in auds)
        return {seg for seg, n in cnt.items() if n >= 2}

    _week_overlap_segs = _camp.groupby("Week")["_auds"].apply(list).apply(_overlapping_segs)

    # Keep only campaigns where at least one of their audiences is an overlapping segment
    def _row_in_overlap(row):
        segs = _week_overlap_segs.get(row["Week"], set())
        return bool(segs and any(a in segs for a in row["_auds"]))

    _camp["_in_overlap"] = _camp.apply(_row_in_overlap, axis=1)
    _freq = _camp[_camp["_in_overlap"]].copy()

    # Weekly aggregation — x-axis will be Campaigns_n (how many campaigns/week to overlapping segs)
    _wgrp = _freq.groupby("Week").agg(
        Campaigns_n  = ("Campaign Name",      "count"),   # frequency metric
        _Delivered   = ("Delivered",          "sum"),
        _UniqueClicks= ("Unique Clicks",      "sum"),
        _UniqueConv  = ("Unique Conversions", "sum"),
        Revenue      = ("Revenue",            "sum"),
        _Unsubs      = ("Unsubscribes",       "sum"),
    ).reset_index()

    _D = _wgrp["_Delivered"].replace(0, pd.NA)
    _wgrp["Click_Rate"] = _wgrp["_UniqueClicks"] / _D
    _wgrp["Unsub_Rate"] = _wgrp["_Unsubs"]       / _D
    _wgrp["RPR"]        = _wgrp["Revenue"]        / _D

    # ── 2. Join with List Growth data ─────────────────────────────────────
    _lg = load_list_growth()
    _lg["Week"] = _lg["Date"].dt.to_period("W").dt.start_time
    _lg_weekly = _lg.groupby("Week").agg(
        Net_Change   = ("Email Net Change", "sum"),
        Signups      = ("Email Signups",    "sum"),
        Unsubs_lg    = ("Email Unsubs",     "sum"),
        List_Size    = ("Email List Size",  "last"),
    ).reset_index()

    _wgrp = _wgrp.merge(_lg_weekly, on="Week", how="left")
    _wgrp = _wgrp.dropna(subset=["Click_Rate", "Unsub_Rate", "RPR"])

    if len(_wgrp) < 4:
        st.info("Not enough weekly data with audience overlap to show frequency analysis.")
    else:
        # ── 3. Scatter plots ──────────────────────────────────────────────
        _sc1, _sc2, _sc3 = st.columns(3)

        def _scatter_with_trend(col, y_col, y_label, y_fmt, color):
            df_s = _wgrp[["Campaigns_n", y_col, "Week"]].dropna()
            if len(df_s) < 3:
                col.info("Insufficient data")
                return
            x_arr = df_s["Campaigns_n"].values.astype(float)
            y_arr = df_s[y_col].values

            # trendline via numpy polyfit
            coeffs = np.polyfit(x_arr, y_arr, 1)
            x_line = np.linspace(x_arr.min(), x_arr.max(), 80)
            y_line = np.polyval(coeffs, x_line)

            direction = "↑ as frequency ↑" if coeffs[0] > 0 else "↓ as frequency ↑"

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=x_arr, y=y_arr, mode="markers",
                marker=dict(color=color, size=7, opacity=0.8),
                customdata=df_s["Week"].dt.strftime("%b %d, %Y"),
                hovertemplate=(
                    "Week of %{customdata}<br>"
                    f"Campaigns to shared segment: %{{x}}<br>"
                    f"{y_label}: %{{y:{y_fmt}}}<extra></extra>"
                ),
                name="Weeks",
            ))
            fig.add_trace(go.Scatter(
                x=x_line, y=y_line, mode="lines",
                line=dict(color="#888888", width=1.5, dash="dot"),
                name="Trend", hoverinfo="skip",
            ))
            fig.update_layout(
                **plot_theme(
                    margin=dict(t=40, b=40, l=50, r=10),
                    xaxis=dict(
                        title="Campaigns/Week (to shared segment)",
                        dtick=1, tickformat="d",
                        showgrid=False, zeroline=False, tickfont=dict(size=10),
                    ),
                ),
                height=260,
                yaxis_title=y_label,
                yaxis_tickformat=y_fmt,
                showlegend=False,
                title=dict(
                    text=f"<b>{y_label}</b>  <span style='font-size:11px;color:#888'>{direction}</span>",
                    font_size=13, x=0,
                ),
            )
            col.plotly_chart(fig, use_container_width=True)

        _scatter_with_trend(_sc1, "Click_Rate",  "Click Rate",  ".2%",  "#caf30b")
        _scatter_with_trend(_sc2, "Unsub_Rate",  "Unsub Rate",  ".3%",  "#f5a623")
        _scatter_with_trend(_sc3, "RPR",         "RPR",         "$.2f", "#4a90d9")

        # ── 4. List Growth context chart ──────────────────────────────────
        _lg_plot = _wgrp.dropna(subset=["Net_Change"])
        if len(_lg_plot) >= 3:
            st.markdown("#### Campaigns/Week to Shared Segments vs. Email List Net Change")
            fig_lg = go.Figure()
            # Bar: Net Change (from List Growth data)
            fig_lg.add_trace(go.Bar(
                x=_lg_plot["Week"], y=_lg_plot["Net_Change"],
                name="List Net Change",
                marker_color=np.where(_lg_plot["Net_Change"] >= 0, "#caf30b", "#f5a623"),
                opacity=0.8,
                hovertemplate="Week of %{x|%b %d}<br>Net Change: %{y:+,.0f}<extra></extra>",
            ))
            # Line: campaign count on secondary axis
            fig_lg.add_trace(go.Scatter(
                x=_lg_plot["Week"], y=_lg_plot["Campaigns_n"],
                name="Campaigns to shared segment", mode="lines+markers",
                marker=dict(size=5), line=dict(color="#4a90d9", width=2),
                yaxis="y2",
                hovertemplate="Week of %{x|%b %d}<br>Campaigns: %{y}<extra></extra>",
            ))
            fig_lg.update_layout(
                **plot_theme(margin=dict(t=40, b=40, l=60, r=60)),
                height=300,
                xaxis_title="Week",
                yaxis_title="Email List Net Change",
                yaxis2=dict(title="Campaigns to Shared Segment", overlaying="y", side="right",
                            showgrid=False, dtick=1, tickformat="d"),
                legend=dict(orientation="h", y=1.08, x=0),
                barmode="relative",
            )
            st.plotly_chart(fig_lg, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# FLOWS TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_flow:
    fm_all = flow_monthly.copy()
    fmsg   = flow_msgs.copy()

    fm_all["Month"] = pd.to_datetime(fm_all["Month"], errors="coerce")
    avail_min = fm_all["Month"].min()
    avail_max = fm_all["Month"].max()
    today = pd.Timestamp.today().normalize()

    # ── Time period + channel filter ────────────────────────────────────────
    period_opts = ["Year to date", "Last 12 months", "Last 6 months", "Custom range"]
    fp1, fp2, fp3 = st.columns([2, 2, 4])
    with fp1:
        sel_period = st.selectbox("Select time period", period_opts, key="pf_period")
    with fp2:
        sel_fch = st.selectbox("Channel", ["All Channels", "Email", "SMS"], key="pf_ch")

    if sel_period == "Custom range":
        cr1, cr2, _cr3 = st.columns([2, 2, 4])
        with cr1:
            cr_start = st.date_input("Start month", value=avail_min.date(), key="pf_start",
                                      min_value=avail_min.date(), max_value=avail_max.date())
        with cr2:
            cr_end = st.date_input("End month", value=avail_max.date(), key="pf_end",
                                    min_value=avail_min.date(), max_value=avail_max.date())
        d_start = pd.Timestamp(cr_start).normalize()
        d_end   = pd.Timestamp(cr_end).normalize()
    elif sel_period == "Year to date":
        d_start = pd.Timestamp(today.year, 1, 1)
        d_end   = avail_max
    elif sel_period == "Last 12 months":
        d_end   = avail_max
        d_start = (d_end - pd.DateOffset(months=11)).normalize()
    else:  # Last 6 months
        d_end   = avail_max
        d_start = (d_end - pd.DateOffset(months=5)).normalize()

    fm = fm_all[(fm_all["Month"] >= d_start) & (fm_all["Month"] <= d_end)].copy()
    if sel_fch == "Email": fm = fm[fm["Channel"] == "email"]
    elif sel_fch == "SMS": fm = fm[fm["Channel"] == "sms"]

    period_label = f"{d_start.strftime('%b %Y')} – {d_end.strftime('%b %Y')}"
    st.markdown(
        f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#666;'
        f'margin:0 0 0.6rem;">Showing <b>{period_label}</b></p>',
        unsafe_allow_html=True,
    )

    if fm.empty:
        st.info("No flow data in the selected period.")
        st.stop()

    # ── Flow benchmarks (reuse campaign benchmark thresholds) ────────────────
    def _bvf(metric, col):
        row = benchmarks[benchmarks["Metric"] == metric]
        return float(row[col].iloc[0]) if not row.empty else None

    def _bm_row(metric):
        return {
            "ind":   _bvf(metric, "Industry Median (DTC Jewelry/Beauty)"),
            "good":  _bvf(metric, "Good"),
            "great": _bvf(metric, "Great"),
        }
    ALL_BMS = {k: _bm_row(k) for k in [
        "Open Rate (Campaign)", "Click Rate (Campaign)", "CTOR (Campaign)",
        "Conversion Rate (Campaign)", "RPR (Campaign)", "Unsub Rate (Campaign)",
        "Welcome Flow Conv Rate", "Abandoned Cart Conv Rate",
        "Abandoned Checkout Conv Rate", "Back In Stock Conv Rate",
        "Flow RPR (Welcome)", "Flow RPR (Cart)", "Flow RPR (Checkout)",
        "SMS Click Rate", "SMS Conv Rate", "SMS Unsub Rate",
    ]}

    def _bm_for(flow_name, channel, metric):
        fn = (flow_name or "").lower()
        is_sms = channel == "sms"
        if metric == "open":
            return ALL_BMS["Open Rate (Campaign)"]
        if metric == "click":
            return ALL_BMS["SMS Click Rate"] if is_sms else ALL_BMS["Click Rate (Campaign)"]
        if metric == "ctor":
            return ALL_BMS["CTOR (Campaign)"]
        if metric == "conv":
            if "welcome" in fn:                              return ALL_BMS["Welcome Flow Conv Rate"]
            if "back in stock" in fn or "bis" in fn:         return ALL_BMS["Back In Stock Conv Rate"]
            if "checkout" in fn:                             return ALL_BMS["Abandoned Checkout Conv Rate"]
            if "cart" in fn:                                 return ALL_BMS["Abandoned Cart Conv Rate"]
            return ALL_BMS["SMS Conv Rate"] if is_sms else ALL_BMS["Conversion Rate (Campaign)"]
        if metric == "rpr":
            if "welcome" in fn:    return ALL_BMS["Flow RPR (Welcome)"]
            if "checkout" in fn:   return ALL_BMS["Flow RPR (Checkout)"]
            if "cart" in fn:       return ALL_BMS["Flow RPR (Cart)"]
            return ALL_BMS["RPR (Campaign)"]
        if metric == "unsub":
            return ALL_BMS["SMS Unsub Rate"] if is_sms else ALL_BMS["Unsub Rate (Campaign)"]
        return None

    # 4-tier color (matches module-level _bg): red → yellow → light green → dark green
    BG_RED, BG_YELLOW, BG_LIGHT, BG_DARK = "#FFCDD2", "#FFF9C4", "#C8F7C5", "#81C784"

    # Per-metric format functions
    def _f_pct1(v): return "—" if pd.isna(v) else f"{v*100:.1f}%"
    def _f_pct2(v): return "—" if pd.isna(v) else f"{v*100:.2f}%"
    def _f_pct3(v): return "—" if pd.isna(v) else f"{v*100:.3f}%"
    def _f_dol(v):  return "—" if pd.isna(v) else f"${v:.2f}"

    def _bm_tip(bm, fmt_fn):
        if not bm or bm.get("ind") is None: return ""
        return (f'<span class="bm-tip">'
                f'<span class="bm-tip-hdr">Industry &middot; Good &middot; Great</span>'
                f'<span class="bm-tip-vals">{fmt_fn(bm["ind"])} | {fmt_fn(bm["good"])} | {fmt_fn(bm["great"])}</span>'
                f'</span>')

    def _bm_cell(value, bm, fmt_fn, lower_better=False, sep=False, bold=False):
        """Grid cell with hover tooltip showing benchmark, colored by benchmark."""
        if value is None or pd.isna(value):
            bg, val_html, tip = "", "—", ""
        else:
            bg = _bg(value, bm["ind"], bm["good"], bm["great"], lower_better=lower_better) if bm else ""
            val_html = fmt_fn(value)
            tip = _bm_tip(bm, fmt_fn)
        s = "border-right:3px solid rgba(0,0,0,0.12);" if sep else ""
        bg_s = f"background:{bg};" if bg else ""
        fw = "700" if bold else "400"
        return (f'<div class="bm-cell" style="padding:7px 5px;text-align:center;display:flex;'
                f'align-items:center;justify-content:center;position:relative;{bg_s}{s}">'
                f'<span style="font-weight:{fw};">{val_html}</span>{tip}</div>')

    def _bm_td(value, bm, fmt_fn, lower_better=False):
        """Subtable td with hover tooltip showing benchmark."""
        if value is None or pd.isna(value):
            return '<td style="padding:5px 6px;text-align:center;">—</td>'
        bg   = _bg(value, bm["ind"], bm["good"], bm["great"], lower_better=lower_better) if bm else ""
        bg_s = f"background:{bg};" if bg else ""
        tip  = _bm_tip(bm, fmt_fn)
        return (f'<td class="bm-cell" style="padding:5px 6px;text-align:center;position:relative;{bg_s}">'
                f'<span style="font-weight:600;">{fmt_fn(value)}</span>{tip}</td>')

    # ── KPI strip (computed from totals over selected window) ───────────────
    flow_count       = fm["Flow ID"].nunique()
    months_count     = fm["Month"].dt.to_period("M").nunique()
    f_total_rev      = fm["Revenue"].sum()
    f_avg_mo_rev     = fm.groupby(fm["Month"].dt.to_period("M"))["Revenue"].sum().mean() if months_count else 0
    f_total_recip    = fm["Recipients"].sum()
    f_total_deliv    = fm["Delivered"].sum()
    f_total_opens    = fm["Unique Opens"].sum()
    f_total_clicks   = fm["Unique Clicks"].sum()
    f_total_conv     = fm["Unique Conversions"].sum()
    f_total_unsubs   = fm["Unsubscribes"].sum()

    f_rpr   = (f_total_rev    / f_total_recip) if f_total_recip else 0
    f_open  = (f_total_opens  / f_total_deliv) if f_total_deliv else 0
    f_click = (f_total_clicks / f_total_deliv) if f_total_deliv else 0
    f_conv  = (f_total_conv   / f_total_deliv) if f_total_deliv else 0
    f_unsub = (f_total_unsubs / f_total_recip) if f_total_recip else 0

    flow_rfmt = fmt_rev_consistent(pd.Series([f_total_rev, f_avg_mo_rev]))

    f_strip = (
        '<div class="kpi-group-wrap">'
        + kpi_group("Volume",
            kpi_cell("Active Flows", f"{flow_count:,}") +
            kpi_cell("Months in Period", f"{months_count:,}"))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Financials",
            kpi_cell("Revenue", flow_rfmt(f_total_rev)) +
            kpi_cell("Avg Monthly Rev", flow_rfmt(f_avg_mo_rev)) +
            kpi_cell("Avg RPR", f"${f_rpr:.2f}"))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Performance",
            kpi_cell("Open Rate", "—" if sel_fch == "SMS" else fmt_pct(f_open)) +
            kpi_cell("Click Rate", fmt_pct(f_click)) +
            kpi_cell("Conv. Rate", fmt_pct(f_conv)))
        + '<div class="kpi-group-divider"></div>'
        + kpi_group("Issues", kpi_cell("Unsub Rate", fmt_pct(f_unsub), issue=True))
        + '</div>'
    )
    st.markdown(f_strip, unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Revenue over time ────────────────────────────────────────────────────
    st.markdown("<h2>Flow Revenue Over Time</h2>", unsafe_allow_html=True)
    rev_ts = (fm.groupby(fm["Month"].dt.to_period("M"))["Revenue"]
              .sum().reset_index())
    rev_ts["Month"] = rev_ts["Month"].dt.to_timestamp()
    rev_ts = rev_ts.sort_values("Month")

    fig_frev = go.Figure()
    fig_frev.add_trace(go.Bar(x=rev_ts["Month"], y=rev_ts["Revenue"],
                               marker_color=COLORS["lavender"], name="Revenue",
                               marker_line_color=COLORS["black"], marker_line_width=1))
    fig_frev.update_layout(**plot_theme(height=280),
                            yaxis_tickprefix="$", xaxis_tickformat="%b %Y", bargap=0.3)
    st.plotly_chart(fig_frev, use_container_width=True)

    # ── Engagement rates over time ───────────────────────────────────────────
    st.markdown("<h2>Flow Engagement Rates Over Time</h2>", unsafe_allow_html=True)
    f_rate_cols = [c for c in ["Open Rate","Click Rate","Conversion Rate"]
                   if c in fm.columns and not (c == "Open Rate" and sel_fch == "SMS")]
    if f_rate_cols:
        rates_ts = (fm.groupby(fm["Month"].dt.to_period("M"))[f_rate_cols]
                    .mean().reset_index())
        rates_ts["Month"] = rates_ts["Month"].dt.to_timestamp()
        rates_ts = rates_ts.sort_values("Month")
        fig_frates = go.Figure()
        for col, color in zip(f_rate_cols, [COLORS["black"], COLORS["lavender"], COLORS["lime"]]):
            fig_frates.add_trace(go.Scatter(x=rates_ts["Month"], y=rates_ts[col]*100,
                                             mode="lines+markers", name=col.replace(" Rate",""),
                                             line=dict(color=color, width=2), marker=dict(size=5)))
        fig_frates.update_layout(**plot_theme(height=260),
                                  yaxis_ticksuffix="%", xaxis_tickformat="%b %Y")
        st.plotly_chart(fig_frates, use_container_width=True)

    # ── Performance by Flow (expandable table) ───────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<h2>Performance by Flow</h2>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;color:#666;'
        f'margin:-0.5rem 0 1rem;">Click any flow to see per-message performance. '
        f'Top-level metrics summarize <b>{period_label}</b>; message rows are a 90-day snapshot.</p>',
        unsafe_allow_html=True,
    )

    # ── Flow groupings (broader types) ───────────────────────────────────────
    FLOW_GROUPS = {
        "Welcome":                       ["F001", "F002"],
        "Abandonment":                   ["F003", "F004", "F005", "F006", "F007"],
        "Post-purchase":                 ["F009", "F015", "F010", "F011", "F012", "F013"],
        "Appointments & Cancellations":  ["F016", "F017", "F018", "F019", "F020", "F021", "F022", "F023"],
        "Winback":                       ["F028", "F029"],
        "Back in stock":                 ["F008"],
        "Birthday & Anniversary":        ["F014", "F030"],
        "Other":                         ["F024", "F025", "F026", "F027"],
    }
    flow_to_group   = {fid: g for g, fids in FLOW_GROUPS.items() for fid in fids}
    group_order_idx = {g: i for i, g in enumerate(FLOW_GROUPS)}
    fm["Group"] = fm["Flow ID"].map(flow_to_group).fillna("Other")

    flow_perf = (
        fm.groupby(["Flow ID","Flow Name","Trigger Type","# Messages","Channel"], as_index=False)
          .agg(Recipients=("Recipients","sum"),
               Delivered=("Delivered","sum"),
               Opens=("Unique Opens","sum"),
               Clicks=("Unique Clicks","sum"),
               Conversions=("Unique Conversions","sum"),
               Revenue=("Revenue","sum"),
               Unsubs=("Unsubscribes","sum"))
    )
    flow_perf["Open Rate"]  = flow_perf["Opens"]       / flow_perf["Delivered"].replace(0, pd.NA)
    flow_perf["Click Rate"] = flow_perf["Clicks"]      / flow_perf["Delivered"].replace(0, pd.NA)
    flow_perf["CTOR"]       = flow_perf["Clicks"]      / flow_perf["Opens"].replace(0, pd.NA)
    flow_perf["Conv Rate"]  = flow_perf["Conversions"] / flow_perf["Delivered"].replace(0, pd.NA)
    flow_perf["RPR"]        = flow_perf["Revenue"]     / flow_perf["Recipients"].replace(0, pd.NA)
    flow_perf["Unsub Rate"] = flow_perf["Unsubs"]      / flow_perf["Recipients"].replace(0, pd.NA)
    flow_perf["Group"]      = flow_perf["Flow ID"].map(flow_to_group).fillna("Other")
    flow_perf["_g"]         = flow_perf["Group"].map(group_order_idx).fillna(99)
    flow_perf = flow_perf.sort_values(["_g", "Recipients"], ascending=[True, False])

    # Group-level weighted aggregation (sum/sum, not mean of rates)
    group_agg = (
        fm.groupby("Group", as_index=False).agg(
            Recipients=("Recipients","sum"),
            Delivered=("Delivered","sum"),
            Opens=("Unique Opens","sum"),
            Clicks=("Unique Clicks","sum"),
            Conversions=("Unique Conversions","sum"),
            Revenue=("Revenue","sum"),
            Unsubs=("Unsubscribes","sum"),
            NumFlows=("Flow ID","nunique"),
        )
    )
    # Email-only delivered for accurate open rate (SMS has no opens)
    fm_email = fm[fm["Channel"] == "email"]
    if not fm_email.empty:
        email_deliv = fm_email.groupby("Group", as_index=False).agg(EmailDelivered=("Delivered","sum"))
    else:
        email_deliv = pd.DataFrame({"Group": [], "EmailDelivered": []})
    group_perf = group_agg.merge(email_deliv, on="Group", how="left")
    group_perf["EmailDelivered"] = group_perf["EmailDelivered"].fillna(0)

    group_perf["Open Rate"]  = group_perf["Opens"]       / group_perf["EmailDelivered"].replace(0, pd.NA)
    group_perf["Click Rate"] = group_perf["Clicks"]      / group_perf["Delivered"].replace(0, pd.NA)
    group_perf["CTOR"]       = group_perf["Clicks"]      / group_perf["Opens"].replace(0, pd.NA)
    group_perf["Conv Rate"]  = group_perf["Conversions"] / group_perf["Delivered"].replace(0, pd.NA)
    group_perf["RPR"]        = group_perf["Revenue"]     / group_perf["Recipients"].replace(0, pd.NA)
    group_perf["Unsub Rate"] = group_perf["Unsubs"]      / group_perf["Recipients"].replace(0, pd.NA)
    group_perf["_g"]         = group_perf["Group"].map(group_order_idx).fillna(99)
    group_perf = group_perf.sort_values("_g")

    # Identity 40% | 8 equal-width metric columns at 7.5% each = 60%
    GCOLS_F = "18% 6% 11% 5% " + " ".join(["7.5%"] * 7) + " auto"

    # Map bg color → text color (matches campaigns tab inner rows)
    _BG_TO_TEXT = {
        "#FFCDD2": "#C0392B",  # red
        "#FFF9C4": "#9A7D00",  # dark yellow
        "#C8F7C5": "#1e7e34",  # light green
        "#81C784": "#145a23",  # dark green
    }
    def _dc(val, bg="", bold=False, sep=False, span=1):
        """Inner data cell — colored text on neutral bg (matches campaigns tab)."""
        txt = _BG_TO_TEXT.get(bg, "#222")
        fw  = "font-weight:700;" if (bg or bold) else "font-weight:400;"
        br  = "border-right:3px solid rgba(0,0,0,0.08);" if sep else ""
        sp  = f"grid-column:span {span};" if span > 1 else ""
        return (f'<div style="padding:5px 4px;text-align:center;font-size:0.73rem;'
                f'display:flex;align-items:center;justify-content:center;'
                f'color:{txt};{fw}{br}{sp}">{val}</div>')

    def _dc_bm(value, bm, fmt_fn, lower_better=False, bold=False, sep=False):
        if pd.isna(value) or value is None:
            return _dc("—", sep=sep)
        bg = _bg(value, bm["ind"], bm["good"], bm["great"], lower_better=lower_better) if bm else ""
        return _dc(fmt_fn(value), bg=bg, bold=bold, sep=sep)

    def _msg_rows(flow_id, flow_name, parent_channel):
        """Render messages as grid rows aligned with parent — colored TEXT, neutral bg."""
        sub = fmsg[fmsg["Flow ID"] == flow_id].copy()
        if sub.empty:
            return ("<div style='padding:10px 16px;font-size:0.75rem;color:#888;"
                    "background:#fafafa;'>No message-level data available.</div>")
        sub = sub.sort_values("Step #")

        bm_open  = _bm_for(flow_name, parent_channel, "open")
        bm_click = _bm_for(flow_name, parent_channel, "click")
        bm_conv  = _bm_for(flow_name, parent_channel, "conv")
        bm_rpr   = _bm_for(flow_name, parent_channel, "rpr")

        rows = ""
        for _, m in sub.iterrows():
            ch         = m["Channel"] if pd.notna(m.get("Channel")) else parent_channel
            recipients = m["Recipients 90d"] if pd.notna(m["Recipients 90d"]) else 0
            rev        = m["Revenue"] if pd.notna(m["Revenue"]) else 0
            open_rate  = None if (ch == "sms" or pd.isna(m.get("Open Rate"))) else m["Open Rate"]
            step_badge = (f'<span style="background:#dadada;color:#222;border-radius:50%;'
                          f'width:16px;height:16px;display:inline-flex;align-items:center;'
                          f'justify-content:center;font-size:0.58rem;font-weight:700;'
                          f'margin-right:6px;flex-shrink:0;">{int(m["Step #"])}</span>')
            name_html = (
                f'<div style="padding:5px 8px 5px 26px;display:flex;align-items:center;'
                f'min-width:0;grid-column:span 4;">'
                f'{step_badge}'
                f'<span class="clamp2" style="font-size:0.72rem;line-height:1.25;color:#222;">'
                f'{m["Message Name"]}</span></div>'
            )
            rows += (
                f'<div class="msg-row" style="display:grid;grid-template-columns:{GCOLS_F};'
                f'align-items:stretch;border-bottom:1px solid #ececec;background:#fafafa;'
                f'min-height:34px;">'
                + name_html
                + _dc(f'{recipients/1e3:.0f}K')
                + _dc(f'${rev/1e3:.1f}K')
                + _dc_bm(m["RPR"], bm_rpr, _f_dol, sep=True)
                + _dc_bm(open_rate, bm_open, _f_pct1)
                + _dc_bm(m["Click Rate"], bm_click, _f_pct2, bold=True)
                + _dc("—")
                + _dc_bm(m["Conversion Rate"], bm_conv, _f_pct2, sep=True)
                + _dc("—")
                + '</div>'
            )
        return rows

    def _group_header(g):
        n_flows = int(g["NumFlows"])
        recip_m = (g['Recipients']/1e6) if g['Recipients'] else 0
        rev_m   = (g['Revenue']/1e6) if g['Revenue'] else 0
        cell_st = ("padding:8px 5px;display:flex;align-items:center;justify-content:center;"
                   "font-weight:700;color:#000;font-size:0.78rem;")
        return f"""
        <div class="group-header" style="display:grid;grid-template-columns:{GCOLS_F};
                    background:#ebebeb;border-top:1px solid #bbb;border-bottom:1px solid #bbb;
                    border-left:4px solid #caf30b;min-height:40px;align-items:stretch;">
          <div style="padding:9px 10px;display:flex;align-items:center;
                      grid-column:span 4;border-right:2px solid rgba(0,0,0,0.15);">
            <span style="font-family:'Barlow Condensed',sans-serif;font-size:0.92rem;
                         font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#000;">
              {g['Group']}</span>
            <span style="margin-left:10px;font-size:0.62rem;font-weight:500;color:#666;
                         font-family:'Barlow',sans-serif;">
              {n_flows} flow{'s' if n_flows != 1 else ''}
            </span>
          </div>
          <div style="{cell_st}">{f'{recip_m:.1f}M' if recip_m else '—'}</div>
          <div style="{cell_st}">{f'${rev_m:.1f}M' if rev_m else '—'}</div>
          <div style="{cell_st}border-right:2px solid rgba(0,0,0,0.15);">{_f_dol(g['RPR'])}</div>
          <div style="{cell_st}">{_f_pct1(g['Open Rate'])}</div>
          <div style="{cell_st}">{_f_pct2(g['Click Rate'])}</div>
          <div style="{cell_st}">{_f_pct1(g['CTOR'])}</div>
          <div style="{cell_st}border-right:2px solid rgba(0,0,0,0.15);">{_f_pct2(g['Conv Rate'])}</div>
          <div style="{cell_st}">{_f_pct2(g['Unsub Rate'])}</div>
        </div>"""

    detail_rows_html_f = ""
    for _, gp in group_perf.iterrows():
        flows_in_group = flow_perf[flow_perf["Group"] == gp["Group"]]
        if flows_in_group.empty:
            continue
        detail_rows_html_f += _group_header(gp)

        for _, r in flows_in_group.iterrows():
            ch         = r["Channel"]
            fname      = r["Flow Name"]
            recipients = r["Recipients"] if pd.notna(r["Recipients"]) else 0
            rev        = r["Revenue"]    if pd.notna(r["Revenue"]) else 0
            open_v     = None if (ch == "sms" or pd.isna(r["Open Rate"])) else r["Open Rate"]

            bm_open  = _bm_for(fname, ch, "open")
            bm_click = _bm_for(fname, ch, "click")
            bm_ctor  = _bm_for(fname, ch, "ctor")
            bm_conv  = _bm_for(fname, ch, "conv")
            bm_rpr   = _bm_for(fname, ch, "rpr")
            bm_unsub = _bm_for(fname, ch, "unsub")

            flow_name_html = (
                f'<div style="padding:5px 5px 5px 14px;display:flex;align-items:center;min-width:0;">'
                f'<span class="toggle-icon" style="flex-shrink:0;"></span>'
                f'<span class="clamp2" style="font-weight:600;font-size:0.72rem;line-height:1.25;">'
                f'{fname}</span></div>'
            )

            detail_rows_html_f += f"""
            <details class="perf-row" style="border-bottom:1px solid #e8e8e8;">
              <summary style="cursor:pointer;display:block;">
                <div class="row-grid" style="display:grid;grid-template-columns:{GCOLS_F};
                            align-items:stretch;font-size:0.8rem;min-height:40px;">
                  {flow_name_html}
                  {_cell(_pill(ch), align="left")}
                  {_cell(r["Trigger Type"], align="left")}
                  {_cell(str(int(r["# Messages"])), sep=True)}
                  {_cell(f'{recipients/1e6:.1f}M')}
                  {_cell(f'${rev/1e6:.1f}M')}
                  {_bm_cell(r["RPR"],        bm_rpr,   _f_dol,  sep=True)}
                  {_bm_cell(open_v,          bm_open,  _f_pct1)}
                  {_bm_cell(r["Click Rate"], bm_click, _f_pct2, bold=True)}
                  {_bm_cell(r["CTOR"],       bm_ctor,  _f_pct1)}
                  {_bm_cell(r["Conv Rate"],  bm_conv,  _f_pct2, sep=True)}
                  {_bm_cell(r["Unsub Rate"], bm_unsub, _f_pct2, lower_better=True)}
                </div>
              </summary>
              <div style="background:#fafafa;border-top:1px solid #ddd;">
                <div style="padding:6px 26px 4px;font-family:'Barlow Condensed',sans-serif;
                            font-size:0.62rem;letter-spacing:0.1em;text-transform:uppercase;color:#888;">
                  Messages &middot; 90-day snapshot
                </div>
                {_msg_rows(r["Flow ID"], fname, ch)}
              </div>
            </details>"""

    n_flows = len(flow_perf)
    flow_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800;900&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
      *, *::before, *::after {{ box-sizing:border-box; margin:0; padding:0; }}
      body {{ font-family:'Barlow',sans-serif; background:#fff; font-size:0.82rem; }}
      details summary {{ list-style:none; }}
      details summary::-webkit-details-marker {{ display:none; }}
      .perf-row summary:hover .row-grid {{ background:#fffde0; }}
      .perf-row[open] summary .row-grid {{ background:#fffde0; }}
      .perf-row[open] summary .toggle-icon::before {{ content:"▼"; }}
      .toggle-icon::before {{ content:"▶"; color:#aaa; font-size:0.6rem; margin-right:5px; }}
      .legend-pill {{ display:inline-flex; align-items:center; gap:5px; margin-right:14px;
                      font-size:0.65rem; color:#444; font-family:'Barlow',sans-serif;
                      white-space:nowrap; }}
      .legend-swatch {{ width:11px; height:11px; border-radius:3px; border:1px solid #00000022;
                        display:inline-block; flex-shrink:0; }}
      .bm-cell {{ position:relative; }}
      .bm-tip {{
        visibility:hidden; opacity:0;
        position:absolute; bottom:calc(100% + 6px); left:50%;
        transform:translateX(-50%);
        background:#1a1a1a; color:#fff;
        padding:6px 10px; border-radius:5px;
        white-space:nowrap; pointer-events:none;
        z-index:9999; transition:opacity 0.12s ease-out;
        display:flex; flex-direction:column; align-items:center; gap:2px;
        box-shadow:0 3px 10px rgba(0,0,0,0.18);
      }}
      .bm-tip-hdr {{ font-family:'Barlow Condensed',sans-serif; font-size:0.58rem;
                     letter-spacing:0.1em; text-transform:uppercase; color:#feee35; }}
      .bm-tip-vals {{ font-family:'Barlow',sans-serif; font-size:0.72rem; font-weight:600;
                      font-feature-settings:'tnum'; }}
      .bm-tip::after {{
        content:""; position:absolute; top:100%; left:50%; margin-left:-5px;
        border:5px solid transparent; border-top-color:#1a1a1a;
      }}
      .bm-cell:hover .bm-tip {{ visibility:visible; opacity:1; }}
      .clamp2 {{
        display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
        overflow:hidden; text-overflow:ellipsis; word-break:break-word;
      }}
      .msg-row:hover {{ background:#eee !important; }}
    </style></head><body>
    <div style="border:2px solid #000;border-radius:12px;overflow:hidden;">
      <div style="padding:7px 12px;background:#f7f7f7;border-bottom:1px solid #ddd;
                  display:flex;flex-wrap:wrap;align-items:center;row-gap:4px;">
        <span style="font-family:'Barlow Condensed',sans-serif;font-size:0.65rem;
                     letter-spacing:0.1em;text-transform:uppercase;color:#666;
                     margin-right:14px;">Color vs. benchmarks</span>
        <span class="legend-pill"><span class="legend-swatch" style="background:{BG_RED};"></span>Below industry</span>
        <span class="legend-pill"><span class="legend-swatch" style="background:{BG_YELLOW};"></span>Industry → Good</span>
        <span class="legend-pill"><span class="legend-swatch" style="background:{BG_LIGHT};"></span>Good → Great</span>
        <span class="legend-pill"><span class="legend-swatch" style="background:{BG_DARK};"></span>Above great</span>
        <span style="margin-left:18px;font-size:0.62rem;color:#555;font-family:'Barlow',sans-serif;">
          Hover any metric to see <b>Industry | Good | Great</b> &middot; benchmarks vary by flow type
        </span>
      </div>
      <div style="display:grid;grid-template-columns:40% 20.5% 24.5% auto;background:#000;color:#feee35;">
        <div style="padding:9px 10px;font-family:'Barlow Condensed',sans-serif;font-size:0.72rem;
                    letter-spacing:0.1em;text-transform:uppercase;border-right:3px solid #333;">
          &#9660; Click any flow to expand
        </div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;
                    border-right:3px solid #333;">&#x24; Financials</div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;
                    border-right:3px solid #feee35;">&#9650; Performance</div>
        <div style="padding:9px 10px;text-align:center;font-family:'Barlow Condensed',sans-serif;
                    font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;">&#9888; Issues</div>
      </div>
      <div style="display:grid;grid-template-columns:{GCOLS_F};background:#222;color:#fff;font-size:0.67rem;">
        <div style="padding:6px 9px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;">Flow</div>
        <div style="padding:6px 6px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;">Channel</div>
        <div style="padding:6px 6px;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.08em;text-transform:uppercase;">Trigger</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #444;"># Msgs</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Recipients</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Revenue</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #555;">RPR</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Open Rate</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Click Rate</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">CTOR</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;border-right:3px solid #555;">Conv. Rate</div>
        <div style="padding:6px 6px;text-align:center;font-family:'Barlow Condensed',sans-serif;letter-spacing:0.07em;text-transform:uppercase;">Unsub Rate</div>
      </div>
      {detail_rows_html_f}
    </div></body></html>"""
    n_groups = len(group_perf)
    components.html(flow_html, height=n_flows * 44 + n_groups * 42 + 220, scrolling=True)


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTS & STUDIOS TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_ps:
    product_df, studio_df = load_product_studio()

    # ── Quartile-tinted cell helper ─────────────────────────────────────────
    # Soft 4-tier palette: bottom = warm/pink, top = cool/green. Text always black.
    TIER_BG = ["#FBE5E5", "#FFF4D6", "#E8F5D0", "#CDEBC0"]

    def _quartile_bg(val, vals, lower_better=False):
        if pd.isna(val):
            return "#FAFAFA"
        clean = pd.Series(vals).dropna()
        if len(clean) < 4:
            return COLORS["white"]
        q1, q2, q3 = clean.quantile([0.25, 0.5, 0.75])
        if lower_better:
            if val <= q1: return TIER_BG[3]
            if val <= q2: return TIER_BG[2]
            if val <= q3: return TIER_BG[1]
            return TIER_BG[0]
        if val <= q1: return TIER_BG[0]
        if val <= q2: return TIER_BG[1]
        if val <= q3: return TIER_BG[2]
        return TIER_BG[3]

    def _fmt_pct_t(v): return "—" if pd.isna(v) else f"{v*100:.1f}%"
    def _fmt_dol_t(v): return "—" if pd.isna(v) else f"${v:.2f}"
    def _fmt_int_t(v): return "—" if pd.isna(v) else f"{int(v):,}"
    def _fmt_rev_t(v):
        if pd.isna(v): return "—"
        return f"${v/1e6:.1f}M" if v >= 1_000_000 else f"${v/1e3:.1f}K"

    def _render_perf_table(df, label_col, label_header, sort_col, metric_specs):
        """metric_specs: list of (col_name, header, fmt_fn, lower_better)."""
        df = df.dropna(subset=[sort_col]).sort_values(sort_col, ascending=False).copy()

        cell_pad  = "padding:9px 14px;"
        label_pad = "padding:9px 16px;"
        header_r = (
            f"font-family:'Barlow',sans-serif;font-size:0.6rem;font-weight:600;"
            f"letter-spacing:0.08em;text-transform:uppercase;color:{COLORS['muted']};"
            f"background:{COLORS['offwhite']};border-bottom:1px solid {COLORS['border']};"
            f"text-align:right;{cell_pad}"
        )
        header_l = header_r.replace("text-align:right;", "text-align:left;")

        head = f'<th style="{header_l}">{label_header}</th>'
        for _, hdr, _, _ in metric_specs:
            head += f'<th style="{header_r}">{hdr}</th>'

        rows = []
        for i, (_, r) in enumerate(df.iterrows()):
            row_bg = COLORS["white"] if i % 2 == 0 else COLORS["offwhite"]
            cells = (f'<td style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;'
                     f'font-weight:600;color:{COLORS["black"]};background:{row_bg};'
                     f'{label_pad}border-bottom:1px solid {COLORS["border"]};">'
                     f'{r[label_col]}</td>')
            for col, _, fmt_fn, lower_better in metric_specs:
                val = r[col]
                bg = _quartile_bg(val, df[col], lower_better=lower_better)
                cells += (f'<td style="font-family:\'Barlow\',sans-serif;'
                          f'font-size:0.73rem;font-weight:600;color:{COLORS["black"]};'
                          f'background:{bg};text-align:right;{cell_pad}'
                          f'border-bottom:1px solid {COLORS["border"]};">'
                          f'{fmt_fn(val)}</td>')
            rows.append(f"<tr>{cells}</tr>")

        table = (
            f'<table style="width:100%;border-collapse:collapse;'
            f'border:1px solid {COLORS["border"]};border-radius:8px;overflow:hidden;'
            f'margin-bottom:0.4rem;">'
            f'<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody>'
            f'</table>'
        )
        st.markdown(table, unsafe_allow_html=True)

    def _legend(extra_note=""):
        labels = ["Bottom 25%", "25–50%", "50–75%", "Top 25%"]
        chips = "".join(
            f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'margin-right:14px;font-family:Barlow,sans-serif;font-size:0.7rem;'
            f'color:{COLORS["muted"]};">'
            f'<span style="display:inline-block;width:14px;height:14px;'
            f'background:{TIER_BG[i]};border:1px solid {COLORS["border"]};'
            f'border-radius:3px;"></span>{labels[i]}</span>'
            for i in range(4)
        )
        note = (f'<span style="font-family:Barlow,sans-serif;font-size:0.7rem;'
                f'color:{COLORS["muted"]};margin-left:auto;font-style:italic;">'
                f'{extra_note}</span>' if extra_note else "")
        st.markdown(
            f'<div style="display:flex;align-items:center;flex-wrap:wrap;'
            f'margin:0.25rem 0 0.6rem 0;">{chips}{note}</div>',
            unsafe_allow_html=True,
        )

    # ── Build aggregated dataframes ────────────────────────────────────────
    # Products: Open/Click from Campaigns by Primary Product;
    #          Sends/Conv/Rev/Returns from Product Performance sheet.
    cdf = campaigns_df.dropna(subset=["Primary Product"]).copy()
    prod_oc = (cdf.groupby("Primary Product").agg(
        _Opens=("Unique Opens", "sum"),
        _Clicks=("Unique Clicks", "sum"),
        _Delivered=("Delivered", "sum"),
    ).reset_index())
    prod_oc["Open Rate"]  = prod_oc["_Opens"]  / prod_oc["_Delivered"].replace(0, pd.NA)
    prod_oc["Click Rate"] = prod_oc["_Clicks"] / prod_oc["_Delivered"].replace(0, pd.NA)

    pdf = product_df.dropna(subset=["Product Theme"]).copy()
    prod_cr = (pdf.groupby("Product Theme").agg(
        Sends=("Emails Sent", "sum"),
        _Conv=("Conversions", "sum"),
        Revenue=("Revenue", "sum"),
        ReturnRate=("Return Rate", "mean"),
    ).reset_index().rename(columns={"Product Theme": "Primary Product"}))
    prod_cr["Conv Rate"] = prod_cr["_Conv"]    / prod_cr["Sends"].replace(0, pd.NA)
    prod_cr["RPR"]       = prod_cr["Revenue"]  / prod_cr["Sends"].replace(0, pd.NA)

    products = prod_cr.merge(
        prod_oc[["Primary Product", "Open Rate", "Click Rate"]],
        on="Primary Product", how="left",
    )

    # Studios: everything from Studio Performance sheet
    sdf = studio_df.dropna(subset=["Studio"]).copy()
    studios = (sdf.groupby("Studio").agg(
        Sends=("Email Sends", "sum"),
        _Opens=("Opens", "sum"),
        _Clicks=("Clicks", "sum"),
        _Conv=("Ecom Conversions", "sum"),
        Revenue=("Ecom Revenue", "sum"),
        Appts=("Appts Completed", "sum"),
    ).reset_index())
    studios["Open Rate"]  = studios["_Opens"]  / studios["Sends"].replace(0, pd.NA)
    studios["Click Rate"] = studios["_Clicks"] / studios["Sends"].replace(0, pd.NA)
    studios["Conv Rate"]  = studios["_Conv"]   / studios["Sends"].replace(0, pd.NA)
    studios["RPR"]        = studios["Revenue"] / studios["Sends"].replace(0, pd.NA)

    # ── Products section ────────────────────────────────────────────────────
    st.markdown("<h2>Product Performance</h2>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-family:Barlow,sans-serif;font-size:0.78rem;'
        f'color:{COLORS["muted"]};margin-bottom:0.4rem;">'
        f'Sorted by revenue. Cell shading shows quartile rank within each metric column.'
        f'</div>', unsafe_allow_html=True)
    _legend("Open & Click from campaigns by Primary Product · all other metrics from Product Performance sheet")

    _render_perf_table(
        products,
        label_col="Primary Product",
        label_header="Product",
        sort_col="Revenue",
        metric_specs=[
            ("Sends",      "Sends",       _fmt_int_t, False),
            ("Open Rate",  "Open Rate",   _fmt_pct_t, False),
            ("Click Rate", "Click Rate",  _fmt_pct_t, False),
            ("Conv Rate",  "Conv Rate",   _fmt_pct_t, False),
            ("RPR",        "RPR",         _fmt_dol_t, False),
            ("Revenue",    "Revenue",     _fmt_rev_t, False),
            ("ReturnRate", "Return Rate", _fmt_pct_t, True),
        ],
    )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Studios section ─────────────────────────────────────────────────────
    st.markdown("<h2>Studio Performance</h2>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-family:Barlow,sans-serif;font-size:0.78rem;'
        f'color:{COLORS["muted"]};margin-bottom:0.4rem;">'
        f'Sorted by revenue. Cell shading shows quartile rank within each metric column.'
        f'</div>', unsafe_allow_html=True)
    _legend("All metrics from studio-level email sends across all months")

    _render_perf_table(
        studios,
        label_col="Studio",
        label_header="Studio",
        sort_col="Revenue",
        metric_specs=[
            ("Sends",      "Sends",      _fmt_int_t, False),
            ("Open Rate",  "Open Rate",  _fmt_pct_t, False),
            ("Click Rate", "Click Rate", _fmt_pct_t, False),
            ("Conv Rate",  "Conv Rate",  _fmt_pct_t, False),
            ("RPR",        "RPR",        _fmt_dol_t, False),
            ("Revenue",    "Revenue",    _fmt_rev_t, False),
            ("Appts",      "Appts",      _fmt_int_t, False),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
# CHANNELS TAB — Email vs SMS performance + cross-channel comparison
# ══════════════════════════════════════════════════════════════════════════════
with tab_channels:
    df_ch = campaigns_df.copy()

    # ── Filters (Year + Category) ────────────────────────────────────────────
    cf1, cf2, _ = st.columns([1.5, 1.5, 6])
    years_ch = sorted(df_ch["Send Date"].dt.year.dropna().unique().astype(int).tolist(),
                      reverse=True)
    cat_opts_ch = ["All Categories"] + sorted(df_ch["Category"].dropna().unique().tolist())
    with cf1: sel_year_ch = st.selectbox("Year", ["All Years"] + [str(y) for y in years_ch], key="ch_yr")
    with cf2: sel_cat_ch  = st.selectbox("Category", cat_opts_ch, key="ch_cat")

    filt_ch = df_ch.copy()
    if sel_year_ch != "All Years":
        filt_ch = filt_ch[filt_ch["Send Date"].dt.year == int(sel_year_ch)]
    if sel_cat_ch != "All Categories":
        filt_ch = filt_ch[filt_ch["Category"] == sel_cat_ch]

    # ── Per-channel weighted aggregates ──────────────────────────────────────
    def _ch_metrics(sub):
        camps = int(len(sub))
        sent  = float(sub["Recipients"].sum())
        deliv = float(sub["Delivered"].sum())
        opens = float(sub["Unique Opens"].sum())
        clk   = float(sub["Unique Clicks"].sum())
        conv  = float(sub["Unique Conversions"].sum())
        rev   = float(sub["Revenue"].sum())
        uns   = float(sub["Unsubscribes"].sum())
        return {
            "campaigns":  camps,
            "sent":       sent,
            "delivered":  deliv,
            "revenue":    rev,
            "rpr":        (rev / deliv) if deliv else 0.0,
            "aov":        (rev / conv)  if conv else 0.0,
            "del_rate":   (deliv / sent) if sent else 0.0,
            "open_rate":  (opens / deliv) if deliv else 0.0,
            "click_rate": (clk / deliv)  if deliv else 0.0,
            "conv_rate":  (conv / deliv) if deliv else 0.0,
            "unsub_rate": (uns / deliv)  if deliv else 0.0,
        }

    em_m  = _ch_metrics(filt_ch[filt_ch["Channel"] == "email"])
    sms_m = _ch_metrics(filt_ch[filt_ch["Channel"] == "sms"])
    all_m = _ch_metrics(filt_ch)

    rfmt_ch = fmt_rev_consistent(pd.Series([em_m["revenue"], sms_m["revenue"], all_m["revenue"]]))

    def _vol(n):
        if n >= 1_000_000: return f"{n/1e6:.1f}M"
        if n >= 1_000:     return f"{n/1e3:.1f}K"
        return f"{n:,.0f}"

    def _pct_or_dash(v, tracked=True):
        if not tracked: return "—"
        return "—" if (v is None or pd.isna(v)) else f"{v*100:.2f}%"

    def _cmp_arrow(em_v, sms_v, lower_better=False):
        """Return inline winner indicator vs the other channel."""
        if em_v is None or sms_v is None:
            return ""
        if pd.isna(em_v) or pd.isna(sms_v) or (em_v == 0 and sms_v == 0):
            return ""
        higher = em_v if em_v >= sms_v else sms_v
        winner = "email" if em_v >= sms_v else "sms"
        if lower_better:
            winner = "email" if em_v <= sms_v else "sms"
            higher = em_v if em_v <= sms_v else sms_v
        return winner

    # ── Comparison Table (banner up top) ─────────────────────────────────────
    rows = [
        ("Campaigns",       f"{em_m['campaigns']:,}",         f"{sms_m['campaigns']:,}",         f"{all_m['campaigns']:,}",       "count"),
        ("Recipients",      _vol(em_m["sent"]),               _vol(sms_m["sent"]),               _vol(all_m["sent"]),             "count"),
        ("Revenue",         rfmt_ch(em_m["revenue"]),         rfmt_ch(sms_m["revenue"]),         rfmt_ch(all_m["revenue"]),       "money"),
        ("Avg RPR",         f"${em_m['rpr']:.2f}",            f"${sms_m['rpr']:.2f}",            f"${all_m['rpr']:.2f}",          "money"),
        ("AOV",             f"${em_m['aov']:,.0f}",           f"${sms_m['aov']:,.0f}",           f"${all_m['aov']:,.0f}",         "money"),
        ("Delivery Rate",   _pct_or_dash(em_m["del_rate"]),   _pct_or_dash(sms_m["del_rate"]),   _pct_or_dash(all_m["del_rate"]), "pct"),
        ("Open Rate",       _pct_or_dash(em_m["open_rate"]),  "—",                               _pct_or_dash(em_m["open_rate"]), "pct"),
        ("Click Rate",      _pct_or_dash(em_m["click_rate"]), _pct_or_dash(sms_m["click_rate"]), _pct_or_dash(all_m["click_rate"]),"pct"),
        ("Conversion Rate", _pct_or_dash(em_m["conv_rate"]),  _pct_or_dash(sms_m["conv_rate"]),  _pct_or_dash(all_m["conv_rate"]),"pct"),
        ("Unsub Rate",      _pct_or_dash(em_m["unsub_rate"]), _pct_or_dash(sms_m["unsub_rate"]), _pct_or_dash(all_m["unsub_rate"]),"pct"),
    ]

    # Winner highlight per metric (numeric, weighted) — light-green tint on winner cell
    win_keys = {
        "Click Rate":      ("click_rate", False),
        "Conversion Rate": ("conv_rate",  False),
        "Avg RPR":         ("rpr",        False),
        "Revenue":         ("revenue",    False),
        "Delivery Rate":   ("del_rate",   False),
        "Unsub Rate":      ("unsub_rate", True),
    }

    body_rows = ""
    _GREEN_TEXT = "#1e7e34"
    for label, em_s, sms_s, total_s, _kind in rows:
        em_color, sms_color = "#222", "#222"
        em_weight, sms_weight = "400", "400"
        if label in win_keys:
            mkey, lower = win_keys[label]
            em_v, sms_v = em_m[mkey], sms_m[mkey]
            if em_v and sms_v:
                if (em_v <= sms_v) if lower else (em_v >= sms_v):
                    em_color, em_weight = _GREEN_TEXT, "700"
                else:
                    sms_color, sms_weight = _GREEN_TEXT, "700"
        body_rows += (
            '<tr style="border-bottom:1px solid #eee;">'
            f'<td style="padding:6px 12px;font-family:\'Barlow\',sans-serif;'
            f'font-size:0.73rem;font-weight:500;color:#333;">{label}</td>'
            f'<td style="padding:6px 12px;text-align:right;'
            f'font-family:\'Barlow\',sans-serif;font-size:0.73rem;'
            f'font-weight:{em_weight};color:{em_color};">{em_s}</td>'
            f'<td style="padding:6px 12px;text-align:right;'
            f'font-family:\'Barlow\',sans-serif;font-size:0.73rem;'
            f'font-weight:{sms_weight};color:{sms_color};">{sms_s}</td>'
            f'<td style="padding:6px 12px;text-align:right;background:#FAFAFA;'
            f'font-family:\'Barlow\',sans-serif;font-size:0.73rem;'
            f'font-weight:400;color:#444;">{total_s}</td>'
            '</tr>'
        )

    st.markdown(
        f'<div style="border:1px solid {COLORS["border"]};border-radius:8px;'
        f'overflow:hidden;margin-top:0.5rem;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="background:#000;color:#feee35;">'
        f'<th style="padding:8px 12px;text-align:left;font-family:\'Barlow\',sans-serif;'
        f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Metric</th>'
        f'<th style="padding:8px 12px;text-align:right;font-family:\'Barlow\',sans-serif;'
        f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Email</th>'
        f'<th style="padding:8px 12px;text-align:right;font-family:\'Barlow\',sans-serif;'
        f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">SMS</th>'
        f'<th style="padding:8px 12px;text-align:right;font-family:\'Barlow\',sans-serif;'
        f'font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;background:#1a1a1a;">Combined</th>'
        f'</tr></thead><tbody>{body_rows}</tbody></table></div>'
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.66rem;color:#888;'
        f'margin-top:6px;">Open Rate, CTOR & Spam Rate are not tracked for SMS · '
        f'green text = winning channel on weighted-avg metrics</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Email vs SMS — historical performance by category ───────────────────
    st.markdown("<h2>Email vs. SMS — performance by category</h2>", unsafe_allow_html=True)

    ch_comp = (
        filt_ch.groupby(["Category", "Channel"])
        .agg(_Clicks=("Unique Clicks", "sum"),
             _Delivered=("Delivered", "sum"),
             _Conv=("Unique Conversions", "sum"),
             Total_Rev=("Revenue", "sum"),
             Count=("Campaign Name", "count"))
        .reset_index().dropna(subset=["Category"])
    )
    ch_comp["Avg_Click"] = ch_comp["_Clicks"] / ch_comp["_Delivered"].replace(0, pd.NA)
    ch_comp["Avg_Conv"]  = ch_comp["_Conv"]   / ch_comp["_Delivered"].replace(0, pd.NA)
    ch_comp["channel"] = ch_comp["Channel"].str.upper()
    ch_comp = ch_comp.dropna(subset=["Avg_Click"])

    cat_order_ch = (ch_comp.groupby("Category")["Avg_Click"]
                    .mean().sort_values(ascending=False).index.tolist())

    def _short_cat(s, n=18):
        return s if len(s) <= n else s[: n - 1] + "…"

    ch_comp["Cat_Short"] = ch_comp["Category"].apply(_short_cat)
    cat_order_short = [_short_cat(c) for c in cat_order_ch]

    n_cats = len(cat_order_ch)
    chart_height = max(360, 28 * n_cats + 140)

    cc1, cc2 = st.columns(2)
    with cc1:
        fig_ch_click = px.bar(
            ch_comp, x="Cat_Short", y="Avg_Click", color="channel",
            color_discrete_map=CMAP, barmode="group",
            category_orders={"Cat_Short": cat_order_short},
            title="CLICK RATE: EMAIL VS SMS", height=chart_height,
            labels={"Avg_Click": "Avg Click Rate", "channel": "", "Cat_Short": ""},
            hover_data={"Category": True, "Cat_Short": False, "Count": True, "Avg_Click": ":.2%"},
        )
        fig_ch_click.update_layout(**plot_theme(
            margin=dict(l=0, r=10, t=40, b=120),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10, family="Barlow, sans-serif"),
                       automargin=True, showgrid=False, zeroline=False),
            yaxis=dict(tickformat=".1%", tickfont=dict(size=10),
                       gridcolor=COLORS["border"], zeroline=False),
        ))
        fig_ch_click.update_traces(marker_line_width=0.5, marker_line_color="#000")
        st.plotly_chart(fig_ch_click, use_container_width=True)

    with cc2:
        fig_ch_rev = px.bar(
            ch_comp, x="Cat_Short", y="Total_Rev", color="channel",
            color_discrete_map=CMAP, barmode="group",
            category_orders={"Cat_Short": cat_order_short},
            title="TOTAL REVENUE: EMAIL VS SMS", height=chart_height,
            labels={"Total_Rev": "Revenue", "channel": "", "Cat_Short": ""},
            hover_data={"Category": True, "Cat_Short": False, "Count": True, "Total_Rev": ":$,.0f"},
        )
        fig_ch_rev.update_layout(**plot_theme(
            margin=dict(l=0, r=10, t=40, b=120),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10, family="Barlow, sans-serif"),
                       automargin=True, showgrid=False, zeroline=False),
            yaxis=dict(tickformat="$,.2s", tickfont=dict(size=10),
                       gridcolor=COLORS["border"], zeroline=False),
        ))
        fig_ch_rev.update_traces(marker_line_width=0.5, marker_line_color="#000")
        st.plotly_chart(fig_ch_rev, use_container_width=True)

    # ── Conversion Rate by category (extra context) ──────────────────────────
    ch_comp_conv = ch_comp.dropna(subset=["Avg_Conv"]).copy()
    if not ch_comp_conv.empty:
        cat_order_conv = (ch_comp_conv.groupby("Category")["Avg_Conv"]
                          .mean().sort_values(ascending=False).index.tolist())
        cat_order_conv_short = [_short_cat(c) for c in cat_order_conv]
        fig_ch_conv = px.bar(
            ch_comp_conv, x="Cat_Short", y="Avg_Conv", color="channel",
            color_discrete_map=CMAP, barmode="group",
            category_orders={"Cat_Short": cat_order_conv_short},
            title="CONVERSION RATE: EMAIL VS SMS", height=chart_height,
            labels={"Avg_Conv": "Avg Conversion Rate", "channel": "", "Cat_Short": ""},
            hover_data={"Category": True, "Cat_Short": False, "Count": True, "Avg_Conv": ":.2%"},
        )
        fig_ch_conv.update_layout(**plot_theme(
            margin=dict(l=0, r=10, t=40, b=120),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10, family="Barlow, sans-serif"),
                       automargin=True, showgrid=False, zeroline=False),
            yaxis=dict(tickformat=".2%", tickfont=dict(size=10),
                       gridcolor=COLORS["border"], zeroline=False),
        ))
        fig_ch_conv.update_traces(marker_line_width=0.5, marker_line_color="#000")
        st.plotly_chart(fig_ch_conv, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TRACKING TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_track:
    # ── Derived columns ───────────────────────────────────────────────────────
    df_t = campaigns_df.copy()
    df_t["_dow"]        = df_t["Send Date"].dt.day_name()
    df_t["_month_abbr"] = df_t["Send Date"].dt.strftime("%b")
    df_t["_month_num"]  = df_t["Send Date"].dt.month
    df_t["_hour"]       = df_t["Send Date"].dt.hour

    def _tbkt(h):
        if pd.isna(h): return None
        if 6  <= h < 10: return "Morning (6–10am)"
        if 10 <= h < 14: return "Midday (10am–2pm)"
        if 14 <= h < 17: return "Afternoon (2–5pm)"
        if 17 <= h < 21: return "Evening (5–9pm)"
        return None

    df_t["_time_bucket"] = df_t["_hour"].apply(_tbkt)
    _dow_col = "Day of Week" if "Day of Week" in df_t.columns else "_dow"

    if "Subject Line" in df_t.columns:
        df_t["_themes"] = df_t["Subject Line"].fillna("").apply(detect_themes)
    else:
        df_t["_themes"] = [[] for _ in range(len(df_t))]

    # ── Option lists ──────────────────────────────────────────────────────────
    _MOS  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    _MOMAP = {m: i+1 for i, m in enumerate(_MOS)}
    _DAYS  = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    _TIMES = ["Morning (6–10am)","Midday (10am–2pm)","Afternoon (2–5pm)","Evening (5–9pm)"]
    _THEME_OPTS = [n for n, _ in THEME_PATTERNS]
    _TONE_OPTS  = ["No preference","Conversational","Urgent / FOMO","Exclusive / VIP",
                   "Editorial / Aspirational","Playful / Witty"]
    _DESIGN_OPTS = ["No preference","Hero Image","Product Grid","Lifestyle Photography",
                    "GIF / Animation","Text-Only / Minimal"]

    _cat_opts    = sorted(df_t["Category"].dropna().unique().tolist())       if "Category"       in df_t.columns else []
    _prod_opts   = sorted(df_t["Primary Product"].dropna().unique().tolist()) if "Primary Product" in df_t.columns else []
    _studio_opts = sorted(df_t["Primary Studio"].dropna().unique().tolist())  if "Primary Studio"  in df_t.columns else []
    _seg_opts    = sorted([str(s) for s in df_t["Audiences"].dropna().unique() if len(str(s)) < 80]) \
                   if "Audiences" in df_t.columns else []

    # ── Core: filter + compute metrics ───────────────────────────────────────
    def _predict(dframe, mode=None, cats=None, prods=None, studios=None,
                 months=None, days=None, times=None, themes=None):
        f = dframe.copy()
        if mode:
            f = f[f["Channel"].str.upper() == mode.upper()]
        if cats   and "Category"       in f.columns: f = f[f["Category"].isin(cats)]
        if prods  and "Primary Product" in f.columns: f = f[f["Primary Product"].isin(prods)]
        if studios and "Primary Studio" in f.columns: f = f[f["Primary Studio"].isin(studios)]
        if months:
            nums = [_MOMAP[m] for m in months if m in _MOMAP]
            f = f[f["_month_num"].isin(nums)]
        if days:   f = f[f[_dow_col].isin(days)]
        if times:  f = f[f["_time_bucket"].isin(times)]
        if themes and "_themes" in f.columns:
            f = f[f["_themes"].apply(lambda t: any(th in t for th in themes))]
        n = len(f)
        if n == 0: return None
        return {
            "open_rate":  f["Open Rate"].mean()       if "Open Rate"       in f.columns else None,
            "click_rate": f["Click Rate"].mean()      if "Click Rate"      in f.columns else None,
            "conv_rate":  f["Conversion Rate"].mean() if "Conversion Rate" in f.columns else None,
            "unsub_rate": f["Unsub Rate"].mean()      if "Unsub Rate"      in f.columns else None,
            "revenue":    f["Revenue"].mean()         if "Revenue"         in f.columns else None,
            "n": n,
        }

    def _ai_rec(dframe, mode=None):
        f = dframe.copy()
        if mode: f = f[f["Channel"].str.upper() == mode.upper()]
        if len(f) < 5: return None, None
        score = pd.Series(0.0, index=f.index)
        for col, w in [("Open Rate",0.20),("Click Rate",0.25),
                       ("Conversion Rate",0.30),("Revenue",0.30)]:
            if col in f.columns:
                s = f[col].fillna(0); mn, mx = s.min(), s.max()
                if mx > mn: score += ((s - mn)/(mx - mn)) * w
        if "Unsub Rate" in f.columns:
            s = f["Unsub Rate"].fillna(0); mn, mx = s.min(), s.max()
            if mx > mn: score -= ((s - mn)/(mx - mn)) * 0.05
        top = f.assign(_score=score)
        top = top[top["_score"] >= top["_score"].quantile(0.75)]
        recs = {}
        for col, lbl in [("Category","Category"),("Primary Product","Product"),
                         ("Primary Studio","Studio"),(_dow_col,"Day"),("_month_abbr","Month")]:
            if col in top.columns:
                vals = top[col].dropna().value_counts().head(2).index.tolist()
                if vals: recs[lbl] = vals
        # Top copy themes
        if "_themes" in top.columns:
            from collections import Counter
            all_t = [th for tl in top["_themes"] for th in tl if th != "Other"]
            if all_t:
                top_themes = [t for t, _ in Counter(all_t).most_common(2)]
                recs["Copy Theme"] = top_themes
        return recs, _predict(top)

    # ── HTML helpers ──────────────────────────────────────────────────────────
    def _v(v, pct=False):
        try:
            if pd.isna(v): return "—"
        except Exception: return "—"
        return f"{v*100:.1f}%" if pct else fmt_revenue(v)

    def _risk(ur):
        if ur is None or (hasattr(ur, "__float__") and pd.isna(ur)): return "Unknown", COLORS["border"], COLORS["muted"]
        ur = float(ur)
        if ur < 0.002: return "Low",    COLORS["lime"],   COLORS["black"]
        if ur < 0.005: return "Medium", COLORS["warn"],   COLORS["black"]
        return              "High",   COLORS["danger"], "#fff"

    def _perf_card(title, perf, accent, badge_n=None, extra_note=None):
        _wrap = (f'<div style="border:1.5px solid {COLORS["border"]};border-radius:12px;'
                 f'padding:16px;background:{COLORS["white"]};margin-bottom:12px;">')
        _hdr  = (f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.62rem;'
                 f'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;'
                 f'color:{COLORS["muted"]};border-left:3px solid {accent};'
                 f'padding-left:8px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center;">'
                 f'<span>{title}</span>'
                 + (f'<span style="font-size:0.58rem;font-weight:600;color:{COLORS["muted"]};">'
                    f'{badge_n} campaign{"s" if badge_n != 1 else ""}</span>' if badge_n is not None else '')
                 + '</div>')
        if perf is None:
            return (_wrap + _hdr +
                    f'<div style="text-align:center;padding:20px 0;font-family:\'Barlow\',sans-serif;'
                    f'font-size:0.8rem;color:{COLORS["muted"]};">No matching historical campaigns</div></div>')
        rl, rb, rt = _risk(perf.get("unsub_rate"))

        def _row(lbl, val_html, last=False):
            br = "" if last else f"border-bottom:1px solid {COLORS['border']};"
            return (f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:5px 0;{br}">'
                    f'<span style="font-family:\'Barlow\',sans-serif;font-size:0.72rem;'
                    f'color:{COLORS["muted"]};">{lbl}</span>'
                    f'{val_html}</div>')

        def _num(v): return (f'<span style="font-family:\'Barlow Condensed\',sans-serif;'
                             f'font-size:1.15rem;font-weight:800;">{v}</span>')
        def _big(v): return (f'<span style="font-family:\'Barlow Condensed\',sans-serif;'
                             f'font-size:1.3rem;font-weight:800;">{v}</span>')

        rows = (
            _row("Open Rate",  _num(_v(perf.get("open_rate"),  pct=True))) +
            _row("Click Rate", _num(_v(perf.get("click_rate"), pct=True))) +
            _row("Conv. Rate", _num(_v(perf.get("conv_rate"),  pct=True))) +
            _row("Unsub Risk",
                 f'<span style="background:{rb};color:{rt};font-family:\'Barlow Condensed\','
                 f'sans-serif;font-size:0.72rem;font-weight:800;padding:2px 10px;'
                 f'border-radius:50px;">{rl}</span>') +
            _row("Avg Revenue", _big(_v(perf.get("revenue"))), last=True)
        )
        note_html = ""
        if extra_note:
            note_html = (f'<div style="margin-top:8px;font-family:\'Barlow\',sans-serif;'
                         f'font-size:0.65rem;color:{COLORS["muted"]};font-style:italic;">{extra_note}</div>')
        return _wrap + _hdr + rows + note_html + '</div>'

    def _ai_rec_html(recs):
        if not recs:
            return (f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.8rem;'
                    f'color:{COLORS["muted"]};text-align:center;padding:16px 0;">Insufficient data</div>')
        rows = ""
        for lbl, vals in recs.items():
            vstr = " / ".join(str(v) for v in vals[:2])
            rows += (f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
                     f'padding:5px 0;border-bottom:1px solid {COLORS["border"]};">'
                     f'<span style="font-family:\'Barlow\',sans-serif;font-size:0.68rem;font-weight:600;'
                     f'text-transform:uppercase;letter-spacing:0.07em;color:{COLORS["muted"]};">{lbl}</span>'
                     f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.88rem;'
                     f'font-weight:700;max-width:58%;overflow:hidden;text-overflow:ellipsis;'
                     f'white-space:nowrap;">{vstr}</span></div>')
        return (f'<div style="border:1.5px solid {COLORS["lime"]};border-radius:10px;'
                f'padding:14px;background:{COLORS["white"]};">'
                f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.6rem;'
                f'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;color:{COLORS["muted"]};'
                f'border-left:3px solid {COLORS["lime"]};padding-left:8px;margin-bottom:10px;">AI Recommended Settings</div>'
                f'{rows}'
                f'<div style="margin-top:8px;font-family:\'Barlow\',sans-serif;font-size:0.6rem;'
                f'color:{COLORS["muted"]};">Top 25% by open rate, conversion &amp; revenue</div></div>')

    # ── Session state init ────────────────────────────────────────────────────
    if "trk_sel_camp" not in st.session_state:
        st.session_state.trk_sel_camp = None

    # ── SECTION 1: Upcoming Campaigns (from Planning → Plan a Campaign) ────────
    _planned_camps = (
        st.session_state.get("plan_added", []) +
        st.session_state.get("plan_drafts", [])
    )
    # Sort by send_date ascending
    _planned_camps = sorted(
        _planned_camps,
        key=lambda c: c.get("send_date") or date.today()
    )

    st.markdown('<div class="section-label" style="margin-bottom:10px;">Upcoming Campaigns</div>',
                unsafe_allow_html=True)

    _status_colors = {
        "planned": (COLORS["lime"],     COLORS["black"]),
        "draft":   (COLORS["yellow"],   COLORS["black"]),
    }

    def _render_camp_card(camp, col):
        with col:
            is_sel = st.session_state.trk_sel_camp == camp["id"]
            ch   = camp.get("channel", "email")
            ch_bg  = COLORS["black"]  if ch == "email" else COLORS["lavender"]
            ch_txt = COLORS["yellow"] if ch == "email" else COLORS["black"]
            status = camp.get("status", "planned")
            st_bg, st_txt = _status_colors.get(status, ("#eee", "#000"))
            border = f"2px solid {COLORS['yellow']}" if is_sel else f"1px solid {COLORS['border']}"
            shadow = "box-shadow:0 2px 8px rgba(0,0,0,0.10);" if is_sel else ""

            # Audiences: list → first item for display
            auds = camp.get("audiences", [])
            aud_str = auds[0] if auds else "—"

            sd = camp.get("send_date")
            date_str = sd.strftime("%b %d") if sd else "—"

            st.markdown(f"""
            <div style="border:{border};border-radius:10px;padding:10px 12px;
                        background:{COLORS['white']};{shadow}min-height:100px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <span style="background:{ch_bg};color:{ch_txt};padding:2px 8px;border-radius:4px;
                             font-family:'Barlow Condensed',sans-serif;font-size:0.62rem;
                             font-weight:800;letter-spacing:0.05em;">{ch.upper()}</span>
                <span style="background:{st_bg};color:{st_txt};padding:2px 7px;border-radius:4px;
                             font-family:'Barlow',sans-serif;font-size:0.58rem;
                             font-weight:600;">{status.title()}</span>
              </div>
              <div style="font-family:'Barlow Condensed',sans-serif;font-size:0.88rem;font-weight:800;
                          color:{COLORS['black']};line-height:1.25;margin-bottom:6px;
                          overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;
                          -webkit-box-orient:vertical;">{camp.get('name','Untitled')}</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;">
                <span style="font-family:'Barlow',sans-serif;font-size:0.62rem;
                             color:{COLORS['muted']};">📅 {date_str}</span>
                <span style="font-family:'Barlow',sans-serif;font-size:0.62rem;
                             color:{COLORS['muted']};max-width:100%;overflow:hidden;
                             text-overflow:ellipsis;white-space:nowrap;">👥 {aud_str[:30]}</span>
              </div>
            </div>""", unsafe_allow_html=True)

            if st.button("Load →" if not is_sel else "✓ Loaded",
                         key=f"trk_load_{camp['id']}", use_container_width=True):
                cid = camp["id"]
                # Campaign basics
                st.session_state["trk_mode"]    = "Email" if ch == "email" else "SMS"
                st.session_state["trk_cat"]     = [camp["category"]] if camp.get("category") in _cat_opts else []
                prod = camp.get("product", "")
                stu  = camp.get("studio",  "")
                st.session_state["trk_prods"]   = [prod] if prod and prod in _prod_opts   else []
                st.session_state["trk_studios"] = [stu]  if stu  and stu  in _studio_opts else []
                # Timing
                if sd:
                    st.session_state["trk_months"] = [sd.strftime("%b")]
                    st.session_state["trk_days"]   = [sd.strftime("%A")]
                # Audiences: pull from Decisioning state first (most up-to-date),
                # fall back to Plan a Campaign audiences
                d_segs = st.session_state.get("decisioning_state", {}).get(cid, {}).get("segments", [])
                seg_source = d_segs if d_segs else auds
                if seg_source:
                    matched   = [a for a in seg_source if a in _seg_opts]
                    unmatched = [a for a in seg_source if a not in _seg_opts]
                    st.session_state["trk_seg"]          = matched
                    st.session_state["trk_seg_cust_inp"] = ", ".join(unmatched)
                # Copy: detect themes from subject line draft
                subj = camp.get("subject", "").strip()
                if subj:
                    detected = [t for t in detect_themes(subj) if t != "Other" and t in _THEME_OPTS]
                    if detected:
                        st.session_state["trk_themes"] = detected
                # Copy tone: pull from Generation tab if this campaign was last generated
                if st.session_state.get("gen_for_camp_id") == cid:
                    gen_t = st.session_state.get("gen_tone", "")
                    if gen_t:
                        st.session_state["trk_tone_text"] = gen_t
                st.session_state.trk_sel_camp = cid
                st.rerun()

    if not _planned_camps:
        st.info("No campaigns planned yet. Go to **Planning → Plan a Campaign** to add campaigns, then come back here to predict their performance.")
    else:
        # Render in rows of 4
        for _row_start in range(0, len(_planned_camps), 4):
            _row_camps = _planned_camps[_row_start:_row_start + 4]
            _row_cols  = st.columns(len(_row_camps), gap="small")
            for col, camp in zip(_row_cols, _row_camps):
                _render_camp_card(camp, col)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── SECTION 2: Decision playground + Prediction ───────────────────────────
    _hdr_style = (f'font-family:\'Barlow Condensed\',sans-serif;font-size:0.65rem;'
                  f'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;'
                  f'color:{COLORS["muted"]};padding-left:8px;')

    def _group_hdr(label, accent):
        return (f'<div style="{_hdr_style}border-left:3px solid {accent};'
                f'margin-bottom:8px;margin-top:6px;">{label}</div>')

    def _hint(text):
        """Small grey contextual hint shown below a decision field."""
        if not text: return
        st.markdown(
            f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.65rem;'
            f'color:{COLORS["muted"]};margin-top:-6px;margin-bottom:6px;'
            f'padding-left:2px;">✦ {text}</div>',
            unsafe_allow_html=True,
        )

    # Pre-read mode from session state so we can compute hints before widgets render
    _t_mode_pre = st.session_state.get("trk_mode", "Email")
    _cid_pre    = st.session_state.get("trk_sel_camp")
    _loaded_camp = next((c for c in _planned_camps if c["id"] == _cid_pre), None) if _cid_pre else None

    # ── Pre-compute per-field hints from historical data ──────────────────────
    def _top_by(df, group_col, metric, n=2, ascending=False):
        """Return list of top-n values in group_col ranked by metric mean."""
        if group_col not in df.columns or metric not in df.columns:
            return []
        s = df.groupby(group_col)[metric].mean().sort_values(ascending=ascending)
        return s.index[:n].tolist()

    def _top_val(df, group_col, metric, ascending=False):
        """Return (top_name, metric_value) for the best entry."""
        if group_col not in df.columns or metric not in df.columns:
            return None, None
        s = df.groupby(group_col)[metric].mean().sort_values(ascending=ascending)
        if s.empty: return None, None
        return s.index[0], s.iloc[0]

    _hf = df_t[df_t["Channel"].str.upper() == _t_mode_pre.upper()].copy()

    # Category hint
    _best_cat, _best_cat_cr = _top_val(_hf, "Category", "Click Rate")
    _hint_cat = (f"{_best_cat} leads with {_best_cat_cr*100:.1f}% click rate for {_t_mode_pre}"
                 if _best_cat and _best_cat_cr else "")

    # Product hint
    _best_prod, _best_prod_rpr = _top_val(_hf, "Primary Product", "RPR")
    _hint_prod = (f"Highest RPR: {_best_prod} at ${_best_prod_rpr:.2f}/recipient"
                  if _best_prod and _best_prod_rpr else "")

    # Studio hint — pull from loaded campaign + historical
    _hint_studio = ""
    if _loaded_camp and _loaded_camp.get("studio"):
        _stu_name = _loaded_camp["studio"]
        _stu_rows = _hf[_hf.get("Primary Studio", pd.Series(dtype=str)) == _stu_name] \
                    if "Primary Studio" in _hf.columns else pd.DataFrame()
        if not _stu_rows.empty and "Revenue" in _stu_rows.columns:
            _stu_rev = _stu_rows["Revenue"].mean()
            _hint_studio = f"{_stu_name}: ${_stu_rev/1e3:.1f}K avg revenue historically"
        else:
            _best_stu, _best_stu_rev = _top_val(_hf, "Primary Studio", "Revenue")
            if _best_stu:
                _hint_studio = f"Best performing studio: {_best_stu} (${_best_stu_rev/1e3:.1f}K avg rev)"
    else:
        _best_stu, _best_stu_rev = _top_val(_hf, "Primary Studio", "Revenue")
        if _best_stu and _best_stu_rev:
            _hint_studio = f"Best performing: {_best_stu} (${_best_stu_rev/1e3:.1f}K avg revenue)"

    # Segment hint — from Decisioning state if campaign is loaded
    _hint_seg = ""
    if _cid_pre:
        _d_segs = st.session_state.get("decisioning_state", {}).get(_cid_pre, {}).get("segments", [])
        if _d_segs:
            _hint_seg = f"Decisioning has {len(_d_segs)} segment{'s' if len(_d_segs)!=1 else ''} configured: {', '.join(_d_segs[:2])}" + (" …" if len(_d_segs) > 2 else "")
    if not _hint_seg and _loaded_camp:
        auds_preview = _loaded_camp.get("audiences", [])
        if auds_preview:
            _hint_seg = f"From Planning: {', '.join(auds_preview[:2])}" + (" …" if len(auds_preview) > 2 else "")

    # Month hint — top 2 by click rate
    _best_mos = _top_by(_hf, "_month_abbr", "Click Rate", n=2)
    _hint_month = f"Best historically: {' / '.join(_best_mos)}" if _best_mos else ""
    # If campaign loaded, also note its planned month
    if _loaded_camp and _loaded_camp.get("send_date"):
        _camp_mo = _loaded_camp["send_date"].strftime("%b")
        _mo_row = _hf[_hf["_month_abbr"] == _camp_mo]
        if not _mo_row.empty and "Click Rate" in _mo_row.columns:
            _mo_cr = _mo_row["Click Rate"].mean()
            _hint_month = f"{_camp_mo} averages {_mo_cr*100:.1f}% click rate · Best: {' / '.join(_best_mos)}"

    # Day hint — top 2 by click rate
    _best_days = _top_by(_hf, _dow_col, "Click Rate", n=2)
    _hint_day = f"Best historically: {' / '.join(_best_days)}" if _best_days else ""
    if _loaded_camp and _loaded_camp.get("send_date"):
        _camp_day = _loaded_camp["send_date"].strftime("%A")
        _day_row = _hf[_hf[_dow_col] == _camp_day]
        if not _day_row.empty and "Click Rate" in _day_row.columns:
            _day_cr = _day_row["Click Rate"].mean()
            _hint_day = f"{_camp_day} averages {_day_cr*100:.1f}% click rate · Best: {' / '.join(_best_days)}"

    # Time hint
    _time_grp = _hf.groupby("_time_bucket")["Open Rate"].mean().dropna().sort_values(ascending=False)
    _best_time = _time_grp.index[0] if not _time_grp.empty and _time_grp.index[0] else None
    _hint_time = (f"Highest opens: {_best_time} ({_time_grp.iloc[0]*100:.1f}% avg open rate)"
                  if _best_time else "Send time data limited — morning sends generally outperform")

    # Copy theme hint
    _hint_theme = ""
    if "_themes" in _hf.columns and "Click Rate" in _hf.columns:
        from collections import Counter as _Counter
        _theme_cr: dict = {}
        for _, _row in _hf.iterrows():
            for _th in (_row.get("_themes") or []):
                if _th != "Other":
                    _theme_cr.setdefault(_th, []).append(_row.get("Click Rate") or 0)
        _theme_avg = {t: sum(v)/len(v) for t, v in _theme_cr.items() if v}
        if _theme_avg:
            _best_th = max(_theme_avg, key=_theme_avg.get)
            _hint_theme = f"Highest click rate: {_best_th} ({_theme_avg[_best_th]*100:.1f}% avg)"

    # Tone / copy hint — pull from Generation if already set for this campaign
    _hint_tone = ""
    if _cid_pre and st.session_state.get("gen_for_camp_id") == _cid_pre:
        _gen_tone = st.session_state.get("gen_tone", "")
        if _gen_tone:
            _hint_tone = f"Generation has: \"{_gen_tone[:60]}{'…' if len(_gen_tone)>60 else ''}\""

    _push_note = (
        f'<p style="font-family:\'Barlow\',sans-serif;font-size:0.72rem;'
        f'color:{COLORS["muted"]};margin-bottom:12px;">'
        f'This is a <strong>playground</strong> — experiment freely. '
        f'Use the push buttons to send decisions to the relevant tabs.</p>'
    )

    col_lbl, col_main, col_perf = st.columns([2, 5, 3], gap="large")

    # ── Left: label strip ─────────────────────────────────────────────────────
    with col_lbl:
        lbl_groups = [
            ("Campaign",    ["Mode","Category","Product","Studio"]),
            ("Audience",    ["Segment"]),
            ("Timing",      ["Month","Day","Time"]),
            ("Copy",        ["Theme","Tone","CTA","Highlights"]),
            ("Design",      ["Format"]),
        ]
        lbl_html = '<div style="margin-top:2.4rem;">'
        for grp, items in lbl_groups:
            lbl_html += (f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.55rem;'
                         f'font-weight:700;letter-spacing:0.1em;text-transform:uppercase;'
                         f'color:{COLORS["muted"]};margin:10px 0 4px 2px;">{grp}</div>')
            for item in items:
                lbl_html += (f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.72rem;'
                             f'font-weight:800;letter-spacing:0.07em;text-transform:uppercase;'
                             f'color:{COLORS["black"]};background:{COLORS["offwhite"]};'
                             f'border:1px solid {COLORS["border"]};border-radius:6px;'
                             f'padding:6px 10px;margin-bottom:5px;text-align:center;">{item}</div>')
        lbl_html += "</div>"
        st.markdown(lbl_html, unsafe_allow_html=True)

    # ── Middle: decision playground ────────────────────────────────────────────
    with col_main:
        st.markdown(_push_note, unsafe_allow_html=True)

        # — Group 1: Campaign basics —
        st.markdown(_group_hdr("Campaign", COLORS["yellow"]), unsafe_allow_html=True)
        g1c1, g1c2 = st.columns(2)
        with g1c1:
            _t_mode = st.radio("Mode", ["Email","SMS"], horizontal=True, key="trk_mode")
        with g1c2:
            _tc_sel  = st.multiselect("Category", _cat_opts, key="trk_cat")
            _tc_cust = st.text_input("trk_cat_c", value="", label_visibility="collapsed",
                                     placeholder="+ Custom category", key="trk_cat_cust_inp")
        t_cats = _tc_sel + ([v.strip() for v in _tc_cust.split(",") if v.strip()] if _tc_cust else [])
        g1c3, g1c4 = st.columns(2)
        with g1c3:
            t_prods = st.multiselect("Product", _prod_opts, key="trk_prods")
            _hint(_hint_prod)
        with g1c4:
            t_studios = st.multiselect("Studio", _studio_opts, key="trk_studios")
            _hint(_hint_studio)

        # — Group 2: Audience — with push to Decisioning
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        aud_hdr_col, aud_push_col = st.columns([4, 1])
        with aud_hdr_col:
            st.markdown(_group_hdr("Audience &amp; Timing", COLORS["lavender"]), unsafe_allow_html=True)
        with aud_push_col:
            _push_dec = st.button("→ Decisioning", key="trk_push_dec", help="Push segment decisions to the Decisioning tab")
        _ts_sel  = st.multiselect("Segment", _seg_opts, key="trk_seg")
        _ts_cust = st.text_input("trk_seg_c", value="", label_visibility="collapsed",
                                 placeholder="+ Custom segment (e.g. customers in LA, last 90 days)",
                                 key="trk_seg_cust_inp")
        t_segs = _ts_sel + ([v.strip() for v in _ts_cust.split(",") if v.strip()] if _ts_cust else [])

        g2c1, g2c2, g2c3 = st.columns(3)
        with g2c1: t_months = st.multiselect("Month", _MOS,   key="trk_months")
        with g2c2: t_days   = st.multiselect("Day",   _DAYS,  key="trk_days")
        with g2c3: t_times  = st.multiselect("Time",  _TIMES, key="trk_times")

        # Handle Decisioning push
        if _push_dec:
            _cid = st.session_state.get("trk_sel_camp")
            if _cid and t_segs:
                if "decisioning_state" not in st.session_state:
                    st.session_state["decisioning_state"] = {}
                if _cid not in st.session_state["decisioning_state"]:
                    st.session_state["decisioning_state"][_cid] = {"segments": [], "freq_cap": "", "suppressions": [], "flow_priority": "", "flow_target": "", "refinements": []}
                st.session_state["decisioning_state"][_cid]["segments"] = t_segs
                st.session_state["active_campaign_id"] = _cid
                st.success(f"✓ Audience pushed to Decisioning tab ({len(t_segs)} segment{'s' if len(t_segs)!=1 else ''})")
            elif not _cid:
                st.warning("Load a campaign first to push decisions.")
            else:
                st.warning("Select at least one segment to push.")

        # — Group 3: Copy — with push to Generation
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        cpy_hdr_col, cpy_push_col = st.columns([4, 1])
        with cpy_hdr_col:
            st.markdown(_group_hdr("Copy", COLORS["lime"]), unsafe_allow_html=True)
        with cpy_push_col:
            _push_gen = st.button("→ Generation", key="trk_push_gen", help="Push copy decisions to the Generation tab")

        t_themes = st.multiselect("Subject Line Theme", _THEME_OPTS, key="trk_themes",
                                  help="Filters prediction to campaigns using these subject line approaches")
        g3c1, g3c2 = st.columns(2)
        with g3c1:
            t_tone = st.text_input("Tone / Voice", key="trk_tone_text",
                                   placeholder='e.g. "Warm and celebratory, slight urgency"')
        with g3c2:
            t_cta = st.text_input("Primary CTA", key="trk_cta_text",
                                  placeholder='e.g. "Shop the edit"')
        t_highlights = st.text_area("Key highlights", key="trk_highlights_text", height=68,
                                    placeholder="Product names, studio context, occasion, press — anything copy should reflect")

        # Handle Generation push
        if _push_gen:
            _cid = st.session_state.get("trk_sel_camp")
            if _cid:
                st.session_state["active_campaign_id"] = _cid
                st.session_state["gen_for_camp_id"]    = _cid
                if t_tone:       st.session_state["gen_tone"]       = t_tone
                if t_cta:        st.session_state["gen_cta"]        = t_cta
                if t_highlights: st.session_state["gen_highlights"] = t_highlights
                st.success("✓ Copy decisions pushed to Generation tab — navigate there to generate.")
            else:
                st.warning("Load a campaign first to push decisions.")

        # — Group 4: Design —
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        st.markdown(_group_hdr("Design", COLORS["border"]), unsafe_allow_html=True)
        t_design = st.selectbox("Visual Format", _DESIGN_OPTS, key="trk_design")

        st.markdown("<hr>", unsafe_allow_html=True)

        # — AI recommendation + comparison —
        _ai_recs, _ai_perf = _ai_rec(df_t, mode=_t_mode)
        bot_l, bot_r = st.columns(2, gap="medium")

        with bot_l:
            st.markdown(f'<div style="{_hdr_style}margin-bottom:8px;">Recommended by AI</div>',
                        unsafe_allow_html=True)
            st.markdown(_ai_rec_html(_ai_recs), unsafe_allow_html=True)

        with bot_r:
            st.markdown(f'<div style="{_hdr_style}margin-bottom:8px;">Compare a Scenario</div>',
                        unsafe_allow_html=True)
            _ac_sel  = st.multiselect("Category",    _cat_opts, key="alt_cats")
            _ac_cust = st.text_input("alt_cat_c", value="", label_visibility="collapsed",
                                     placeholder="+ Custom category", key="alt_cat_cust_inp")
            a_cats = _ac_sel + ([v.strip() for v in _ac_cust.split(",") if v.strip()] if _ac_cust else [])
            ar1, ar2 = st.columns(2)
            with ar1: a_prods   = st.multiselect("Product", _prod_opts,   key="alt_prods")
            with ar2: a_studios = st.multiselect("Studio",  _studio_opts, key="alt_studios")
            ar3, ar4 = st.columns(2)
            with ar3: a_months = st.multiselect("Month", _MOS,  key="alt_months")
            with ar4: a_days   = st.multiselect("Day",   _DAYS, key="alt_days")
            a_times  = st.multiselect("Time",  _TIMES,  key="alt_times")
            a_themes = st.multiselect("Copy Theme", _THEME_OPTS, key="alt_themes")

    # ── Right: prediction panel ────────────────────────────────────────────────
    with col_perf:
        st.markdown(f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:0.65rem;'
                    f'font-weight:800;letter-spacing:0.1em;text-transform:uppercase;'
                    f'color:{COLORS["muted"]};margin-bottom:12px;margin-top:0;">Expected Performance</div>',
                    unsafe_allow_html=True)

        # — Decision badges —
        _decisions_made = []
        if _t_mode:                                    _decisions_made.append(("Mode",     _t_mode,                      COLORS["black"],    "#fff"))
        if t_cats:                                     _decisions_made.append(("Category", ", ".join(t_cats[:1]),         COLORS["yellow"],   COLORS["black"]))
        if t_segs:                                     _decisions_made.append(("Audience", f"{len(t_segs)} seg",          COLORS["lavender"], COLORS["black"]))
        if t_months or t_days or t_times:              _decisions_made.append(("Timing",   f"{len(t_months)+len(t_days)+len(t_times)} set", COLORS["lavender"], COLORS["black"]))
        if t_themes:                                   _decisions_made.append(("Theme",    ", ".join(t_themes[:1]),       COLORS["lime"],     COLORS["black"]))
        if t_tone:                                     _decisions_made.append(("Tone",     t_tone[:18],                  COLORS["lime"],     COLORS["black"]))
        if t_design and t_design != "No preference":   _decisions_made.append(("Design",   t_design[:14],                COLORS["offwhite"], COLORS["black"]))

        if _decisions_made:
            badges_html = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px;">'
            for lbl, val, bg, txt in _decisions_made:
                badges_html += (f'<span style="background:{bg};color:{txt};font-family:\'Barlow\',sans-serif;'
                                f'font-size:0.6rem;font-weight:600;padding:2px 8px;border-radius:50px;'
                                f'border:1px solid {COLORS["border"]};">{lbl}: {val}</span>')
            badges_html += '</div>'
            st.markdown(badges_html, unsafe_allow_html=True)

        # Compute user prediction (progressive)
        _user_perf = _predict(
            df_t, mode=_t_mode,
            cats=t_cats or None, prods=t_prods or None, studios=t_studios or None,
            months=t_months or None, days=t_days or None, times=t_times or None,
            themes=t_themes or None,
        )
        _n = _user_perf["n"] if _user_perf else 0

        # Design note (qualitative)
        _design_note = None
        if t_design and t_design != "No preference":
            _notes = {
                "Hero Image":             "Hero images tend to drive strong open-to-click.",
                "Product Grid":           "Grid formats support higher conversion from browse intent.",
                "Lifestyle Photography":  "Lifestyle imagery typically lifts open rates.",
                "GIF / Animation":        "Animated content often improves click engagement.",
                "Text-Only / Minimal":    "Minimal designs can reduce inbox clutter friction.",
            }
            _design_note = _notes.get(t_design)

        st.markdown(_perf_card("Your Selection", _user_perf, COLORS["yellow"],
                               badge_n=_n, extra_note=_design_note),
                    unsafe_allow_html=True)

        st.markdown(_perf_card("AI Recommendation", _ai_perf, COLORS["lime"],
                               badge_n=_ai_perf["n"] if _ai_perf else None),
                    unsafe_allow_html=True)

        # Comparison scenario (only if alt inputs used)
        _alt_any = any([a_cats, a_prods, a_studios, a_months, a_days, a_times, a_themes])
        if _alt_any:
            _alt_perf = _predict(
                df_t, mode=_t_mode,
                cats=a_cats or None, prods=a_prods or None, studios=a_studios or None,
                months=a_months or None, days=a_days or None, times=a_times or None,
                themes=a_themes or None,
            )
            st.markdown(_perf_card("Comparison Scenario", _alt_perf, COLORS["lavender"],
                                   badge_n=_alt_perf["n"] if _alt_perf else None),
                        unsafe_allow_html=True)
