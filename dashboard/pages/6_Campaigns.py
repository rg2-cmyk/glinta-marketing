import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import datetime as dt
import streamlit as st

from shared.styles import COLORS, inject_css, top_nav
from shared.mock_campaigns import PHASES, PHASE_LABELS   # only constants, not mock data
from shared.owners import TEAMS, ROLES, render_assignment_widget, role_badge, team_badge

inject_css()
top_nav("Campaign Dashboard")

TODAY = dt.date.today()

# ── Ensure plan_added is seeded (mirrors Planning page init) ──────────────────
if "plan_added" not in st.session_state:
    st.session_state["plan_added"] = []
    try:
        from shared.sheets import load_planned_campaigns as _sheets_load
        st.session_state["plan_added"] = _sheets_load()
    except Exception:
        pass

# ── Session state ─────────────────────────────────────────────────────────────
if "cd_selected" not in st.session_state:
    st.session_state["cd_selected"] = None
if "cd_task_assignments" not in st.session_state:
    st.session_state["cd_task_assignments"] = {}

# ── Constants ─────────────────────────────────────────────────────────────────
PHASE_ORDER = {p: i for i, p in enumerate(PHASES)}

PHASE_DEADLINE_DAYS = {
    "planning": 7, "decisioning": 5, "generation": 4, "design": 2, "execution": 1
}
PHASE_DEADLINE_LABELS = {
    "planning":    "Brief due",
    "decisioning": "Audience sign-off",
    "generation":  "Copy approval",
    "design":      "Design approval",
    "execution":   "QA sign-off",
}

PHASE_BADGE_COLORS = {
    "planning":    ("#E8F4FD", "#2980B9"),
    "decisioning": ("#FEF9E7", "#D4AC0D"),
    "generation":  ("#EAF4FB", "#1A5276"),
    "design":      ("#F4ECF7", "#8E44AD"),
    "execution":   ("#EAFAF1", "#1E8449"),
}

STATUS_COLORS = {
    "Not Started": (COLORS["offwhite"], COLORS["muted"]),
    "Draft":       ("#FFF8E1", "#E67E22"),
    "In Review":   ("#E3F2FD", "#1565C0"),
    "In Progress": ("#FFF3E0", "#E65100"),
    "Approved":    ("#E8F5E9", "#2E7D32"),
}

PRIORITY_COLORS = {
    "High":   COLORS["danger"],
    "Medium": COLORS["warn"],
    "Low":    COLORS["muted"],
}

DECISION_AREAS = ["Brief", "Audience", "Send Time", "Copy", "Personalizations", "Design"]
DECISION_ICONS = {
    "Brief": "📋", "Audience": "👥", "Send Time": "🕐",
    "Copy": "✍️", "Personalizations": "🎯", "Design": "🎨",
}

KEY_MOMENT_RULES = {
    "Product Launch": {
        "tags": ["Product Launch", "Launch", "Drop"],
        "categories": ["VIP/Loyalty"],
        "icon": "🚀",
        "label": "Product Launch",
    },
    "Studio Opening": {
        "tags": ["Studio", "Event"],
        "categories": ["Studio/Retail"],
        "icon": "🏛",
        "label": "Studio Opening",
    },
    "Promo / Sale": {
        "tags": ["Flash Sale", "Discount", "Promo", "Sale"],
        "categories": ["Promotional"],
        "icon": "🏷",
        "label": "Promo / Sale",
    },
    "Restock": {
        "tags": ["Restock"],
        "categories": ["Restock"],
        "icon": "📦",
        "label": "Restock",
    },
    "Holiday / Seasonal": {
        "tags": ["Holiday", "Seasonal"],
        "categories": ["Holiday/Seasonal"],
        "icon": "🎉",
        "label": "Holiday",
    },
    "Editorial": {
        "tags": ["Editorial", "Gift", "Content"],
        "categories": ["Editorial"],
        "icon": "📰",
        "label": "Editorial",
    },
}


