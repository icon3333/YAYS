# PRD — Video Feed: 3‑Line Layout + Dedicated Logs Button

## Overview
- Standardize each video feed item to a 3‑line layout.
- Extract Logs into a dedicated small grey button (same geometry as “Read Summary”).
- Keep the current release date formatting (no forced relative dates).

## Layout
- Line 1: Title (single line, truncate with ellipsis). Right side: existing actions (Read Summary, status chips, labels) unchanged in placement.
- Line 2: Duration • Channel • Upload date (use current product formatting exactly).
- Line 3: Left: source tag only — “channel” if from a channel, “manual” if added manually. Right: small grey “Logs” button.

## Behavior
- Logs button opens the existing logs modal.
- Status chips no longer open Logs; they remain informative only.
- Read Summary behavior unchanged.

## Accessibility
- Buttons keyboard accessible with visible focus.
- Truncated title shows full text on hover via title attribute.

## Acceptance Criteria
- Feed items render in 3 lines as specified across breakpoints.
- Line 3 contains only the source tag (left) and the Logs button (right).
- Summary/status chips stay on the right of Line 1 as today.
- Logs modal opens and shows content or empty state.

