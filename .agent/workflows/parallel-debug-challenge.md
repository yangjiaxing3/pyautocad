---
description: Run a parallel agent challenge to debug UI issues, broken links, and UX flows.
---

# Parallel Agent Challenge Mode

This workflow simulates a multi-agent debate to ensure code quality and UX robustness.

## 1. 🕵️ Agent 1: The Simulator (Visual & Functional Check)

- **Role**: Simulate a user clicking through the interface.
- **Action**: View and parse all key HTML files (`Index_Portal.html`, `Index_Creator.html`, `Index_Reviewer.html`).
- **Check**:
  - Are there any unclosed tags?
  - Are `<script>` tags properly terminated?
  - Do `<?= var ?>` injections look correct?
  - **Crucial**: Check `Index_Reviewer.html` for raw code leakage (as reported).

## 2. 😈 Agent 2: The Challenger (UX & Edge Cases)

- **Role**: Play the "Devil's Advocate".
- **Action**: Critique the current flow.
  - "What if the URL param is missing?"
  - "What if the user clicks back?"
  - "Is the 'Jump Board' intuitive?"
  - "Are the filters in Reviewer working?"

## 3. 🧠 Agent 3: The Verifier (Claude Opus 4.5 Mode)

- **Role**: Synthesize findings and approve the fix plan.
- **Action**: Review the findings from Agent 1 & 2 and determine the "Golden Path" for the fix.

## 4. 🛠️ Gemini 3.1 Pro (The Builder)

- **Role**: Execute the code changes.
- **Action**:
  - Fix syntax errors in `Index_Reviewer.html`.
  - Refine Portal links if needed.
  - Ensure all JS is valid.
