"""
Google Drive / Docs integration for Glinta Generation copy.

Auth: Application Default Credentials (same `gcloud auth application-default login`
used by the rest of the project). Uses the user's own credentials — no service
account impersonation needed since the target folder lives in the user's Drive.

Public API
----------
create_copy_doc(camp, copy_data)  → (doc_id, view_url)
update_copy_doc(doc_id, camp, copy_data) → view_url
read_copy_doc(doc_id)             → dict(subject, email, sms, tone, cta, offer,
                                         highlights, preview)
doc_view_url(doc_id)              → str
"""

import re
import requests as http_req
import google.auth
import google.auth.transport.requests

# ── Config ────────────────────────────────────────────────────────────────────
FOLDER_ID = "1B01MZT_jtxWZS92NqA1mAORUF111HsbD"

# Docs and Drive operations use YOUR credentials (not the service account)
# because Google Docs/Drive storage quota is tied to your account.
# Run once to re-auth with these scopes:
#   gcloud auth application-default login \
#     --scopes="openid,https://www.googleapis.com/auth/userinfo.email,\
#               https://www.googleapis.com/auth/cloud-platform,\
#               https://www.googleapis.com/auth/drive,\
#               https://www.googleapis.com/auth/documents"
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

# Section markers — written verbatim into the Google Doc; used to parse back.
_SEP             = "═" * 44
SECTION_SUBJECT  = "SUBJECT LINE"
SECTION_EMAIL    = "EMAIL BODY"
SECTION_SMS      = "SMS COPY"
SECTION_BRIEF    = "BRIEF INPUTS"


# ── Auth ──────────────────────────────────────────────────────────────────────
def _get_token() -> str:
    """Return a fresh bearer token using your own ADC credentials (with Drive scope)."""
    creds, _ = google.auth.default(scopes=DRIVE_SCOPES)
    req = google.auth.transport.requests.Request()
    creds.refresh(req)
    return creds.token


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ── Document formatting ───────────────────────────────────────────────────────
def _format_doc(camp: dict, copy_data: dict) -> str:
    """Render copy_data + campaign metadata into structured plain text."""
    status   = copy_data.get("status", "")
    reviewer = copy_data.get("reviewer", "")
    saved_by = copy_data.get("saved_by", "")
    saved_at = copy_data.get("saved_at", "")
    subject  = copy_data.get("subject", "")
    email    = copy_data.get("email", "")
    sms      = copy_data.get("sms", "")
    tone     = copy_data.get("tone", "")
    cta      = copy_data.get("cta", "")
    offer    = copy_data.get("offer", "")
    hl       = copy_data.get("highlights", "")
    preview  = copy_data.get("preview", "")

    send_date = camp.get("send_date", "")
    if hasattr(send_date, "strftime"):
        send_date = send_date.strftime("%B %d, %Y")

    meta = f"Campaign: {camp.get('name','')}  |  Channel: {camp.get('channel','').upper()}  |  Send: {send_date}"
    if status:
        meta += f"  |  Status: {status}"
    if reviewer:
        meta += f"  |  Reviewer: {reviewer}"
    if saved_by:
        meta += f"  |  By: {saved_by}"
    if saved_at:
        meta += f"  |  Saved: {saved_at}"

    def _section(name, body):
        return f"\n{_SEP}\n{name}\n{_SEP}\n\n{body}\n"

    lines = [
        f"Glinta Copy — {camp.get('name','')}",
        "─" * 52,
        "",
        meta,
        _section(SECTION_SUBJECT, subject),
        _section(SECTION_EMAIL, email),
        _section(SECTION_SMS, sms),
        _section(
            SECTION_BRIEF,
            "\n".join([
                f"Tone: {tone}",
                f"CTA: {cta}",
                f"Offer: {offer}",
                f"Highlights: {hl}",
                f"Preview: {preview}",
            ]),
        ),
    ]
    return "\n".join(lines)