# ── Campaign normalizer ───────────────────────────────────────────────────────
def _normalize(c: dict) -> dict:
    phase_raw = c.get("phase") or c.get("status") or "planning"
    phase = {"planned": "planning"}.get(phase_raw, phase_raw)
    if phase not in PHASE_ORDER:
        phase = "planning"
    phase_idx = PHASE_ORDER[phase]

    sd = c.get("send_date")
    if hasattr(sd, "date"):
        sd = sd.date()
    if not isinstance(sd, dt.date):
        sd = TODAY + dt.timedelta(days=14)

    dec = c.get("decisioning") or {}
    audiences = c.get("audiences") or dec.get("segments") or []
    if isinstance(audiences, str):
        audiences = [a.strip() for a in audiences.split(",") if a.strip()]
    primary_segment = audiences[0] if audiences else c.get("segment", "TBD")

    send_time = c.get("send_time") or dec.get("send_time") or ""
    subject = c.get("subject") or c.get("subject_line_draft") or ""

    brief_status = (
        c.get("brief_status") or
        ("Approved" if phase_idx >= 2 else "In Review" if phase_idx == 1 else "Not Started")
    )
    design_status = (
        c.get("design_status") or
        ("Approved" if phase_idx >= 4 else "In Progress" if phase_idx == 3 else "Not Started")
    )
    qa_status = c.get("qa_status") or ("In Progress" if phase_idx == 4 else "Not Started")

    all_assigns = st.session_state.get("_campaign_assignments", {})
    camp_assigns = all_assigns.get(c.get("id", ""), [])
    owner = camp_assigns[0]["team"] if camp_assigns else c.get("assigned_to", "Unassigned")

    offset = PHASE_DEADLINE_DAYS.get(phase, 7)
    next_deadline = sd - dt.timedelta(days=offset)

    tags = c.get("tags") or []
    category = c.get("category", "")
    moment_type = "Other"
    for mtype, rules in KEY_MOMENT_RULES.items():
        if any(t in tags for t in rules["tags"]) or category in rules["categories"]:
            moment_type = mtype
            break

    return {
        "id":                   c.get("id", ""),
        "name":                 c.get("name", "Untitled"),
        "category":             category,
        "channel":              (c.get("channel") or "email").lower(),
        "send_date":            sd,
        "phase":                phase,
        "tags":                 tags,
        "segment":              primary_segment,
        "audiences":            audiences,
        "audience_est":         c.get("audience_est") or 0,
        "subject_line_draft":   subject,
        "copy_notes":           c.get("copy_notes") or "",
        "personalization_notes": c.get("personalization_notes") or "",
        "design_brief":         c.get("design_brief") or "",
        "revenue_est":          c.get("revenue_est") or 0,
        "assigned_to":          owner,
        "brief_status":         brief_status,
        "design_status":        design_status,
        "qa_status":            qa_status,
        "priority":             c.get("priority") or "Medium",
        "next_deadline":        next_deadline,
        "next_deadline_label":  PHASE_DEADLINE_LABELS.get(phase, "Next milestone"),
        "send_time":            send_time,
        "goal":                 c.get("goal") or "",
        "decisioning":          dec,
        "moment_type":          moment_type,
        "products":             c.get("products") or c.get("product") or "",
    }


# ── Badge helpers ─────────────────────────────────────────────────────────────
def phase_badge_html(phase):
    bg, fg = PHASE_BADGE_COLORS.get(phase, ("#f0f0f0", "#333"))
    label = PHASE_LABELS.get(phase, phase.title())
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 9px;border-radius:4px;'
        f'font-size:0.65rem;font-weight:600;font-family:\'Barlow\',sans-serif;'
        f'white-space:nowrap;">{label}</span>'
    )


def channel_badge_html(channel):
    bg  = "#1a1a1a" if channel == "email" else "#f0f0f0"
    fg  = "#ffffff"  if channel == "email" else COLORS["black"]
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:4px;'
        f'font-size:0.65rem;font-weight:600;font-family:\'Barlow\',sans-serif;'
        f'letter-spacing:0.04em;">{channel.upper()}</span>'
    )


# ── Decision logic ────────────────────────────────────────────────────────────
def decision_status(camp, area):
    phase_idx = PHASE_ORDER.get(camp["phase"], 0)
    if area == "Brief":
        return camp["brief_status"]
    if area == "Audience":
        if phase_idx >= 2: return "Approved"
        if phase_idx == 1 and camp["audiences"]: return "In Review"
        return "Not Started"
    if area == "Send Time":
        if phase_idx >= 2: return "Approved"
        if camp.get("send_time"): return "In Review"
        if phase_idx == 1: return "In Review"
        return "Not Started"
    if area == "Copy":
        if phase_idx >= 3: return "Approved"
        if camp["subject_line_draft"] or camp["copy_notes"]: return "Draft"
        return "Not Started"
    if area == "Personalizations":
        if phase_idx >= 3: return "Approved"
        if camp["personalization_notes"]: return "Draft"
        return "Not Started"
    if area == "Design":
        return camp["design_status"]
    return "Not Started"


def decision_value(camp, area):
    if area == "Brief":
        parts = [p for p in [camp["category"], camp["channel"].upper(), camp.get("goal")] if p]
        return " · ".join(parts) if parts else "—"
    if area == "Audience":
        segs = camp["audiences"]
        if segs:
            label = segs[0] if isinstance(segs[0], str) else str(segs[0])
            extra = f" +{len(segs)-1}" if len(segs) > 1 else ""
            size = f" ({camp['audience_est']:,})" if camp["audience_est"] else ""
            return label + extra + size
        return camp.get("segment", "—")
    if area == "Send Time":
        send_time = camp.get("send_time", "")
        date_str = camp["send_date"].strftime("%b %d, %Y")
        return f"{date_str}  {send_time}".strip() if send_time else date_str
    if area == "Copy":
        sl = camp["subject_line_draft"]
        return sl if sl else (camp["copy_notes"] or "—")
    if area == "Personalizations":
        return camp["personalization_notes"] or "—"
    if area == "Design":
        return camp["design_brief"] or "—"
    return "—"


