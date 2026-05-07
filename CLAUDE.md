# Glinta Marketing — Project Guidelines

> ⚠️ CRITICAL: These rules are NON-NEGOTIABLE and apply to EVERY chat session, every file, and every component in this project. No exceptions. If a rule conflicts with a default behavior, this file wins.

## Project Goal
Prototype automating Glinta's Email and SMS Marketing process.
Output: a shareable link with working, interactive sections.

## Brand Colors
- Lime green: `#caf30b`
- Yellow: `#f5f000`
- Soft purple: `#e8c5ff`

- MUST only use these colors sparingly — for chart highlights, hover states, and clicked/active states only
- NEVER use these as backgrounds or dominant UI colors

## Colors: Text & Background
- MUST always use black (`#000000`) for text
- MUST always use white (`#ffffff`) or near-white (`#f7f7f7`) for backgrounds
- NEVER use brand colors as backgrounds

## Number Formatting: Revenue
- MUST always prefix revenue with `$`
- MUST shorten millions to `$X.XM` (1 decimal place, e.g. `$3.2M`)
- MUST shorten thousands to `$X.XK` (1 decimal place, e.g. `$847.3K`)
- MUST use the same abbreviation across an entire section or page (all `$M` or all `$K`)
- NEVER mix `$M` and `$K` within the same section or page

## Team & Ownership
- MUST only use the following names for any owner, assignee, or approver field anywhere in this project
- NEVER invent, generate, or use placeholder names (e.g. "John Smith", "Sarah", "User 1")
- This applies everywhere: campaign owners, task assignees, approvers, design briefs, etc.

Valid owners:
  - Leadership
  - Marketing Director
  - Marketing Strategy
  - Brand & Social
  - Growth Marketing
  - Retail Marketing
  - Merchandising & Planning
  - Design
  - Operations
  - Data

## Task Types
- MUST use one of the following task types when adding or assigning tasks:
  - Review
  - Revise
  - Provide input
  - Approve
  - Handoff
  - Other (free-text custom input box)
- NEVER create or display task types outside of this list

## Campaign Data Source
- MUST pull all upcoming/planned campaign data from the Google Sheet below
- NEVER use mock, hardcoded, or invented campaign data anywhere in this project
- If the Google Sheet is not yet connected, MUST surface a clear integration placeholder — NEVER invent data

Google Sheet: https://docs.google.com/spreadsheets/d/1UOz9J-V-F1grQ86_KPypI7yizx6dyQWyuKdJdU-8YNQ/edit?gid=0#gid=0

## Core Design Principles
- MUST let neutrals dominate — white/off-white backgrounds, black text, gray borders throughout
- MUST use accent colors (yellow `#f5f000`, lavender `#e8c5ff`, lime `#caf30b`) at most once or twice per page — NEVER as fills for large areas
- NEVER use Barlow Condensed outside of page titles (h1) — all other text MUST use Barlow
- MUST prioritise user-friendliness — everything must be clearly readable, well-spaced, never crowded

## Typography
- h1 (page titles): Barlow Condensed only
- h2 (section headers): Barlow 700, uppercase, no fills
- h3 (sub-headers): Barlow 600, muted gray
- KPI group labels: Barlow 600
- KPI values: Barlow 700
- Benchmark cards: Barlow 600, muted gray
- Modal campaign name: Barlow 17px / 700
- Modal category label: Barlow 600
- Modal KPI values: Barlow 700
- Gantt row labels: Barlow 13px / 500, letter-spacing: 0.02em
- Gantt section headers: Barlow 600
- Gantt month headers: Barlow 600, dark background
- Gantt week labels: Barlow 500

## Colors
- Active tab pill: yellow fill ✅ (one intentional accent use)
- Gantt month header: dark (`#1a1a1a`) background + white text
- Gantt week header: off-white background, gray text
- Gantt current week highlight: yellow background (one accent use)
- Monthly calendar day headers: off-white background, muted gray text
- Monthly calendar email chips: dark (`#1a1a1a`) background + white text
- Monthly calendar SMS chips: off-white, gray border
- Email channel pills: dark (`#1a1a1a`) background + white text
- SMS channel pills: off-white, gray border
- Segment type badges (VIP/Winback/Geo etc.): MUST use neutral gray or plain text — NEVER multi-color fills
- Priority badges: plain colored text only — NEVER colored background fills
- Campaign theme tags: off-white fill, gray text
- Modal close button: off-white background, dark gray text
- Modal KPI cards: off-white background, gray border
- Modal divider: 1px solid `#E4E4E4`
- Category performance chart: neutral grays + muted blues/teals/terracottas — NEVER multi-color palette
- "Suggested" segment badge: neutral — NEVER bright green
- Behavioral segment cards: white background, gray border

## Borders & Cards
- MUST use 1px solid `#E4E4E4` for all card borders — NEVER 2px solid black
- Border radius: 8px throughout
- Pipeline cards: thin gray border
- Segment summary box: 1px gray border
- Modal: 1px gray border, soft shadow
- Metric cards: white background, 1px gray border
- Dividers: 1px solid `#E4E4E4` throughout

## Calendar-Specific
- Monthly chip font size: 11px minimum
- Monthly chip padding: 3px 6px
- Today cell highlight: soft yellow tint + 1px muted border — NEVER yellow fill + 2px black border
- Gantt row label padding: 7px 8px
- Gantt row label line-height: 1.4
- Gantt "today" column: very subtle tint (`#fffff5`) — NEVER yellow fill

## What Must Be Kept (Approved Designs)
- Green-gradient bar chart on Performance tab
- Category performance table colors and interaction
- Overall Gantt calendar layout and structure
- SMS dot indicator in lavender (small accent use — approved)

## Transparency & Explainability
- MUST explain the rationale for all recommendations made anywhere in the prototype
- MUST add hover tooltips on all data points explaining where the data comes from and how it is calculated
- MUST automatically track and display who saved, deleted, or edited any information across all tabs

## Spacing & Typography
- MUST keep maximum font size at 16px
- MUST keep minimum font size at 9px
- MUST ensure all text fits its allocated space — NEVER let text wrap onto a second line
- MUST give every element sufficient padding and spacing so labels, legends, and values are clearly readable
