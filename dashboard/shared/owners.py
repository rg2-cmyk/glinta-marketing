"""
Universal owner teams and task roles used across all phases.
Import TEAMS, ROLES, and render_assignment_widget() anywhere in the app.
"""
import streamlit as st
from shared.styles import COLORS

# ── Teams ─────────────────────────────────────────────────────────────────────
TEAMS = [
    "Executive Leadership",
    "Marketing Director",
    "Marketing Strategy",
    "Brand & Social",
    "Growth Marketing",
    "Retail Marketing",
    "Merchandising & Planning",
    "Design",
    "Data",
]

# ── Task roles ────────────────────────────────────────────────────────────────
ROLES = [
    "Task Owner",
    "Reviewer",
    "Input Provider",
    "Decision Maker",
    "Other",
]

ROLE_DESCRIPTIONS = {
    "Task Owner":      "Accountable for completing and delivering this task",
    "Reviewer":        "Reviews output and provides structured feedback",
    "Input Provider":  "Provides required inputs (data, assets, approvals)",
    "Decision Maker":  "Has final sign-off authority",
    "Other":           "Custom role — specify below",
}

ROLE_COLORS = {
    "Task Owner":     COLORS["black"],
    "Reviewer":       "#4A90D9",
    "Input Provider": "#F5A623",
    "Decision Maker": "#9B59B6",
    "Other":          COLORS["muted"],
}


def role_badge(role: str) -> str:
    """Returns an HTML badge for a given role."""
    color = ROLE_COLORS.get(role, COLORS["muted"])
    txt   = "#fff" if color not in [COLORS["yellow"], COLORS["lavender"]] else COLORS["black"]
    return (
        f'<span style="background:{color};color:{txt};padding:2px 9px;'
        f'border-radius:4px;font-size:0.6rem;font-weight:600;'
        f'font-family:\'Barlow\',sans-serif;white-space:nowrap;">{role}</span>'
    )


def team_badge(team: str) -> str:
    """Returns an HTML badge for a given team."""
    return (
        f'<span style="background:{COLORS["offwhite"]};color:{COLORS["black"]};'
        f'border:1px solid {COLORS["border"]};padding:2px 9px;'
        f'border-radius:4px;font-size:0.6rem;font-weight:500;'
        f'font-family:\'Barlow\',sans-serif;white-space:nowrap;">{team}</span>'
    )


def render_assignment_widget(
    key: str,
    label: str = "Assign owners",
    allow_multiple: bool = True,
    existing = None,
    show_task: bool = False,
):
    """
    Renders a team + role assignment UI.

    Returns a list of assignment dicts:
        Without show_task: [{"team": "Design", "role": "Task Owner", "note": ""}, ...]
        With show_task:    [{"task": "Write copy", "team": "Design", "role": "Task Owner", "note": ""}, ...]

    Args:
        key:            Unique key prefix (avoids widget key collisions).
        label:          Section label shown above the widget.
        allow_multiple: If True, shows an "Add another" button.
        existing:       Pre-populated assignments (list of dicts).
        show_task:      If True, adds a "Task" description field per row.
    """
    state_key = f"_assign_{key}"
    default_row = {"task": "", "team": TEAMS[0], "role": ROLES[0], "note": ""} if show_task \
                  else {"team": TEAMS[0], "role": ROLES[0], "note": ""}
    if state_key not in st.session_state:
        st.session_state[state_key] = existing or [dict(default_row)]

    assignments = st.session_state[state_key]

    st.markdown(
        f'<div style="font-family:\'Barlow\',sans-serif;font-size:0.62rem;'
        f'letter-spacing:0.08em;text-transform:uppercase;color:{COLORS["muted"]};'
        f'font-weight:600;margin-bottom:6px;">{label}</div>',
        unsafe_allow_html=True,
    )

    to_remove = None
    for i, assignment in enumerate(assignments):
        if show_task:
            cols = st.columns([3, 2.5, 2, 2.5, 0.5])
            with cols[0]:
                assignment["task"] = st.text_input(
                    "Task" if i == 0 else " ",
                    value=assignment.get("task", ""),
                    key=f"{key}_task_{i}",
                    label_visibility="visible" if i == 0 else "hidden",
                    placeholder="e.g. Review copy draft",
                )
            team_col, role_col, desc_col, rm_col = cols[1], cols[2], cols[3], cols[4]
        else:
            cols = st.columns([3, 2, 3, 0.5])
            team_col, role_col, desc_col, rm_col = cols[0], cols[1], cols[2], cols[3]

        with team_col:
            assignment["team"] = st.selectbox(
                "Team" if i == 0 else " ",
                TEAMS,
                index=TEAMS.index(assignment["team"]) if assignment["team"] in TEAMS else 0,
                key=f"{key}_team_{i}",
                label_visibility="visible" if i == 0 else "hidden",
            )
        with role_col:
            assignment["role"] = st.selectbox(
                "Role" if i == 0 else " ",
                ROLES,
                index=ROLES.index(assignment["role"]) if assignment["role"] in ROLES else 0,
                key=f"{key}_role_{i}",
                label_visibility="visible" if i == 0 else "hidden",
            )
        with desc_col:
            if assignment["role"] == "Other":
                assignment["note"] = st.text_input(
                    "Specify role" if i == 0 else " ",
                    value=assignment.get("note", ""),
                    key=f"{key}_note_{i}",
                    label_visibility="visible" if i == 0 else "hidden",
                    placeholder="Describe the role…",
                )
            else:
                desc = ROLE_DESCRIPTIONS.get(assignment["role"], "")
                st.markdown(
                    f'<div style="padding:{"28px" if i == 0 else "8px"} 0 0;'
                    f'font-size:0.75rem;color:{COLORS["muted"]};">{desc}</div>',
                    unsafe_allow_html=True,
                )
                assignment["note"] = ""
        with rm_col:
            remove_label = "×" if len(assignments) > 1 else " "
            if i == 0:
                st.markdown('<div style="height:22px;"></div>', unsafe_allow_html=True)
            if st.button(remove_label, key=f"{key}_rm_{i}",
                         type="secondary", disabled=(len(assignments) <= 1)):
                to_remove = i

    if to_remove is not None:
        assignments.pop(to_remove)
        st.session_state[state_key] = assignments
        st.rerun()

    if allow_multiple:
        btn_label = "+ Add task" if show_task else "+ Add owner"
        if st.button(btn_label, key=f"{key}_add", type="secondary"):
            assignments.append(dict(default_row))
            st.session_state[state_key] = assignments
            st.rerun()

    st.session_state[state_key] = assignments
    return assignments


def assignment_summary_html(assignments: list) -> str:
    """Renders a compact inline summary of assignments as HTML badges."""
    if not assignments:
        return f'<span style="color:{COLORS["muted"]};font-size:0.75rem;">No owners assigned</span>'
    parts = []
    for a in assignments:
        role_note = a.get("note") or a.get("role", "")
        role_disp = role_note if a["role"] == "Other" else a["role"]
        task_name = a.get("task", "").strip()
        task_html = (
            f'<span style="font-size:0.7rem;font-weight:600;font-family:\'Barlow\','
            f'sans-serif;">{task_name} — </span>'
        ) if task_name else ""
        parts.append(
            f'<div style="display:flex;align-items:center;gap:4px;margin-bottom:3px;">'
            f'{task_html}{team_badge(a["team"])} {role_badge(role_disp)}'
            f'</div>'
        )
    return '<div style="display:flex;flex-direction:column;">' + "".join(parts) + "</div>"