# ── Task panel ────────────────────────────────────────────────────────────────
def _render_task_panel(camp):
    cid = camp["id"]
    if cid not in st.session_state["cd_task_assignments"]:
        st.session_state["cd_task_assignments"][cid] = []
    tasks = st.session_state["cd_task_assignments"][cid]

    st.markdown(
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.62rem;'
        f'text-transform:uppercase;letter-spacing:0.08em;font-weight:600;'
        f'color:{COLORS["muted"]};margin-bottom:10px;">Assigned Tasks</div>',
        unsafe_allow_html=True,
    )

    if tasks:
        for i, task in enumerate(tasks):
            due = task.get("due")
            due_str = due.strftime("%b %d") if isinstance(due, dt.date) else (str(due) if due else "—")
            delta = (due - TODAY).days if isinstance(due, dt.date) else None
            due_color = (
                COLORS["danger"] if delta is not None and delta <= 0 else
                COLORS["warn"]   if delta is not None and delta <= 2 else
                COLORS["muted"]
            )
            t_cols = st.columns([3.5, 0.4])
            with t_cols[0]:
                st.markdown(
                    f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};'
                    f'border-radius:5px;padding:8px 10px;margin-bottom:5px;">'
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.75rem;font-weight:600;'
                    f'color:{COLORS["black"]};margin-bottom:4px;">{task["task"]}</div>'
                    f'<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">'
                    + team_badge(task["team"]) + "&nbsp;" + role_badge(task.get("note") or task["role"]) +
                    f'<span style="font-size:0.62rem;color:{due_color};font-weight:600;'
                    f'font-family:\'Barlow\',sans-serif;white-space:nowrap;">Due {due_str}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            with t_cols[1]:
                st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
                if st.button("×", key=f"cd_rm_task_{cid}_{i}", type="secondary"):
                    tasks.pop(i)
                    st.session_state["cd_task_assignments"][cid] = tasks
                    st.rerun()
    else:
        st.markdown(
            f'<div style="color:{COLORS["muted"]};font-family:\'Barlow\',sans-serif;'
            f'font-size:0.75rem;margin-bottom:8px;">No tasks assigned yet.</div>',
            unsafe_allow_html=True,
        )

    with st.expander("＋ Assign New Task", expanded=False):
        new_task_name = st.text_input(
            "Task description",
            key=f"cd_task_name_{cid}",
            placeholder="e.g. Review copy draft, Approve design…",
        )
        assign_result = render_assignment_widget(
            key=f"cd_assign_{cid}",
            label="Assign to",
            allow_multiple=False,
        )
        due_date = st.date_input(
            "Due date",
            value=camp["next_deadline"],
            min_value=TODAY,
            key=f"cd_task_due_{cid}",
        )
        if st.button("Assign Task", key=f"cd_add_task_{cid}", type="primary"):
            if new_task_name.strip() and assign_result:
                tasks.append({
                    "task": new_task_name.strip(),
                    "team": assign_result[0]["team"],
                    "role": assign_result[0]["role"],
                    "note": assign_result[0].get("note", ""),
                    "due":  due_date,
                })
                st.session_state["cd_task_assignments"][cid] = tasks
                st.toast(f"Task assigned to {assign_result[0]['team']}", icon="✓")
                st.rerun()
            else:
                st.warning("Enter a task description before assigning.")


# ── Detail panel ──────────────────────────────────────────────────────────────
def _render_detail_panel(camp):
    st.markdown('<div style="height:4px;"></div>', unsafe_allow_html=True)

    ch_bg  = "#1a1a1a" if camp["channel"] == "email" else "#f0f0f0"
    ch_txt = "#ffffff"  if camp["channel"] == "email" else COLORS["black"]

    send_time_str = f"  ·  {camp['send_time']}" if camp.get("send_time") else ""
    st.markdown(
        f'<div style="background:{COLORS["offwhite"]};border:1px solid {COLORS["border"]};'
        f'border-bottom:none;border-radius:8px 8px 0 0;padding:14px 20px;">'
        f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">'
        f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.2rem;'
        f'font-weight:800;color:{COLORS["black"]};">{camp["name"]}</span>'
        f'<span style="background:{ch_bg};color:{ch_txt};padding:2px 10px;border-radius:4px;'
        f'font-size:0.65rem;font-weight:600;font-family:\'Barlow\',sans-serif;">'
        f'{camp["channel"].upper()}</span>'
        + phase_badge_html(camp["phase"]) +
        f'<span style="margin-left:auto;font-family:\'Barlow\',sans-serif;font-size:0.75rem;'
        f'color:{COLORS["muted"]};">Owner: <strong style="color:{COLORS["black"]};">'
        f'{camp["assigned_to"]}</strong>&nbsp;&nbsp;·&nbsp;&nbsp;Send: '
        f'<strong style="color:{COLORS["black"]};">'
        f'{camp["send_date"].strftime("%b %d, %Y")}{send_time_str}</strong></span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns([1.6, 1])

    with left_col:
        st.markdown(
            f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};'
            f'border-right:none;border-top:none;padding:16px 20px;">',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.62rem;'
            f'text-transform:uppercase;letter-spacing:0.08em;font-weight:600;'
            f'color:{COLORS["muted"]};margin-bottom:12px;">Campaign Decisions</div>',
            unsafe_allow_html=True,
        )
        d_rows = [DECISION_AREAS[:3], DECISION_AREAS[3:]]
        for row_areas in d_rows:
            dcols = st.columns(3)
            for dcol, area in zip(dcols, row_areas):
                with dcol:
                    status = decision_status(camp, area)
                    value  = decision_value(camp, area)
                    bg, fg = STATUS_COLORS.get(status, (COLORS["offwhite"], COLORS["muted"]))
                    icon   = DECISION_ICONS.get(area, "")
                    display_val = value if len(value) <= 55 else value[:52] + "…"
                    st.markdown(
                        f'<div style="background:{COLORS["offwhite"]};'
                        f'border:1px solid {COLORS["border"]};border-radius:6px;'
                        f'padding:10px 12px;margin-bottom:8px;min-height:78px;">'
                        f'<div style="display:flex;justify-content:space-between;'
                        f'align-items:flex-start;margin-bottom:5px;">'
                        f'<span style="font-family:\'Barlow\',sans-serif;font-size:0.7rem;'
                        f'font-weight:600;color:{COLORS["black"]};">{icon} {area}</span>'
                        f'<span style="background:{bg};color:{fg};padding:1px 7px;'
                        f'border-radius:3px;font-size:0.58rem;font-weight:600;'
                        f'font-family:\'Barlow\',sans-serif;white-space:nowrap;">{status}</span>'
                        f'</div>'
                        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.7rem;'
                        f'color:{COLORS["muted"]};line-height:1.4;">{display_val}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        st.markdown('</div>', unsafe_allow_html=True)

    with right_col:
        st.markdown(
            f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};'
            f'border-top:none;padding:16px 20px;">',
            unsafe_allow_html=True,
        )
        _render_task_panel(camp)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div style="background:{COLORS["offwhite"]};border:1px solid {COLORS["border"]};'
        f'border-top:none;border-radius:0 0 8px 8px;padding:4px 20px;"></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)


