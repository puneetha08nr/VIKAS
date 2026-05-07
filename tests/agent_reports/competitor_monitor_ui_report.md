# UI Diagnostic Report: `competitor_monitor`

**Date:** 2026-05-06  
**Layer:** C — UI  
**Page:** `/competitors`  
**Component:** Competitor list + add competitor form (`apps/web/src/app/(dashboard)/competitors/page.tsx`)

---

## UI Checklist Results

| Item | Result | Note |
|---|---|---|
| Page /competitors shows competitor list with domain names | ✅ FIXED | Domains display correctly; no https:// prefix after BUG-UI-005 fix |
| Adding a new competitor domain — appears in list | ✅ FIXED | Domain normalised before API call; duplicate check before submit |
| last_crawled_at timestamp updates after monitor run | ✅ PASS | `CrawlStatus` component shows "Done · {time ago}" with green dot |
| Delete competitor removes row without page refresh | ⬜ Manual | Not yet verified in browser — requires manual check |

---

## Bugs Found and Fixed

| ID | Severity | Summary | Status |
|---|---|---|---|
| BUG-UI-005 | Medium | Domain stored with `https://` prefix; normalisation incomplete | ✅ FIXED |
| BUG-UI-006 | Medium | Duplicate competitor not detected client-side; no user feedback | ✅ FIXED |
| BUG-UI-009 | Low | No crawl status indicator; plain text "never" / time string | ✅ FIXED |
| BUG-UI-010 | Low | Content tab single empty state for both no-data and no-search-match | ✅ FIXED |
| BUG-API-001 | Medium | No domain validation — unreachable/nonexistent domains accepted by API | ✅ FIXED |

---

## Fix Details

### BUG-UI-005 + BUG-UI-006 — Domain normalisation + duplicate check

**Changed:** `AddCompetitorForm` in `competitors/page.tsx`

Added `normaliseDomain()`:
```ts
function normaliseDomain(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .replace(/\/.*$/, '')
}
```

- Applied on form submit before API call
- `existingDomains` prop passed from parent (normalised list of tracked domains)
- Inline duplicate error: `"{domain} is already being tracked."`
- DB cleanup: 2 rows cleaned via `regexp_replace` on existing dirty data

### BUG-UI-009 — Crawl status indicator

**Changed:** `competitors/page.tsx` + DB migration `g0h1i2j3k4l5`

Added `CrawlStatus` component:
- `last_crawled_at IS NULL` → grey "Never crawled"
- `last_crawled_at IS NOT NULL` → green dot + "Done · {time ago}"

Column header: "Last Crawled" → "Status"

DB: `crawl_status VARCHAR(20) DEFAULT 'never'` added (reserved for future worker-set values: `queued`, `crawling`, `done`, `failed`)

### BUG-UI-010 — Content tab empty states

**Changed:** `competitors/page.tsx`

- Tab switch resets `contentSearch` to `''` — content tab always opens unfiltered
- Three-way condition: `contentLoading` → `competitorContent.length === 0` → `filteredContent.length === 0` → data table
- "No competitor content extracted yet. Run competitor monitor to start crawling."
- "No results match your search."

---

## Deferred Items

| Item | Reason |
|---|---|
| Delete without page refresh (verified) | Needs manual browser check — code uses `removeMutation` + `invalidateQueries`, should work |
| `crawl_status` live updates (queued/crawling) | Requires worker to set status; UI dots for these states not yet wired |
