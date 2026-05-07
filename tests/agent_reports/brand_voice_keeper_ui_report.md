# UI Diagnostic Report: `brand_voice_keeper`

**Date:** 2026-05-06  
**Layer:** C — UI  
**Page:** `/settings`  
**Component:** Brand Voice settings form (`apps/web/src/app/(dashboard)/settings/page.tsx`, `BrandVoiceSection`)

---

## Field Coverage Cross-Reference

| Field | In DB (`brand_voice`) | Agent accepts? | UI shows? | Classification |
|---|---|---|---|---|
| `tone` | ✅ VARCHAR(255) | ✅ `ctx.params.get("tone")` | ✅ `<Input>` field | **No gap** |
| `vocabulary` | ✅ JSONB array | ✅ `ctx.params.get("vocabulary")` | ✅ Comma-separated input | **No gap** |
| `banned_phrases` | ✅ JSONB array | ✅ `ctx.params.get("banned_phrases")` | ✅ Comma-separated input | **No gap** |
| `style_rules` | ✅ JSONB object | ✅ `ctx.params.get("style_rules")` | ❌ Not rendered | **BUG-UI-003** |
| `target_audience` | ❌ No column | ❌ Not a param | ❌ Not rendered | **FEATURE** |
| `updated_at` | ✅ timestamptz | ❌ Auto-managed | ❌ Display-only | Correct |

---

## Bug: BUG-UI-003 — style_rules not exposed in UI

**Status:** Confirmed  
**Severity:** Medium

**Evidence:**
- DB column `style_rules JSONB` exists in `brand_voice` (confirmed via `\d brand_voice`)
- Agent upserts `style_rules` via `ctx.params.get("style_rules", {})` (line ~38 in `brand_voice_keeper.py`)
- `BrandVoiceSection` state: `tone`, `vocabulary`, `bannedPhrases` — `style_rules` absent
- `useEffect` maps API response but has no `setStyleRules` call
- Mutation payload: `{ tone, vocabulary, banned_phrases }` — `style_rules` never sent

**Impact clarification (corrects original description):**  
Saving the form does NOT corrupt existing `style_rules`. The `PUT /api/v1/brand-voice` handler guards with `if body.style_rules is not None` — omitting the field preserves the DB value. The real impact is visibility/editability only: users cannot read or write `style_rules` through the UI.

**Fix required:** Add a key-value editor for `style_rules` in `BrandVoiceSection`. The PUT endpoint already accepts it — no backend change needed.

---

## Feature gap: target_audience — not a bug

**Status:** FEATURE (unbuilt)  
**Severity:** N/A

`target_audience` was listed in the UI checklist as aspirational. Diagnostic confirms it was never built at any layer:
- No DB column (not in `\d brand_voice` output)
- No agent param
- No UI field

This is a **future feature request**, not a bug. Requires: Alembic migration, agent param addition, UI field.

---

## UI Checklist Results

| Item | Result | Note |
|---|---|---|
| Page /settings loads without console errors | ⬜ Manual | Not yet verified |
| Brand Voice section displays current tone value | ⬜ Manual | Not yet verified |
| Vocabulary terms render as tags or comma list | ⬜ Manual | Not yet verified |
| Banned phrases section shows correct phrase count | ⬜ Manual | Not yet verified |
| Editing tone and saving — value persists after refresh | ⬜ Manual | Not yet verified |
| Adding a vocabulary term — term appears immediately | ⬜ Manual | Not yet verified |
| Style rules section renders key-value pairs | ❌ FAIL | `style_rules` not implemented in form (BUG-UI-003) |
| Target audience field is visible | ❌ FAIL | `target_audience` never built (FEATURE) |
| Target audience accepts free text | ❌ FAIL | `target_audience` never built (FEATURE) |