# ── Summary tab helpers ───────────────────────────────────────────────────────
def _kpi_card(label, value, sub="", icon="", accent_color=None):
    border_left = (
        f'border-left:4px solid {accent_color};'
        if accent_color else f'border-left:1px solid {COLORS["border"]};'
    )
    return (
        f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};{border_left}'
        f'border-radius:8px;padding:18px 20px;flex:1;min-width:0;">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        + (f'<span style="font-size:16px;line-height:1;">{icon}</span>' if icon else "")
        + f'<div style="font-family:\'Barlow\',sans-serif;font-size:11px;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.08em;color:{COLORS["muted"]};">{label}</div>'
        f'</div>'
        f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:32px;font-weight:800;'
        f'color:{COLORS["black"]};line-height:1;">{value}</div>'
        + (f'<div style="font-family:\'Barlow\',sans-serif;font-size:12px;color:{COLORS["muted"]};margin-top:6px;">{sub}</div>' if sub else "")
        + f'</div>'
    )


def _section_header(text, accent_color=None):
    bar = (
        f'<span style="display:inline-block;width:4px;height:14px;background:{accent_color};'
        f'border-radius:2px;margin-right:8px;vertical-align:middle;"></span>'
        if accent_color else ""
    )
    return (
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:13px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.08em;color:{COLORS["black"]};'
        f'border-bottom:2px solid {COLORS["black"]};padding-bottom:7px;margin:24px 0 14px;">'
        f'{bar}<span style="vertical-align:middle;">{text}</span></div>'
    )


def fmt_rev(val):
    if val >= 1_000_000:
        return f"${val/1e6:.1f}M"
    if val >= 1_000:
        return f"${val/1e3:.1f}K"
    return f"${val:,.0f}"