# ── Document parsing (sync-back) ──────────────────────────────────────────────
def _parse_doc(text: str) -> dict:
    """Parse the structured doc text back into copy fields."""

    def _section(name):
        pattern = (
            r"═+\n" + re.escape(name) + r"\n═+\n\n"
            r"(.*?)"
            r"(?=\n═+\n[A-Z ]+\n═+|\Z)"
        )
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else ""

    def _kv(block, key):
        for line in block.splitlines():
            if line.startswith(f"{key}:"):
                return line[len(key) + 1:].strip()
        return ""

    brief = _section(SECTION_BRIEF)
    return {
        "subject":    _section(SECTION_SUBJECT),
        "email":      _section(SECTION_EMAIL),
        "sms":        _section(SECTION_SMS),
        "tone":       _kv(brief, "Tone"),
        "cta":        _kv(brief, "CTA"),
        "offer":      _kv(brief, "Offer"),
        "highlights": _kv(brief, "Highlights"),
        "preview":    _kv(brief, "Preview"),
    }


# ── Public API ────────────────────────────────────────────────────────────────
def create_copy_doc(
    camp: dict,
    copy_data: dict,
    folder_id: str = FOLDER_ID,
) -> tuple:
    """
    Create a new Google Doc in folder_id with the campaign copy.
    Returns (doc_id, view_url).
    """
    token   = _get_token()
    hdrs    = _headers(token)
    title   = f"Glinta Copy — {camp.get('name','Campaign')}"
    content = _format_doc(camp, copy_data)

    # 1. Create an empty Google Doc in the target folder
    r = http_req.post(
        "https://www.googleapis.com/drive/v3/files",
        headers=hdrs,
        json={
            "name":     title,
            "mimeType": "application/vnd.google-apps.document",
            "parents":  [folder_id],
        },
        timeout=20,
    )
    r.raise_for_status()
    doc_id = r.json()["id"]

    # 2. Insert content via the Docs API
    http_req.post(
        f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
        headers=hdrs,
        json={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        timeout=20,
    ).raise_for_status()

    return doc_id, doc_view_url(doc_id)


def update_copy_doc(doc_id: str, camp: dict, copy_data: dict) -> str:
    """
    Overwrite the body of an existing Google Doc with fresh copy.
    Returns the view URL.
    """
    token   = _get_token()
    hdrs    = _headers(token)
    content = _format_doc(camp, copy_data)

    # Get the current body to find its end index
    doc_resp = http_req.get(
        f"https://docs.googleapis.com/v1/documents/{doc_id}",
        headers=hdrs,
        timeout=20,
    )
    doc_resp.raise_for_status()
    end_index = doc_resp.json()["body"]["content"][-1]["endIndex"] - 1

    reqs = []
    if end_index > 1:
        reqs.append(
            {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index}}}
        )
    reqs.append(
        {"insertText": {"location": {"index": 1}, "text": content}}
    )

    http_req.post(
        f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
        headers=hdrs,
        json={"requests": reqs},
        timeout=20,
    ).raise_for_status()

    return doc_view_url(doc_id)


def read_copy_doc(doc_id: str) -> dict:
    """
    Read a Google Doc and parse it back into copy fields.
    Returns dict with keys: subject, email, sms, tone, cta, offer, highlights, preview.
    """
    token = _get_token()
    r = http_req.get(
        f"https://docs.googleapis.com/v1/documents/{doc_id}",
        headers=_headers(token),
        timeout=20,
    )
    r.raise_for_status()

    # Flatten paragraph text from the doc body
    parts = []
    for element in r.json().get("body", {}).get("content", []):
        para = element.get("paragraph")
        if not para:
            continue
        line = "".join(
            e.get("textRun", {}).get("content", "")
            for e in para.get("elements", [])
        )
        parts.append(line)

    return _parse_doc("".join(parts))


def doc_view_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit"


