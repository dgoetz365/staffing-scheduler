---
name: Fieldwork Scheduler
description: A precise volunteer scheduling workspace with botanical index colors.
colors:
  ink: "#163e36"
  muted: "#4d655c"
  paper: "#f4f5ed"
  surface: "#fffef8"
  line: "#c9d1c5"
  soft: "#e5ebdc"
  accent: "#d8ed9a"
  danger: "#8e3023"
  danger-bg: "#fff0e9"
  focus: "#9b4c08"
typography:
  heading:
    fontFamily: "Segoe UI, Arial, sans-serif"
    fontSize: "2rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Segoe UI, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  control: "5px"
spacing:
  compact: "8px"
  base: "16px"
  section: "28px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: ".6rem .9rem"
---

# Fieldwork design system

## Overview

The surface is an operation screen: the schedule leads, constraints are visible beside it, and publication and requests have separate standard tabs. The user explicitly requested immediate implementation without browser use or further questions. The product and visual direction are inferred from that brief; no rendered review is claimed.

## Direction

The grounded candidates were museum identity manuals, public garden maps, classroom science workbooks, community workshop programs, exhibition catalogs, field survey forms and botanical collection indexes. The seed selected the seventh direction (`seed:b9ba14b33e69b749`). Its restrained botanical index world contributes deep green ink, pale leaf stock, compact named entries and a readable window of time beside every volunteer. It contributes no metaphorical navigation or decorative scientific equipment.

The monochrome marketing challenger loses audience fit and operational clarity; its discipline of supporting each claim with visible proof strengthens the explicit availability roster. The vertical video feed loses both, but strengthens the requirement for an obvious current workspace. The garden map is competitive on audience fit but loses table-like scanability; its discipline of consistent state color is retained. The boarding-pass board is competitive on time reading but too travel-specific; its disciplined tabular numerals are retained. The raked timetable loses both due to skew and material effects; its clear bounded cells reinforce consistent schedule rows. These transfers concern clarity, not decorative motifs.

## Colors

- Ink and primary action: `#163e36`.
- Body secondary text: `#4d655c`.
- Page ground: `#f4f5ed`; content surface: `#fffef8`.
- Secondary surface: `#e5ebdc`; hairline: `#c9d1c5`.
- Masthead edge and count marker: `#d8ed9a`.
- Error text: `#8e3023`; error background: `#fff0e9`.
- Focus outline: `#9b4c08`, 3px with 3px offset.
- Font: Segoe UI / Arial / sans-serif, 16px body. Operational system font rather than an external asset dependency.
- Heading scale: 2rem page, 1.3rem section, 1rem row. Body 1rem, compact labels .85rem.
- Corner radius: 5px. No drop shadows, gradients or decorative imagery.

## Typography

The interface uses an operational system font and a restrained heading scale. Times use tabular numerals. There is no separate display face or third-party font request.

## Layout

The 1500px maximum width uses a schedule/roster split above 1100px. The roster moves below the schedule at smaller widths and becomes a two-column list under 700px. Shift rows move their assignment controls underneath the station at narrow widths. Published issues use a semantic table with its own horizontal scroll region. Standard button/select/textarea controls stay visible and keyboard-accessible.

## Elevation & Depth

Flat tonal layers distinguish work areas; there are no shadows or blur effects.

## Shapes

Controls and tonal areas use 5px corners. Navigation tabs use square corners and a 3px selected underline.

## Components

Tab selection uses aria-selected, roving tabIndex and the arrow, Home, and End keys. Status copy names what changed or why an attempt failed. Disabled publishing pairs with coverage copy explaining the open places. Mutations expose a busy state and avoid repeat clicks. All changing names, reasons and status text are inserted through textContent.

The signature is the volunteer field-note roster: each entry places eligible roles immediately above its exact available window, making the scheduler's constraints readable without opening a detail panel. Motion is limited to brief button-state changes and removed for reduced-motion preferences.

## Do's and Don'ts

- Do show named roles and time windows beside the schedule.
- Do preserve native keyboard controls and visible focus.
- Don't use color as the only expression of a status.
- Don't hide publication history behind the editable draft.