def _render_summary_tab(all_campaigns):
    import plotly.graph_objects as go

    upcoming = [c for c in all_campaigns if c["send_date"] >= TODAY]

    email_count  = sum(1 for c in upcoming if c["channel"] == "email")
    sms_count    = sum(1 for c in upcoming if c["channel"] == "sms")
    email_reach  = sum(c["audience_est"] for c in upcoming if c["channel"] == "email")
    sms_reach    = sum(c["audience_est"] for c in upcoming if c["channel"] == "sms")
    total_reach  = email_reach + sms_reach

    # ── Illustrative performance benchmarks ───────────────────────────────────
    # Email: delivery 95%, click 2.5%, conv 1.5%, RPR $0.18
    # SMS:   delivery 95%, click 8.0%, conv 2.5%, RPR $0.22
    EMAIL_DELIVERY, EMAIL_CLICK, EMAIL_CONV, EMAIL_RPR = 0.95, 0.025, 0.015, 0.18
    SMS_DELIVERY,   SMS_CLICK,   SMS_CONV,   SMS_RPR   = 0.95, 0.080, 0.025, 0.22

    # Weight by reach if available, fall back to campaign count split
    e_wt = email_reach if total_reach else email_count
    s_wt = sms_reach   if total_reach else sms_count
    total_wt = e_wt + s_wt or 1

    w_click_rate = (e_wt * EMAIL_CLICK + s_wt * SMS_CLICK) / total_wt
    w_conv_rate  = (e_wt * EMAIL_CONV  + s_wt * SMS_CONV)  / total_wt
    exp_revenue  = (
        email_reach * EMAIL_DELIVERY * EMAIL_RPR +
        sms_reach   * SMS_DELIVERY   * SMS_RPR
    )

    def _fmt_n(n):
        if n >= 1_000_000: return f"{n/1e6:.1f}M"
        if n >= 1_000:     return f"{n/1e3:.1f}K"
        return f"{n:,}"

    # ── Top KPIs — compact row ────────────────────────────────────────────────
    reach_sub = f"Email {_fmt_n(email_reach)} · SMS {_fmt_n(sms_reach)}" if total_reach else "recipient data not yet set"
    LIME = "#caf30b"
    LAVENDER = "#e8c5ff"
    YELLOW = "#f5f000"
    kpi_html = (
        '<div style="display:flex;gap:12px;margin-bottom:28px;">'
        + _kpi_card("Upcoming Campaigns", str(len(upcoming)), "across all channels", icon="📣", accent_color=LIME)
        + _kpi_card("Email Campaigns", str(email_count), "planned sends", icon="✉️")
        + _kpi_card("SMS Campaigns", str(sms_count), "planned sends", icon="💬")
        + _kpi_card("Total Recipients", _fmt_n(total_reach) if total_reach else "—", reach_sub, icon="👥", accent_color=LAVENDER)
        + '</div>'
    )
    st.markdown(kpi_html, unsafe_allow_html=True)

    # ── Expected Performance ──────────────────────────────────────────────────
    st.markdown(_section_header("Expected Performance Across All Planned Campaigns", accent_color=LIME), unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:12px;color:{COLORS["muted"]};'
        f'margin:-8px 0 14px;font-style:italic;">'
        f'Illustrative — rates from historical benchmarks weighted by channel mix; '
        f'revenue = recipients × delivery rate × RPR</div>',
        unsafe_allow_html=True,
    )

    rev_val = fmt_rev(exp_revenue) if exp_revenue else "—"
    rev_sub = (
        f"RPR Email ${EMAIL_RPR} · SMS ${SMS_RPR} · {EMAIL_DELIVERY*100:.0f}% delivery"
        if exp_revenue else "Add recipient counts to campaigns to calculate"
    )
    perf_cols = st.columns(3)
    perf_metrics = [
        ("Click Rate",       f"{w_click_rate*100:.1f}%", f"Email {EMAIL_CLICK*100:.1f}% · SMS {SMS_CLICK*100:.1f}%", "👆", LIME),
        ("Conversion Rate",  f"{w_conv_rate*100:.1f}%",  f"Email {EMAIL_CONV*100:.1f}% · SMS {SMS_CONV*100:.1f}%",   "🎯", LAVENDER),
        ("Expected Revenue", rev_val, rev_sub, "💰", YELLOW),
    ]
    for col, (label, val, sub, icon, accent) in zip(perf_cols, perf_metrics):
        with col:
            st.markdown(
                f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};'
                f'border-top:4px solid {accent};border-radius:8px;padding:18px 22px;">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
                f'<span style="font-size:16px;line-height:1;">{icon}</span>'
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:11px;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.08em;color:{COLORS["muted"]};">{label}</div>'
                f'</div>'
                f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:36px;font-weight:800;'
                f'color:{COLORS["black"]};line-height:1;margin-bottom:8px;">{val}</div>'
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:12px;color:{COLORS["muted"]};">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="height:24px;"></div>', unsafe_allow_html=True)

    # ── Categories covered ────────────────────────────────────────────────────
    st.markdown(_section_header("Categories Covered"), unsafe_allow_html=True)

    cat_data = {}
    for c in upcoming:
        cat = c["category"] or "Uncategorized"
        cat_data.setdefault(cat, {"count": 0, "reach": 0})
        cat_data[cat]["count"] += 1
        cat_data[cat]["reach"] += c["audience_est"]

    total_up = len(upcoming) or 1
    sorted_cats = sorted(cat_data.items(), key=lambda x: -x[1]["count"])
    bar_palette = ["#1a1a1a", "#5a5a5a", LAVENDER, LIME, "#888888", YELLOW]

    cat_html = (
        f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};'
        f'border-radius:8px;padding:18px 22px;margin-bottom:24px;">'
    )
    for i, (cat, d) in enumerate(sorted_cats):
        pct   = d["count"] / total_up * 100
        bar_w = max(int(pct), 3)
        bar_color = bar_palette[i % len(bar_palette)]
        cat_html += (
            f'<div style="margin-bottom:14px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">'
            f'<span style="font-family:\'Barlow\',sans-serif;font-size:14px;font-weight:600;'
            f'color:{COLORS["black"]};">{cat}</span>'
            f'<span style="font-family:\'Barlow\',sans-serif;font-size:12px;color:{COLORS["muted"]};">'
            f'{d["count"]} campaign{"s" if d["count"] != 1 else ""} · '
            f'{_fmt_n(d["reach"])} recipients</span>'
            f'</div>'
            f'<div style="background:{COLORS["offwhite"]};border-radius:4px;height:10px;overflow:hidden;">'
            f'<div style="background:{bar_color};height:100%;width:{bar_w}%;border-radius:4px;"></div>'
            f'</div>'
            f'</div>'
        )
    cat_html += '</div>'
    st.markdown(cat_html, unsafe_allow_html=True)

    # ── Customer segments touched ─────────────────────────────────────────────
    seg_list = [(c["segment"], c["audience_est"]) for c in upcoming if c["segment"] and c["segment"] != "TBD"]
    if seg_list:
        st.markdown(_section_header("Customer Segments Touched", accent_color=LAVENDER), unsafe_allow_html=True)
        seg_dedup = {}
        for seg, est in seg_list:
            if seg not in seg_dedup or est > seg_dedup[seg]:
                seg_dedup[seg] = est
        seg_html = '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:24px;">'
        for seg, est in sorted(seg_dedup.items(), key=lambda x: -x[1]):
            seg_html += (
                f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};'
                f'border-left:3px solid {LAVENDER};border-radius:8px;padding:10px 14px;">'
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:13px;font-weight:600;'
                f'color:{COLORS["black"]};">{seg}</div>'
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:11px;color:{COLORS["muted"]};margin-top:2px;">'
                f'{_fmt_n(est)} est. recipients</div>'
                f'</div>'
            )
        seg_html += '</div>'
        st.markdown(seg_html, unsafe_allow_html=True)

    # ── Products & Studio Launches ────────────────────────────────────────────
    launches = [c for c in upcoming if c["moment_type"] in ("Product Launch", "Studio Opening", "Restock")]
    if launches:
        st.markdown(_section_header("Products & Studio Launches", accent_color=LIME), unsafe_allow_html=True)
        launch_cols = st.columns(min(len(launches), 3))
        for col, camp in zip(launch_cols, sorted(launches, key=lambda c: c["send_date"])):
            with col:
                rule = KEY_MOMENT_RULES.get(camp["moment_type"], {})
                icon = rule.get("icon", "•")
                label = rule.get("label", camp["moment_type"])
                days_away = (camp["send_date"] - TODAY).days
                timing = (
                    "Today" if days_away == 0 else
                    f"In {days_away}d" if days_away > 0 else f"{abs(days_away)}d ago"
                )
                ch_bg = "#1a1a1a" if camp["channel"] == "email" else COLORS["offwhite"]
                ch_fg = "#fff" if camp["channel"] == "email" else COLORS["black"]
                ch_border = "" if camp["channel"] == "email" else f"border:1px solid {COLORS['border']};"
                st.markdown(
                    f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};'
                    f'border-top:3px solid {LIME};border-radius:8px;padding:16px 18px;margin-bottom:12px;">'
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
                    f'<span style="font-size:18px;">{icon}</span>'
                    f'<span style="font-family:\'Barlow\',sans-serif;font-size:11px;font-weight:600;'
                    f'text-transform:uppercase;letter-spacing:0.08em;color:{COLORS["muted"]};">{label}</span>'
                    f'<span style="margin-left:auto;background:{ch_bg};color:{ch_fg};{ch_border}'
                    f'padding:2px 9px;border-radius:4px;font-size:10px;font-weight:700;font-family:\'Barlow\',sans-serif;">'
                    f'{camp["channel"].upper()}</span>'
                    f'</div>'
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:14px;font-weight:700;'
                    f'color:{COLORS["black"]};margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;'
                    f'white-space:nowrap;">{camp["name"]}</div>'
                    f'<div style="font-family:\'Barlow\',sans-serif;font-size:12px;color:{COLORS["muted"]};">'
                    f'{camp["send_date"].strftime("%b %d")} · {timing}'
                    + (f' · {_fmt_n(camp["audience_est"])} recipients' if camp["audience_est"] else "")
                    + f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Promotional Periods ───────────────────────────────────────────────────
    promos = sorted(
        [c for c in upcoming if c["moment_type"] in ("Promo / Sale", "Holiday / Seasonal")],
        key=lambda c: c["send_date"],
    )
    if promos:
        st.markdown(_section_header("Promotional Periods", accent_color=YELLOW), unsafe_allow_html=True)
        promo_html = (
            f'<div style="background:{COLORS["white"]};border:1px solid {COLORS["border"]};'
            f'border-radius:8px;padding:6px 22px;margin-bottom:12px;">'
        )
        for i, camp in enumerate(promos):
            days_away = (camp["send_date"] - TODAY).days
            timing = (
                "Today" if days_away == 0 else
                f"In {days_away}d" if days_away > 0 else f"{abs(days_away)}d ago"
            )
            timing_color = COLORS["black"] if days_away <= 7 else COLORS["muted"]
            rule = KEY_MOMENT_RULES.get(camp["moment_type"], {})
            icon = rule.get("icon", "•")
            ch_bg = "#1a1a1a" if camp["channel"] == "email" else COLORS["offwhite"]
            ch_fg = "#fff" if camp["channel"] == "email" else COLORS["black"]
            ch_border = "" if camp["channel"] == "email" else f"border:1px solid {COLORS['border']};"
            border_bottom = "" if i == len(promos) - 1 else f"border-bottom:1px solid {COLORS['border']};"
            promo_html += (
                f'<div style="display:flex;align-items:center;gap:14px;padding:12px 0;{border_bottom}">'
                f'<span style="font-size:18px;flex-shrink:0;">{icon}</span>'
                f'<span style="font-family:\'Barlow\',sans-serif;font-size:14px;font-weight:600;'
                f'color:{COLORS["black"]};flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                f'{camp["name"]}</span>'
                f'<span style="font-family:\'Barlow\',sans-serif;font-size:12px;'
                f'color:{COLORS["muted"]};white-space:nowrap;">{camp["send_date"].strftime("%b %d")}</span>'
                f'<span style="font-family:\'Barlow\',sans-serif;font-size:12px;font-weight:600;'
                f'color:{timing_color};white-space:nowrap;">{timing}</span>'
                f'<span style="background:{ch_bg};color:{ch_fg};{ch_border}padding:2px 9px;border-radius:4px;'
                f'font-size:10px;font-weight:700;font-family:\'Barlow\',sans-serif;white-space:nowrap;">'
                f'{camp["channel"].upper()}</span>'
                + (f'<span style="font-family:\'Barlow\',sans-serif;font-size:12px;'
                   f'color:{COLORS["muted"]};white-space:nowrap;">{_fmt_n(camp["audience_est"])} recipients</span>'
                   if camp["audience_est"] else "")
                + f'</div>'
            )
        promo_html += '</div>'
        st.markdown(promo_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("<h1>Campaign Dashboard</h1>", unsafe_allow_html=True)
st.markdown(
    '<p style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;color:#444;'
    'margin:-0.4rem 0 1.5rem;">All planned campaigns — executive overview and detail tracking.</p>',
    unsafe_allow_html=True,
)

# ── Load & normalize ──────────────────────────────────────────────────────────
raw_campaigns = st.session_state.get("plan_added", [])
all_campaigns = [_normalize(c) for c in raw_campaigns if c.get("name")]

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_summary, tab_detail = st.tabs(["Marketing Calendar Summary", "Campaign Detail"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Marketing Calendar Summary
# ══════════════════════════════════════════════════════════════════════════════
with tab_summary:
    if not all_campaigns:
        st.markdown(
            f'<div style="background:{COLORS["offwhite"]};border:1px solid {COLORS["border"]};'
            f'border-radius:8px;padding:40px 32px;text-align:center;margin-top:2rem;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.4rem;'
            f'font-weight:700;color:{COLORS["black"]};margin-bottom:8px;">No campaigns yet</div>'
            f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;color:{COLORS["muted"]};">'
            f'Create campaigns in the <strong>Planning</strong> page to see the summary here.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        _render_summary_tab(all_campaigns)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Campaign Detail
# ══════════════════════════════════════════════════════════════════════════════
with tab_detail:
    if not all_campaigns:
        st.markdown(
            f'<div style="background:{COLORS["offwhite"]};border:1px solid {COLORS["border"]};'
            f'border-radius:8px;padding:40px 32px;text-align:center;margin-top:2rem;">'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.4rem;'
            f'font-weight:700;color:{COLORS["black"]};margin-bottom:8px;">No campaigns yet</div>'
            f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.85rem;color:{COLORS["muted"]};">'
            f'Create campaigns in the <strong>Planning</strong> page to see them tracked here.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.stop()

    # ── Summary stats ─────────────────────────────────────────────────────────
    phase_counts = {p: sum(1 for c in all_campaigns if c["phase"] == p) for p in PHASES}
    overdue_count = sum(1 for c in all_campaigns if c["next_deadline"] < TODAY)

    stat_cols = st.columns(7)
    stats = [
        ("Total",       str(len(all_campaigns)),                 COLORS["black"]),
        ("Planning",    str(phase_counts.get("planning", 0)),    PHASE_BADGE_COLORS["planning"][1]),
        ("Decisioning", str(phase_counts.get("decisioning", 0)), PHASE_BADGE_COLORS["decisioning"][1]),
        ("Generation",  str(phase_counts.get("generation", 0)),  PHASE_BADGE_COLORS["generation"][1]),
        ("Design",      str(phase_counts.get("design", 0)),      PHASE_BADGE_COLORS["design"][1]),
        ("Execution",   str(phase_counts.get("execution", 0)),   PHASE_BADGE_COLORS["execution"][1]),
        ("Overdue",     str(overdue_count),                      COLORS["danger"] if overdue_count else COLORS["muted"]),
    ]
    for col, (label, val, color) in zip(stat_cols, stats):
        with col:
            st.markdown(
                f'<div style="background:{COLORS["offwhite"]};border:1px solid {COLORS["border"]};'
                f'border-radius:6px;padding:10px 14px;text-align:center;">'
                f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.6rem;'
                f'font-weight:800;color:{color};line-height:1;">{val}</div>'
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.62rem;color:{COLORS["muted"]};'
                f'text-transform:uppercase;letter-spacing:0.07em;margin-top:3px;">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="margin-top:1.5rem;"></div>', unsafe_allow_html=True)

    # ── Filters ───────────────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
    with fc1:
        filter_phase = st.selectbox(
            "Phase", ["All"] + [PHASE_LABELS[p] for p in PHASES], key="cd_filter_phase"
        )
    with fc2:
        filter_channel = st.selectbox("Channel", ["All", "Email", "SMS"], key="cd_filter_channel")
    with fc3:
        filter_priority = st.selectbox("Priority", ["All", "High", "Medium", "Low"], key="cd_filter_priority")
    with fc4:
        owners = sorted({c["assigned_to"] for c in all_campaigns})
        filter_owner = st.selectbox("Owner", ["All"] + owners, key="cd_filter_owner")

    campaigns = list(all_campaigns)
    if filter_phase != "All":
        phase_key = next(p for p in PHASES if PHASE_LABELS[p] == filter_phase)
        campaigns = [c for c in campaigns if c["phase"] == phase_key]
    if filter_channel != "All":
        campaigns = [c for c in campaigns if c["channel"] == filter_channel.lower()]
    if filter_priority != "All":
        campaigns = [c for c in campaigns if c["priority"] == filter_priority]
    if filter_owner != "All":
        campaigns = [c for c in campaigns if c["assigned_to"] == filter_owner]

    campaigns = sorted(campaigns, key=lambda c: c["send_date"])

    # ── Table ─────────────────────────────────────────────────────────────────
    st.markdown('<div style="margin-top:0.5rem;"></div>', unsafe_allow_html=True)

    header_cols = st.columns([0.5, 3.0, 0.8, 1.1, 1.0, 1.3, 1.0, 0.8, 0.45])
    headers = ["", "Campaign", "Channel", "Phase", "Owner", "Next Deadline", "Send Date", "Priority", ""]
    hdr_style = (
        f'font-family:\'Barlow\',sans-serif;font-size:0.6rem;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.08em;color:{COLORS["muted"]};padding:6px 0;'
    )
    for col, h in zip(header_cols, headers):
        with col:
            st.markdown(f'<div style="{hdr_style}">{h}</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div style="border-top:2px solid {COLORS["black"]};margin-bottom:0;"></div>',
        unsafe_allow_html=True,
    )

    if not campaigns:
        st.markdown(
            f'<div style="color:{COLORS["muted"]};font-family:\'Barlow\',sans-serif;'
            f'font-size:0.85rem;padding:20px 0;">No campaigns match the current filters.</div>',
            unsafe_allow_html=True,
        )

    for camp in campaigns:
        is_selected = st.session_state["cd_selected"] == camp["id"]
        deadline    = camp["next_deadline"]
        pri_color   = PRIORITY_COLORS.get(camp["priority"], COLORS["muted"])

        row_cols = st.columns([0.5, 3.0, 0.8, 1.1, 1.0, 1.3, 1.0, 0.8, 0.45])

        with row_cols[0]:
            st.markdown(
                f'<div style="display:flex;align-items:center;justify-content:center;height:40px;">'
                f'<span style="width:7px;height:7px;border-radius:50%;background:{pri_color};'
                f'display:inline-block;"></span></div>',
                unsafe_allow_html=True,
            )

        with row_cols[1]:
            tags = camp.get("tags") or []
            tags_html = " ".join(
                f'<span style="background:{COLORS["offwhite"]};border:1px solid {COLORS["border"]};'
                f'color:{COLORS["muted"]};padding:1px 6px;border-radius:3px;font-size:0.58rem;">{t}</span>'
                for t in tags[:2]
            )
            goal_chip = ""
            if camp.get("goal") and not tags:
                goal_chip = (
                    f'<span style="background:{COLORS["offwhite"]};border:1px solid {COLORS["border"]};'
                    f'color:{COLORS["muted"]};padding:1px 6px;border-radius:3px;font-size:0.58rem;">'
                    f'{camp["goal"]}</span>'
                )
            st.markdown(
                f'<div style="padding:7px 0;">'
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.82rem;font-weight:600;'
                f'color:{COLORS["black"]};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
                f'max-width:260px;">{camp["name"]}</div>'
                f'<div style="margin-top:3px;">{tags_html or goal_chip}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with row_cols[2]:
            st.markdown(
                f'<div style="display:flex;align-items:center;height:40px;">'
                + channel_badge_html(camp["channel"]) + "</div>",
                unsafe_allow_html=True,
            )

        with row_cols[3]:
            st.markdown(
                f'<div style="display:flex;align-items:center;height:40px;">'
                + phase_badge_html(camp["phase"]) + "</div>",
                unsafe_allow_html=True,
            )

        with row_cols[4]:
            st.markdown(
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.75rem;'
                f'color:{COLORS["black"]};display:flex;align-items:center;height:40px;">'
                f'{camp["assigned_to"]}</div>',
                unsafe_allow_html=True,
            )

        with row_cols[5]:
            delta = (deadline - TODAY).days
            dl_color = (
                COLORS["danger"] if delta <= 0 else
                COLORS["warn"]   if delta <= 2 else
                COLORS["black"]
            )
            overdue_mark = " ⚠" if delta < 0 else ""
            st.markdown(
                f'<div style="padding:7px 0;">'
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
                f'font-weight:600;color:{dl_color};">{deadline.strftime("%b %d")}{overdue_mark}</div>'
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.62rem;'
                f'color:{COLORS["muted"]};">{camp["next_deadline_label"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with row_cols[6]:
            st.markdown(
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.78rem;'
                f'color:{COLORS["black"]};display:flex;align-items:center;height:40px;">'
                f'{camp["send_date"].strftime("%b %d, %Y")}</div>',
                unsafe_allow_html=True,
            )

        with row_cols[7]:
            st.markdown(
                f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.72rem;font-weight:600;'
                f'color:{pri_color};display:flex;align-items:center;height:40px;">'
                f'{camp["priority"]}</div>',
                unsafe_allow_html=True,
            )

        with row_cols[8]:
            btn_label = "▲" if is_selected else "▼"
            if st.button(btn_label, key=f"cd_view_{camp['id']}", type="secondary"):
                st.session_state["cd_selected"] = None if is_selected else camp["id"]
                st.rerun()

        st.markdown(
            f'<div style="border-bottom:1px solid {COLORS["border"]};"></div>',
            unsafe_allow_html=True,
        )

        if is_selected:
            _render_detail_panel(camp)