# ── Brief doc formatting ──────────────────────────────────────────────────────
def _format_brief_doc(camp: dict, brief_data: dict) -> str:
    """Render design brief fields into structured plain text for a Google Doc."""
    send_date = camp.get("send_date", "")
    if hasattr(send_date, "strftime"):
        send_date = send_date.strftime("%B %d, %Y")

    def _section(name, body):
        return f"\n{_SEP}\n{name}\n{_SEP}\n\n{body}\n"

    review = brief_data.get("review", {})
    review_line = ""
    if review.get("status"):
        review_line = (
            f"Review status: {review['status']}"
            + (f"  |  Reviewer: {review['reviewer']}" if review.get("reviewer") else "")
            + (f"  |  Approved by: {review['approved_by']}" if review.get("approved_by") else "")
        )

    meta_parts = [
        f"Campaign:  {camp.get('name', '')}",
        f"Channel:   {camp.get('channel', '').upper()}",
        f"Send date: {send_date}",
        f"Segment:   {camp.get('segment', '—')}",
        f"Audience:  {brief_data.get('audience', '—')}",
        f"Owner:     {brief_data.get('owner', '—')}",
    ]
    if review_line:
        meta_parts.append(review_line)

    creative_parts = [
        f"Objective:\n{brief_data.get('objective', '')}",
        f"\nSubject line (approved):\n{brief_data.get('subject', '')}",
        f"\nPreview / preheader:\n{brief_data.get('preview', '')}",
        f"\nTone & style direction:\n{brief_data.get('tone', '')}",
        f"\nPrimary CTA: {brief_data.get('cta', '')}",
    ]
    if brief_data.get("offer"):
        creative_parts.append(f"Offer / promo code: {brief_data['offer']}")

    lines = [
        f"Glinta Design Brief — {camp.get('name', '')}",
        "─" * 52,
        "",
        "\n".join(meta_parts),
        _section("CREATIVE DIRECTION", "\n".join(creative_parts)),
        _section("REQUIRED ASSETS", brief_data.get("assets", "")),
        _section("IMAGE REFERENCES", brief_data.get("refs", "")),
        _section("NOTES FOR DESIGN", brief_data.get("notes", "")),
    ]

    if brief_data.get("email") or brief_data.get("sms"):
        approved_copy = ""
        if brief_data.get("email"):
            approved_copy += f"EMAIL BODY:\n\n{brief_data['email']}\n"
        if brief_data.get("sms"):
            approved_copy += f"\nSMS COPY:\n\n{brief_data['sms']}\n"
        lines.append(_section("APPROVED COPY", approved_copy))

    if brief_data.get("asana_task"):
        asana = brief_data["asana_task"]
        lines.append(_section(
            "ASANA TASK",
            "\n".join([
                f"Project:  {asana.get('project', '')}",
                f"Section:  {asana.get('section', '')}",
                f"Task:     {asana.get('task', '')}",
                f"Owner:    {asana.get('owner', '')}",
                f"Due:      {asana.get('due', '')}",
            ]),
        ))

    return "\n".join(lines)


def create_brief_doc(
    camp: dict,
    brief_data: dict,
    folder_id: str = FOLDER_ID,
) -> tuple:
    """
    Create a new Google Doc design brief in folder_id.
    brief_data keys: objective, subject, preview, tone, cta, offer, assets,
                     refs, notes, email, sms, audience, owner, review, asana_task
    Returns (doc_id, view_url).
    """
    token   = _get_token()
    hdrs    = _headers(token)
    title   = f"Glinta Brief — {camp.get('name', 'Campaign')}"
    content = _format_brief_doc(camp, brief_data)

    r = http_req.post(
        "https://www.googleapis.com/drive/v3/files",
        headers=hdrs,
        json={
            "name":     title,
            "mimeType": "application/vnd.google-apps.document",
            "parents":  [folder_id],
        },
        timeout=20,
    )
    r.raise_for_status()
    doc_id = r.json()["id"]

    http_req.post(
        f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
        headers=hdrs,
        json={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        timeout=20,
    ).raise_for_status()

    return doc_id, doc_view_url(doc_id)


def update_brief_doc(doc_id: str, camp: dict, brief_data: dict) -> str:
    """Overwrite an existing brief Google Doc with fresh content."""
    token   = _get_token()
    hdrs    = _headers(token)
    content = _format_brief_doc(camp, brief_data)

    doc_resp = http_req.get(
        f"https://docs.googleapis.com/v1/documents/{doc_id}",
        headers=hdrs,
        timeout=20,
    )
    doc_resp.raise_for_status()
    end_index = doc_resp.json()["body"]["content"][-1]["endIndex"] - 1

    reqs = []
    if end_index > 1:
        reqs.append(
            {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index}}}
        )
    reqs.append({"insertText": {"location": {"index": 1}, "text": content}})

    http_req.post(
        f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
        headers=hdrs,
        json={"requests": reqs},
        timeout=20,
    ).raise_for_status()

    return doc_view_url(doc_id)
