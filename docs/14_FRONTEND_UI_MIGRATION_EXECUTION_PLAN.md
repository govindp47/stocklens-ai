# 14_FRONTEND_UI_MIGRATION_EXECUTION_PLAN.md

> **Document purpose:** Guide a full UI refactor of the StockLens AI frontend to bring it into complete visual alignment with `docs/00_PRODUCT_SPECIFICATION.md` — without touching any business logic, API contracts, state management, or backend integrations.

---

## 1. MIGRATION OVERVIEW

### Current UI Limitations (based on codebase analysis)

| # | Limitation |
|---|-----------|
| 1 | **Panel layout** uses a generic 2-column grid (`grid grid-cols-1 md:grid-cols-2`) — does not implement the spec's intentional Row 1–4 panel arrangement (Stock+Chart, News+Sentiment, Events+Insight, DataSources full-width) |
| 2 | **No "Analyze Another Ticker" affordance** rendered after pipeline completion |
| 3 | **No global partial-failure banner** ("Some data could not be retrieved. Report may be incomplete.") |
| 4 | **No step-entry animation** in `ReasoningViewer` — steps appear without the spec-required slide-in or fade-in |
| 5 | **No panel fade-in animation** as individual panels receive data — all panels render with static visibility |
| 6 | **No price direction entrance animation** on `PriceDirection` component |
| 7 | **Ticker validator regex** (`^[A-Za-z]{1,10}`) excludes numeric characters in exchange qualifiers; spec says alphanumeric + periods up to 12 chars |
| 8 | **Docs page** has no sidebar navigation — spec requires a sidebar with clickable endpoint anchors |
| 9 | **News articles** lack deduplication count badge when multiple articles are merged |
| 10 | **Sentiment Panel** lacks an "emerging concern" callout for sudden negative article spikes |
| 11 | **Reasoning Viewer** does not show "Using: OpenAI [model name]" indicator when OpenAI key is active |
| 12 | **Empty state** on first load lacks the spec's one-sentence system description and example ticker placeholder text |
| 13 | **Header area** lacks product tagline; footer disclaimer visibility is not validated at all viewport sizes |

### Target UI Goals (from product spec)

- Landing page has a clear empty state with system description and example tickers
- Analysis input auto-uppercases, supports alphanumeric + periods, max 12 chars, Enter submits
- Panels render progressively in spec-defined Row order, each fading in as data arrives
- Agent Reasoning Viewer streams steps with slide-in animation and model indicator
- All panels have proper empty/partial/failure states and spec-defined copy
- Sentiment Panel includes emerging-concern callout
- News articles include deduplication count where applicable
- Docs page has sidebar anchor navigation
- Responsive at ≥1024px (multi-col), 768–1023px (two-col), <768px (single-col)
- WCAG 2.1 AA throughout (color not sole differentiator, 44px touch targets, focus rings)

### Migration Scope

**In scope:** UI components, layouts, styling, theming, spacing, typography, colors, animations, copy strings, ARIA labels.

**Out of scope (non-negotiable):** Business logic, API contracts, Zustand store slices, custom hooks (`useAnalysis`, `useSSEStream`), lib utilities, type definitions, backend integrations.

### Risks

| Risk | Mitigation |
|------|-----------|
| Breaking SSE-driven progressive panel rendering while adding animations | Animate via CSS transitions keyed off store state, never re-wire data flow |
| Recharts SSR incompatibility when refactoring chart layout | Keep `PriceTrendChartClient` as separate dynamic import with `ssr: false` |
| Docs page sidebar breaking the Server Component pattern | Implement sidebar as a pure CSS/HTML scroll-spy; no client hooks needed |
| Ticker validator regex change causing false positives | Validate against spec precisely: `^[A-Z0-9]{1,12}(\.[A-Z]{1,3})?$` in display context only |

---

## 2. UI STRUCTURE MAPPING

### Screen Mapping

| Current | Target (spec) | Delta |
|---------|--------------|-------|
| Single route `/` with Playground | Same — SPA | No change |
| `/docs` route as RSC | Same — static docs page | Add sidebar nav |
| Settings as Radix Dialog modal | Same — modal via gear icon | Minor copy/layout tweaks |

### Panel Arrangement

| Row | Spec layout | Current layout | Status |
|-----|------------|---------------|--------|
| Row 1 | Stock Overview (left) + Price Trend Chart (right) | Col 1 + Col 2 | ❌ Order not guaranteed |
| Row 2 | News Summary (wider, left) + Sentiment (narrower, right) | Col 1 + Col 2 | ❌ Equal columns; ratio wrong |
| Row 3 | Events (left) + AI Insight (right) | Col 1 + Col 2 | ✅ Acceptable |
| Row 4 | Data Sources (full width) | `col-span-2` ✅ | ✅ Already full-width |

### What Stays vs What Changes

| Element | Decision |
|---------|---------|
| Tailwind color tokens (brand, sentiment) | **KEEP** — already WCAG-compliant |
| Inter + JetBrains Mono fonts | **KEEP** |
| Zustand store structure | **KEEP** (out of scope) |
| `useAnalysis` / `useSSEStream` hooks | **KEEP** (out of scope) |
| Recharts `PriceTrendChartClient` | **KEEP** — only adjust container sizing |
| ReportGrid column structure | **CHANGE** — implement Row 1–4 layout with correct col spans |
| Panel skeleton & error states | **KEEP** — refine copy strings only |
| Disclaimer component | **KEEP** — verify always-visible at all breakpoints |

---

## 3. DESIGN SYSTEM EXTRACTION

### Color System (derived from current tokens + spec requirements)

```css
/* Already defined in app/globals.css — KEEP AS-IS */
--brand-50:  210 100% 97%   /* tinted backgrounds */
--brand-500: 210 100% 50%   /* primary actions, links */
--brand-900: 210 100% 20%   /* hover states */
--sentiment-positive: 142 76% 36%   /* green — always paired with icon */
--sentiment-neutral:  43  96% 56%   /* amber — always paired with icon */
--sentiment-negative: 0   84% 60%   /* red — always paired with icon */
```

No new colors needed. Spec does not define a palette; existing tokens are compliant.

### Typography (existing, verify usage consistency)

| Role | Token | Usage |
|------|-------|-------|
| Product name | `text-xl font-bold` | Header |
| Panel headings | `text-sm font-semibold` | Panel headers |
| Body / data labels | `text-sm` | Metric labels |
| Large price display | `text-2xl font-bold` | Stock price |
| Monospace | `font-mono text-xs` | Code blocks, tickers |
| Disclaimer | `text-xs` | Footer / banner |

### Spacing

Existing Tailwind scale is sufficient. No new spacing tokens needed.

### Animation Tokens (new — to be added to `globals.css`)

```css
@keyframes fade-in-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes slide-in-left {
  from { opacity: 0; transform: translateX(-8px); }
  to   { opacity: 1; transform: translateX(0); }
}
.animate-fade-in-up   { animation: fade-in-up   0.3s ease-out forwards; }
.animate-slide-in-left{ animation: slide-in-left 0.25s ease-out forwards; }
```

---

## 4. COMPONENT STANDARDIZATION PLAN

| Component | Current State | Required Change |
|-----------|-------------|----------------|
| **TickerInput** | Good base; regex narrow | Update validation pattern; ensure max=12; add "Try: AAPL…" hint text; verify auto-uppercase |
| **AnalyzeButton** | Loading state good | Add "Analyze Another" affordance in `complete` status |
| **Panel** | Solid base | No structural change; add `animate-fade-in-up` when transitioning from skeleton → content |
| **PanelSkeleton** | Functional | No change |
| **ReasoningViewer** | Good structure | Add `animate-slide-in-left` per step; add model indicator line |
| **ReportGrid** | Generic 2-col | Reimplement as Row 1–4 explicit layout |
| **StockOverviewPanel** | Complete | Minor: verify "N/A" fallback for all fields |
| **NewsSummaryPanel** | Good | Add deduplication count badge |
| **SentimentPanel** | Good | Add emerging-concern callout block |
| **EventsPanel** | Good | Verify categorization labels match spec |
| **InsightPanel** | Good | Verify all 6 sections labeled; insufficient-data copy |
| **DataSourcesPanel** | Good | Verify grouping (Market Data / News Sources) labels |
| **SettingsModal** | Good | Add "Using: [model]" indicator display |
| **Disclaimer** | Good | Verify always-visible without scroll at all breakpoints |
| **EndpointBlock (docs)** | Good | No change |
| **CodeBlock (docs)** | Good | No change |
| **GlobalFailureBanner** | **MISSING** | **NEW** component for mid-pipeline failure |
| **DocsLayout (sidebar)** | **MISSING** | **NEW** sidebar nav component for `/docs` |

---

## 5. SCREEN-BY-SCREEN MIGRATION

### Screen 1: Landing / Playground (Empty State)

**Current:** Shows ticker input + AnalyzeButton. No system description, no example hint text prominent.  
**Required changes:**

- Add one-sentence system description above or near input
- Make example ticker hint ("Try: AAPL, TSLA, NVDA") visually prominent below input
- Ensure no panels visible until analysis triggered

### Screen 2: Landing / Playground (Post-Analysis State)

**Current:** 2-column grid with 8 panels in arbitrary order.  
**Required changes:**

- Row 1: Stock Overview (col-span 1) + Price Trend Chart (col-span 1)
- Row 2: News Summary (col-span 7/12) + Sentiment (col-span 5/12) — or use `lg:col-span-7` / `lg:col-span-5`
- Row 3: Events (col-span 1) + AI Insight (col-span 1)
- Row 4: Data Sources (full width)
- Reasoning Viewer persistent above or alongside grid
- Add "Analyze Another Ticker" button affordance after completion
- Add GlobalFailureBanner when `status === 'failed'` (partial data scenario)

### Screen 3: API Documentation

**Current:** Single-column RSC, no sidebar.  
**Required changes:**

- Add sidebar with anchor links to each endpoint section
- Sidebar sticky on scroll (desktop only)
- Mobile: sidebar collapses or stacks above content

### Screen 4: Settings Modal

**Current:** OpenAI key input, Save/Clear buttons, explanatory note.  
**Required changes:**

- Add display of active model name: "Currently using: [Local Ollama / OpenAI gpt-4o]"
- Verify copy strings match spec exactly

---

## 6. TASK BREAKDOWN

---

### Task ID: UI-001

**Title:** Finalize design token system — animation keyframes and global CSS additions

**Phase:** 0 — Design Tokens & Theme

**Subsystem:** Global styles

**Description:**
Add `fade-in-up` and `slide-in-left` CSS keyframe animations as Tailwind-compatible utility classes to `app/globals.css`. These will be referenced by panels and ReasoningViewer steps in later tasks. Also verify existing color/font tokens are complete and no orphaned CSS variables exist.

**Scope Boundaries**

Files affected:

- `frontend/app/globals.css`
- `frontend/tailwind.config.ts`

Modules affected: Global stylesheet, Tailwind theme extension

Explicitly NOT touching: Any component `.tsx` file, Zustand store, hooks

**Implementation Steps**

1. Open `app/globals.css` and add `@keyframes fade-in-up` and `@keyframes slide-in-left` definitions in the base layer
2. Add `.animate-fade-in-up` and `.animate-slide-in-left` utility classes using the keyframes
3. In `tailwind.config.ts`, add `animation` entries: `'fade-in-up': 'fade-in-up 0.3s ease-out forwards'` and `'slide-in-left': 'slide-in-left 0.25s ease-out forwards'` under `extend`
4. Verify existing CSS custom properties (brand, sentiment, background, foreground, border) are all present and consistent between light and dark mode blocks

**User Action Steps**

- None; visual effect only appears when components consume the classes in later tasks

**Data Impact:** None

**Test Plan:**

- Open browser DevTools → Elements → verify keyframes registered
- Apply class manually to a div; confirm animation plays
- Run `npm run build` — confirm no Tailwind purge removes the classes

**Acceptance Criteria:**

- Animation classes available in Tailwind IntelliSense
- No existing styles broken
- Build succeeds

**Rollback Strategy:** Remove the added keyframe blocks from `globals.css` and the animation entries from `tailwind.config.ts`

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/app/globals.css`, `frontend/tailwind.config.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Animations

---

### Task ID: UI-002

**Title:** Ticker input — update validation pattern, placeholder copy, and auto-uppercase enforcement

**Phase:** 1 — Core Components

**Subsystem:** Playground input area

**Description:**
The spec allows alphanumeric characters plus periods, up to 12 characters. The current regex `^[A-Za-z]{1,10}(\.[A-Za-z]{1,3})?$` excludes numeric characters (e.g., `BRK.B`) and caps at 10 base characters. Update the display-facing input attributes and error copy. Also verify the `onInput` handler uppercases all characters. Add a visually prominent example hint below the input.

**Scope Boundaries**

Files affected:

- `frontend/components/playground/TickerInput.tsx`
- `frontend/lib/validators.ts`

Modules affected: Input validation, error message strings

Explicitly NOT touching: `useAnalysis` hook, Zustand store, API call logic

**Implementation Steps**

1. In `lib/validators.ts`: update `isValidTicker` regex to `^[A-Z0-9]{1,12}(\.[A-Z]{1,3})?$` (after uppercase coercion)
2. Update `formatTickerError` string to match spec: `"Please enter a valid stock ticker (e.g., AAPL, TSLA, MSFT)"`
3. In `TickerInput.tsx`: set `maxLength={12}` on the `<input>` element
4. Confirm `onChange` or `onInput` handler calls `.toUpperCase()` on the value
5. Below the input add a `<p>` hint: `"Try: AAPL, TSLA, NVDA"` with `text-xs text-neutral-400` styling, only visible when input is empty and status is idle

**User Action Steps**

- Type `brk.b` → field auto-uppercases to `BRK.B`
- Type 13 characters → 13th character rejected
- Submit empty → see correct error message

**Data Impact:** None

**Test Plan:**

- Manual: type lowercase, verify uppercase coercion
- Manual: type `123ABC` — should be accepted (alphanumeric)
- Manual: type `@@@@` — should fail validation
- Unit test: update `validators.test.ts` assertions for new regex behavior

**Acceptance Criteria:**

- Validator accepts alphanumeric + period tickers up to 12 chars
- Error copy matches spec exactly
- Hint text visible on empty state, hidden during/after analysis

**Rollback Strategy:** Revert `validators.ts` regex and `TickerInput.tsx` changes

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/lib/validators.ts`, `frontend/components/playground/TickerInput.tsx`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Input Field

---

### Task ID: UI-003

**Title:** Analyze button — add "Analyze Another Ticker" affordance and complete state copy

**Phase:** 1 — Core Components

**Subsystem:** Playground input area

**Description:**
After pipeline completion (`status === 'complete'`), the spec requires an "Analyze Another Ticker" affordance — either the button re-enables with different label, or a secondary CTA appears. Currently the button simply re-enables with the same "Analyze" label. Implement the spec-defined completion affordance.

**Scope Boundaries**

Files affected:

- `frontend/components/playground/AnalyzeButton.tsx`

Modules affected: Button visual states

Explicitly NOT touching: `useAnalysis` hook, store `status` logic

**Implementation Steps**

1. In `AnalyzeButton.tsx`, read `status` from the Zustand store via selector
2. When `status === 'complete'`, render the button with label `"Analyze Another Ticker"` and a secondary/outlined visual style (e.g., `border border-brand-500 text-brand-500 bg-white hover:bg-brand-50`) instead of the primary filled style
3. When `status === 'idle'` or `status === 'failed'`, render `"Analyze"` with the primary style
4. When `status === 'loading' | 'streaming'`, render disabled with spinner as currently implemented
5. Ensure min-height 44px is maintained across all states

**User Action Steps**

- Submit a ticker → button shows loading spinner
- Analysis completes → button reads "Analyze Another Ticker" in outlined style
- Click "Analyze Another Ticker" → starts new analysis (existing `onClick` handler handles this)

**Data Impact:** None

**Test Plan:**

- Set store `status` to `'complete'` manually; confirm button label and style
- Confirm existing loading state still renders spinner
- Confirm touch target ≥ 44px in all states

**Acceptance Criteria:**

- Button shows "Analyze Another Ticker" after analysis completes
- Visual distinction between primary (idle) and secondary (complete) states
- No regression in loading/disabled state

**Rollback Strategy:** Remove the `status === 'complete'` branch from `AnalyzeButton.tsx`

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/playground/AnalyzeButton.tsx`, `frontend/store/index.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Button Components

---

### Task ID: UI-004

**Title:** Create GlobalFailureBanner component for mid-pipeline partial-data warning

**Phase:** 1 — Core Components

**Subsystem:** Playground layout

**Description:**
The spec requires a visible banner: "Some data could not be retrieved. Report may be incomplete." when a mid-pipeline step fails but the pipeline continues. Currently no such banner exists. Create a new `GlobalFailureBanner` component and integrate it into the playground page layout.

**Scope Boundaries**

Files affected:

- `frontend/components/ui/GlobalFailureBanner.tsx` *(new file)*
- `frontend/app/page.tsx`

Modules affected: UI display layer only; reads `status` and `errorMessage` from Zustand store

Explicitly NOT touching: Store logic, pipeline error handling, API layer

**Implementation Steps**

1. Create `components/ui/GlobalFailureBanner.tsx` — a dismissible amber banner component
2. Banner displays when `status === 'failed'` AND report panels have partial data (check `marketData !== null || news !== null`)  
   - Copy: `"Some data could not be retrieved. Report may be incomplete."`
   - Style: `bg-amber-50 border border-amber-200 text-amber-800` (matches existing Disclaimer palette)
   - Include an `×` dismiss button (updates local `dismissed` state only; no store mutation)
3. In `app/page.tsx`, render `<GlobalFailureBanner />` immediately above the `<ReportGrid />` when conditions are met

**User Action Steps**

- Simulate a partial failure (one panel empty, others populated)
- Banner appears above the report grid in amber style
- User clicks `×` — banner dismisses

**Data Impact:** None

**Test Plan:**

- Set store `status = 'failed'` + `marketData = {...}` → banner appears
- Set store `status = 'complete'` → banner does not appear
- Click dismiss → banner hidden without affecting panels

**Acceptance Criteria:**

- Banner appears correctly on partial pipeline failure
- Does not appear on full success or on idle state
- Dismiss works without affecting any data

**Rollback Strategy:** Remove `GlobalFailureBanner` import and render call from `page.tsx`; delete component file

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? Yes
- Required files: `frontend/app/page.tsx`, `frontend/components/ui/Disclaimer.tsx` (reference styling), `frontend/store/index.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Flow 5: Mid-Pipeline Failure

---

### Task ID: UI-005

**Title:** Landing page empty state — system description and example ticker hint

**Phase:** 2 — Screen Refactor

**Subsystem:** Playground page layout

**Description:**
On first load (empty state), the spec requires: a one-sentence system description and a placeholder prompt showing example tickers. Currently the page shows only the TickerInput + AnalyzeButton with no surrounding context. Update `app/page.tsx` layout for the empty state.

**Scope Boundaries**

Files affected:

- `frontend/app/page.tsx`

Modules affected: Page-level layout and conditional rendering

Explicitly NOT touching: TickerInput component internals, AnalyzeButton, store logic

**Implementation Steps**

1. In `app/page.tsx`, identify the main centered content area
2. Add above the input group: a `<h1>` with the product name (e.g., "StockLens AI") and a subtitle `<p>` with one-sentence description: `"AI-powered stock research: market data, news analysis, and insights in one place."`
3. Verify these are only rendered before any analysis state (i.e., `status === 'idle'`) — after analysis, they collapse or remain as a compact header
4. Ensure the non-financial-advice disclaimer in the footer/header is visible without scrolling on typical viewport heights (600px+)

**User Action Steps**

- Open app fresh → see title, description, input, example hint
- After analysis → title/description remain or compact; panels appear below

**Data Impact:** None

**Test Plan:**

- Visual: verify description visible at 1280px, 768px, 375px
- Verify disclaimer always visible without scrolling at 768px viewport height
- Confirm no layout shift when panels start rendering

**Acceptance Criteria:**

- System description and product name visible on empty state
- Disclaimer always visible without scroll
- No visual regression when panels load

**Rollback Strategy:** Remove the added `<h1>` and `<p>` description elements from `page.tsx`

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/app/page.tsx`, `frontend/app/layout.tsx`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Flow 6: Empty State

---

### Task ID: UI-006

**Title:** Report grid — implement Row 1–4 panel arrangement with correct column proportions

**Phase:** 2 — Screen Refactor

**Subsystem:** Playground report grid

**Description:**
The spec prescribes a specific panel order and layout ratio: Row 1 (Stock Overview + Price Chart, equal), Row 2 (News wider + Sentiment narrower), Row 3 (Events + AI Insight, equal), Row 4 (Data Sources full width). The current `ReportGrid` uses a flat 2-column grid that does not guarantee order or ratio. Reimplement `ReportGrid` with explicit layout using CSS grid areas or ordered placement.

**Scope Boundaries**

Files affected:

- `frontend/components/playground/ReportGrid.tsx`

Modules affected: Panel layout and ordering

Explicitly NOT touching: Individual panel component internals, store selectors, data flow

**Implementation Steps**

1. Replace the generic `grid grid-cols-1 md:grid-cols-2` approach with a named grid or explicit column-span assignments:
   - On desktop (lg+): use a 12-column grid
   - Row 1: `StockOverviewPanel` = `lg:col-span-6`, `PriceTrendChart` = `lg:col-span-6`
   - Row 2: `NewsSummaryPanel` = `lg:col-span-7`, `SentimentPanel` = `lg:col-span-5`
   - Row 3: `EventsPanel` = `lg:col-span-6`, `InsightPanel` = `lg:col-span-6`
   - Row 4: `DataSourcesPanel` = `lg:col-span-12`
   - `ReasoningViewer` = `lg:col-span-12` above all panels
2. On tablet (md, 768–1023px): use 2-col grid; Row 2 uses equal cols (7/5 ratio collapses to 1/1)
3. On mobile (<768px): all panels single-column stacked
4. Maintain existing conditional rendering (only render panels when data is available via store selectors)

**User Action Steps**

- Submit analysis → observe panel order matches spec Row 1–4
- Resize to tablet → 2-col layout
- Resize to mobile → single-column stacked

**Data Impact:** None

**Test Plan:**

- Visual regression: screenshot at 1440px, 768px, 375px
- Confirm Row 2 News panel is visibly wider than Sentiment panel at desktop
- Confirm Data Sources always full-width

**Acceptance Criteria:**

- Panel order and proportions match spec exactly at desktop breakpoint
- Responsive behavior correct at all 3 breakpoints
- No functional regression in panel rendering

**Rollback Strategy:** Revert `ReportGrid.tsx` to previous flat 2-column grid

**Estimated Complexity:** Medium

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? Yes
- Required files: `frontend/components/playground/ReportGrid.tsx`, `frontend/store/index.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Landing/Playground Post-Analysis, §Panel Structure

---

### Task ID: UI-007

**Title:** Agent Reasoning Viewer — step slide-in animation and model indicator

**Phase:** 2 — Screen Refactor

**Subsystem:** Reasoning Viewer

**Description:**
The spec requires two things currently missing from `ReasoningViewer`: (1) each step entry should animate in with a slide-in or fade-in effect as it appears; (2) when an OpenAI key is active, steps that use OpenAI should display "Using: OpenAI [model name]". Add both without modifying the SSE data flow or Zustand append logic.

**Scope Boundaries**

Files affected:

- `frontend/components/playground/ReasoningViewer.tsx`

Modules affected: Step list visual rendering

Explicitly NOT touching: `useSSEStream`, `useAnalysis`, store `stepEvents` append logic

**Implementation Steps**

1. In the step list render loop, add `animate-slide-in-left` class (defined in UI-001) to each step `<li>` element
2. Use a CSS `animation-delay` tied to step index to stagger entries: `style={{ animationDelay: \`\${index * 0.05}s\` }}`
3. For the model indicator: read `activeModel` from the settings store slice; in the viewer header or step description area, add a `<span>` reading `"Using: \${activeModel}"` styled as `text-xs text-neutral-400` — show only when `openAiKeyStatus === 'set'`
4. Verify "In Progress" step shows a spinner icon and "Complete" step shows a checkmark (already implemented — confirm visual)

**User Action Steps**

- Submit analysis → watch steps slide in sequentially in the Reasoning Viewer
- If OpenAI key is set → model indicator appears in viewer header
- Without key → indicator not shown

**Data Impact:** None — reads `activeModel` and `openAiKeyStatus` from existing store state

**Test Plan:**

- Submit analysis with no key — confirm no model indicator shown
- Set OpenAI key in settings — submit analysis — confirm indicator shows model name
- Confirm step animation plays without layout shift

**Acceptance Criteria:**

- Each step slides/fades in as it's appended
- Model indicator displays correctly based on key status
- No regression in step status icons or streaming behavior

**Rollback Strategy:** Remove `animate-slide-in-left` class and model indicator JSX from `ReasoningViewer.tsx`

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/playground/ReasoningViewer.tsx`, `frontend/store/index.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Agent Reasoning Viewer

---

### Task ID: UI-008

**Title:** Stock Overview Panel — verify N/A fallbacks, data freshness note, and price direction animation

**Phase:** 2 — Screen Refactor

**Subsystem:** Stock Overview Panel

**Description:**
The spec requires: (1) all missing data fields display "N/A" rather than empty space; (2) a visible "Data may be delayed up to 15 minutes" note; (3) the price direction indicator (arrow + percentage) animates on load. Verify and implement these three requirements.

**Scope Boundaries**

Files affected:

- `frontend/components/panels/StockOverviewPanel.tsx`
- `frontend/components/ui/PriceDirection.tsx`

Modules affected: Data display formatting, animation

Explicitly NOT touching: `formatters.ts` logic, store market data selectors, Recharts

**Implementation Steps**

1. In `StockOverviewPanel.tsx`: audit every metric field (P/E ratio, 52-week high/low, volume, market cap) — ensure each uses `value ?? 'N/A'` or the existing `formatRatio`/`formatLargeNumber` formatters which already return `'N/A'` for null
2. Verify the data freshness note exists: `"Data may be delayed up to 15 minutes"` in `text-xs text-neutral-400` below the panel content
3. In `PriceDirection.tsx`: add `animate-fade-in-up` class (from UI-001) to the root element so it plays the entrance animation when the component mounts

**User Action Steps**

- Analyze a ticker with missing P/E ratio → "N/A" shown
- Stock panel renders → data freshness note visible
- Panel appears → price direction arrow animates upward entrance

**Data Impact:** None

**Test Plan:**

- Mock `marketData` with `pe_ratio: null` → confirm "N/A" displayed
- Visual: confirm data freshness note present in panel
- Visual: confirm animation plays once on panel mount

**Acceptance Criteria:**

- All metric fields show "N/A" for missing data (not blank)
- Data freshness note always present in Stock Overview
- Price direction animates on panel appearance

**Rollback Strategy:** Remove `animate-fade-in-up` from `PriceDirection.tsx`; N/A fallbacks are safe additive changes

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/panels/StockOverviewPanel.tsx`, `frontend/components/ui/PriceDirection.tsx`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Stock Overview Panel

---

### Task ID: UI-009

**Title:** News Summary Panel — add deduplication count badge and article topic tags

**Phase:** 2 — Screen Refactor

**Subsystem:** News Summary Panel

**Description:**
The spec requires showing a deduplication count if multiple articles were merged ("3 articles merged into this summary"), and topic tags per article (e.g., "Earnings," "Regulatory"). Review the current `NewsSummaryPanel` and `ArticleSummary` type to determine if these fields are present in the data model, then add the UI display.

**Scope Boundaries**

Files affected:

- `frontend/components/panels/NewsSummaryPanel.tsx`
- `frontend/types/report.ts` *(read-only — verify fields exist)*

Modules affected: Article list item rendering

Explicitly NOT touching: API response structure, news retrieval logic, store news selectors

**Implementation Steps**

1. Check `types/report.ts` → `ArticleSummary` interface: confirm `topics: string[]` and `deduplication_count?: number` (or similar) fields exist
2. In `NewsSummaryPanel.tsx`, in the article list item:
   - If `article.deduplication_count > 1`: render a small `<span>` badge: `"${count} sources"` with `bg-neutral-100 text-neutral-600 text-xs px-1.5 py-0.5 rounded` styling
   - Map `article.topics` array → render each as an existing topic tag chip (already partially implemented — verify and ensure spec copy: "Earnings", "Regulatory", "Product Launch", etc.)
3. Verify sentiment badge per article is present (already implemented via `SentimentBadge` component)
4. Verify empty state: "No recent articles found" with retrieval window text

**User Action Steps**

- View news panel with deduplicated articles → see "X sources" badge
- View article topic tags → rendered as chips
- Analyze ticker with no news → "No recent articles found" shown

**Data Impact:** None

**Test Plan:**

- Mock article with `topics: ['Earnings', 'Regulatory']` → tags render
- Mock article with `deduplication_count: 3` → "3 sources" badge appears
- Mock empty news collection → empty state renders

**Acceptance Criteria:**

- Deduplication count badge visible when count > 1
- Topic tags render for each article
- Empty state copy matches spec

**Rollback Strategy:** Remove deduplication badge and topic tag rendering from `NewsSummaryPanel.tsx`

**Estimated Complexity:** Low–Medium

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/panels/NewsSummaryPanel.tsx`, `frontend/types/report.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §News Summary Panel

---

### Task ID: UI-010

**Title:** Sentiment Panel — add emerging-concern callout and limited-sources caveat

**Phase:** 2 — Screen Refactor

**Subsystem:** Sentiment Panel

**Description:**
The spec requires: (1) a callout block when an emerging concern pattern is detected (sudden spike in negative articles); (2) a "Based on limited sources" caveat when fewer than 3 articles were analyzed. Review `SentimentPanel.tsx` and `SentimentResult` type, then add both UI elements.

**Scope Boundaries**

Files affected:

- `frontend/components/panels/SentimentPanel.tsx`
- `frontend/types/report.ts` *(read-only — verify fields)*

Modules affected: Sentiment display and caveat text

Explicitly NOT touching: Sentiment analysis logic, store sentiment selectors

**Implementation Steps**

1. Check `types/report.ts` → `SentimentResult`: confirm fields for `article_count`, and `emerging_concern?: boolean` (or `dominant_narrative`, etc.)
2. In `SentimentPanel.tsx`:
   - If `sentiment.article_count < 3`: render `<p className="text-xs text-neutral-400 mt-2">"Based on limited sources"</p>` below the distribution bar
   - If `sentiment.emerging_concern === true` (or equivalent field): render a callout box above the distribution bar: amber-tinted `<div>` with ⚠ icon and text "Emerging concern: sudden increase in negative articles detected" — styled like a mini version of the Disclaimer component
3. Verify the dominant narrative label is rendered (e.g., "Mostly Positive", "Mixed", "Predominantly Negative")
4. Verify distribution percentages round to whole numbers totalling 100%

**User Action Steps**

- View analysis with < 3 news articles → limited sources caveat visible
- View analysis with emerging concern flag → amber callout visible
- Verify both absent in normal conditions

**Data Impact:** None

**Test Plan:**

- Mock `article_count: 2` → caveat appears
- Mock `emerging_concern: true` → callout appears
- Mock normal data → neither appears

**Acceptance Criteria:**

- Limited sources caveat appears correctly
- Emerging concern callout appears correctly with amber styling
- Neither appears in normal data conditions

**Rollback Strategy:** Remove the two conditional render blocks from `SentimentPanel.tsx`

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/panels/SentimentPanel.tsx`, `frontend/types/report.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Sentiment Overview Panel

---

### Task ID: UI-011

**Title:** Events Panel — verify category labels, empty state, and multi-source link display

**Phase:** 2 — Screen Refactor

**Subsystem:** Events Panel

**Description:**
The spec defines specific event categories (Earnings Announcements, Acquisitions/Mergers, Regulatory Actions, Product Launches, Leadership Changes, Other) and requires that the same event reported by multiple articles lists all source links once. Review `EventsPanel.tsx` against these requirements.

**Scope Boundaries**

Files affected:

- `frontend/components/panels/EventsPanel.tsx`

Modules affected: Event list rendering

Explicitly NOT touching: Event extraction logic, pipeline, store

**Implementation Steps**

1. Verify category badge labels in `EventsPanel.tsx` match spec exactly: "Earnings", "M&A", "Regulatory", "Product Launch", "Leadership", "Other"
2. Verify that each event's source links (array of URLs) render as separate `<a>` elements opening in new tab
3. Verify empty state copy: `"No significant events identified in the current news window"`
4. If event `date` is null/undefined: do not render a date field (omit rather than show empty)

**User Action Steps**

- View events panel with multiple events — confirm category labels match spec
- Click a source link — opens in new tab
- Analyze ticker with no events — empty state copy shown

**Data Impact:** None

**Test Plan:**

- Mock events with each category type — confirm badge labels
- Mock event with 3 source links — confirm all 3 render
- Mock empty events result — confirm empty state copy

**Acceptance Criteria:**

- Category labels match spec enumeration
- Source links all open in new tab
- Empty state copy matches spec verbatim

**Rollback Strategy:** Revert label and link changes in `EventsPanel.tsx`

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/panels/EventsPanel.tsx`, `frontend/types/report.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Event Extraction Panel

---

### Task ID: UI-012

**Title:** AI Insight Panel — verify all 6 sections, labels, and insufficient-data copy

**Phase:** 2 — Screen Refactor

**Subsystem:** AI Insight Panel

**Description:**
The spec defines exactly 6 labeled sections: Company Overview, Recent Developments, Sentiment Overview, Potential Drivers, Potential Risks, AI Summary. Each must be labeled "AI-generated" and show "Insufficient data available for this section" when empty. Verify `InsightPanel.tsx` against this spec.

**Scope Boundaries**

Files affected:

- `frontend/components/panels/InsightPanel.tsx`

Modules affected: AI insight section rendering

Explicitly NOT touching: Insight generation logic, store, API

**Implementation Steps**

1. Verify all 6 section keys render in the correct order with exact spec labels
2. Confirm the "AI-generated" label appears prominently in the panel header or per-section
3. Confirm `"Insufficient data available for this section"` is shown (not empty space) when a section's content is null/empty
4. Verify the "not financial advice" disclaimer is visible within the panel or directly adjacent
5. Confirm section headings use a distinct typography style (`font-semibold` or similar) for visual hierarchy

**User Action Steps**

- View insight panel → all 6 sections present with correct labels
- Analyze ticker with sparse data → "Insufficient data" shown in empty sections
- Verify AI-generated label visible without scrolling

**Data Impact:** None

**Test Plan:**

- Mock `insights` with some sections null — confirm fallback copy renders
- Confirm 6 sections in correct order
- Confirm disclaimer visible

**Acceptance Criteria:**

- All 6 sections labeled correctly and in spec order
- Insufficient data copy correct
- No blank/empty section content

**Rollback Strategy:** Revert label and fallback copy changes in `InsightPanel.tsx`

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/panels/InsightPanel.tsx`, `frontend/types/report.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §AI Insight Panel

---

### Task ID: UI-013

**Title:** Data Sources Panel — verify grouped layout (Market Data / News Sources) and link behavior

**Phase:** 2 — Screen Refactor

**Subsystem:** Data Sources Panel

**Description:**
The spec requires sources grouped into two sections: "Market Data" (provider + data type) and "News Sources" (article title + link). All links open in new tab. Sources with no usable data should not be listed. Verify `DataSourcesPanel.tsx` matches this.

**Scope Boundaries**

Files affected:

- `frontend/components/panels/DataSourcesPanel.tsx`

Modules affected: Data source list rendering

Explicitly NOT touching: Data source collection logic, store, API

**Implementation Steps**

1. Confirm two distinct sections with labels "Market Data" and "News Sources" are rendered as visual group headers
2. For Market Data sources: render provider name + data type contributed (e.g., "Yahoo Finance — Price, Volume, Market Cap")
3. For News Sources: render article title as a link (`<a target="_blank" rel="noopener noreferrer">`)
4. Confirm sources with `status === 'unavailable'` are filtered out (not listed)
5. Confirm the panel is collapsible and starts collapsed by default (already in store UISlice — verify `DataSourcesPanel` default is `false`)

**User Action Steps**

- View data sources panel → see two groups with correct labels
- Click a news source link → opens in new tab
- Confirm unavailable sources not shown

**Data Impact:** None

**Test Plan:**

- Mock sources with one unavailable — confirm it doesn't appear
- Mock news source with article title — confirm link renders with title text
- Confirm panel starts collapsed

**Acceptance Criteria:**

- Two groups visible with correct headers
- All links open `target="_blank"`
- Unavailable sources excluded
- Panel starts collapsed

**Rollback Strategy:** Revert grouping and link changes in `DataSourcesPanel.tsx`

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/panels/DataSourcesPanel.tsx`, `frontend/types/report.ts`, `frontend/store/index.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Data Sources Panel

---

### Task ID: UI-014

**Title:** Settings Modal — add active model display and verify copy strings

**Phase:** 2 — Screen Refactor

**Subsystem:** Settings Modal

**Description:**
The spec requires the settings area to show which model is currently active. Currently the modal shows only the API key input. Add a "Currently using: [model name]" display and verify all button labels and explanatory text match spec.

**Scope Boundaries**

Files affected:

- `frontend/components/settings/SettingsModal.tsx`

Modules affected: Modal UI rendering

Explicitly NOT touching: Settings store logic, API key validation, model switching logic

**Implementation Steps**

1. In `SettingsModal.tsx`, read `activeModel` and `openAiKeyStatus` from the settings store slice
2. Add a display line: `"Currently using: \${activeModel}"` styled as `text-sm text-neutral-600` — shown at the top of the modal content
3. Verify explanatory note matches spec: `"Your API key is used only for this session and is not stored."`
4. Verify button labels: "Save" and "Clear"
5. When `openAiKeyStatus === 'invalid'`: verify an error message is shown in the modal

**User Action Steps**

- Open settings modal → see "Currently using: Local Ollama" (or current model)
- Enter and save OpenAI key → "Currently using: OpenAI gpt-4o"
- Enter invalid key → error message shown in modal

**Data Impact:** None

**Test Plan:**

- Open modal with no key set — confirm "Local Ollama" or equivalent shown
- Set OpenAI key — confirm model name updates in modal
- Confirm explanatory copy matches spec verbatim

**Acceptance Criteria:**

- Active model visible in modal
- All copy matches spec
- Error state for invalid key works

**Rollback Strategy:** Remove `activeModel` display from `SettingsModal.tsx`

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/settings/SettingsModal.tsx`, `frontend/store/index.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Settings/Config Area

---

### Task ID: UI-015

**Title:** API Documentation page — add sticky sidebar with endpoint anchor navigation

**Phase:** 2 — Screen Refactor

**Subsystem:** Docs page

**Description:**
The spec defines the docs page as having a sidebar with clickable endpoint anchors + a main content area. Currently `app/docs/page.tsx` is a single-column RSC with no sidebar. Add a two-column layout with a sticky sidebar listing all endpoints as anchor links.

**Scope Boundaries**

Files affected:

- `frontend/app/docs/page.tsx`
- `frontend/components/docs/EndpointBlock.tsx` *(read-only — add `id` props for anchors)*

Modules affected: Docs page layout

Explicitly NOT touching: Endpoint data, code block content, copy-to-clipboard logic

**Implementation Steps**

1. In `docs/page.tsx`, wrap the existing content in a two-column layout: `<div className="flex gap-8">` with a `<aside>` (sidebar) and `<main>` (content)
2. Sidebar: `<nav>` with a list of `<a href="#endpoint-id">` links for each endpoint — sticky on desktop (`sticky top-4`)
3. Each `EndpointBlock` needs an `id` prop passed through to its root `<section id={...}>` for anchor navigation
4. On mobile (`<lg`): sidebar renders above the content (stacked, not side-by-side)
5. Sidebar styling: `text-sm text-neutral-600 hover:text-brand-500 space-y-2`

**User Action Steps**

- Navigate to `/docs` → see sidebar on left, endpoints on right (desktop)
- Click a sidebar link → scrolls to that endpoint section
- On mobile → sidebar stacks above content

**Data Impact:** None

**Test Plan:**

- Click each sidebar link → scrolls to correct section
- Resize to mobile → sidebar stacks
- Verify RSC constraint not broken (no `use client` added)

**Acceptance Criteria:**

- Sidebar present with all endpoint links
- Anchor navigation works
- No regression in existing endpoint content

**Rollback Strategy:** Revert `docs/page.tsx` to single-column layout

**Estimated Complexity:** Medium

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? Yes
- Required files: `frontend/app/docs/page.tsx`, `frontend/components/docs/EndpointBlock.tsx`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §API Documentation Page

---

### Task ID: UI-016

**Title:** Panel progressive fade-in — add entrance animation as panels receive data

**Phase:** 3 — Visual Polish

**Subsystem:** All report panels

**Description:**
The spec requires each panel to fade in as data becomes available, giving the impression of progressive rendering. Currently panels appear or remain invisible with no transition. Add `animate-fade-in-up` to each panel's root element when transitioning from skeleton/loading to populated state.

**Scope Boundaries**

Files affected:

- `frontend/components/ui/Panel.tsx`

Modules affected: Panel shell animation

Explicitly NOT touching: Panel content components, data selectors, store

**Implementation Steps**

1. In `Panel.tsx`, identify the prop or state that transitions from "loading" to "content" (likely `children` presence or a passed `isLoaded` prop)
2. Add a `data-loaded` attribute or conditional class: when the panel transitions to populated state, apply `animate-fade-in-up` to the panel root `<div>`
3. Alternatively: pass an `animated` prop from each panel component that becomes `true` once data is received from the store
4. Use a CSS `transition: opacity` approach as a fallback for environments where animation is disabled (`prefers-reduced-motion: reduce` check in `globals.css`)
5. Verify `@media (prefers-reduced-motion: reduce)` disables the animation

**User Action Steps**

- Submit analysis → each panel fades in gracefully as data arrives
- Enable "Reduce Motion" in OS settings → panels appear without animation

**Data Impact:** None

**Test Plan:**

- Visual: submit analysis, confirm panels fade in sequentially
- Prefers-reduced-motion: confirm animation disabled
- Confirm no layout shift during fade

**Acceptance Criteria:**

- All panels animate in on data arrival
- `prefers-reduced-motion` respected
- No layout shift or content flash

**Rollback Strategy:** Remove `animate-fade-in-up` class application from `Panel.tsx`

**Estimated Complexity:** Low–Medium

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/ui/Panel.tsx`, `frontend/app/globals.css` (updated in UI-001)
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Animations

---

### Task ID: UI-017

**Title:** Price Trend Chart — verify timeframe toggles, responsive sizing, and accessibility

**Phase:** 3 — Visual Polish

**Subsystem:** Price Trend Chart panel

**Description:**
The spec requires: (1) timeframe toggles (1M, 3M, 6M, 1Y) that update the chart without re-running the full pipeline; (2) responsive chart that does not overflow viewport; (3) accessible chart (color not sole differentiator, accessible data table). Verify all three in `PriceTrendChart.tsx` and `PriceTrendChartClient.tsx`.

**Scope Boundaries**

Files affected:

- `frontend/components/panels/PriceTrendChart.tsx`
- `frontend/components/panels/PriceTrendChartClient.tsx`

Modules affected: Chart display and timeframe controls

Explicitly NOT touching: `activeTimeframe` store action, price history data fetching

**Implementation Steps**

1. Verify timeframe toggle buttons (1M, 3M, 6M, 1Y) read/write `activeTimeframe` from UISlice without triggering a new analysis run
2. Verify active toggle has a visually distinct selected state (e.g., `bg-brand-50 text-brand-500 font-medium` vs default `text-neutral-600`)
3. Confirm the chart uses `<ResponsiveContainer width="100%" height={200}>` for responsive sizing
4. Confirm the accessible data table exists (currently `<table className="sr-only">`) and is populated with price data
5. Add a trend direction text label ("↑ Upward Trend", "↓ Downward Trend", "→ Sideways") below the chart — this must be text-based, not color-only

**User Action Steps**

- Click 1M, 6M, 1Y toggles — chart updates, no full re-analysis
- Resize browser to 375px — chart scales within bounds
- Screen reader: navigate chart area — accessible table announced

**Data Impact:** None

**Test Plan:**

- Click each timeframe toggle — confirm chart data changes
- Confirm no `analyze()` call triggered on toggle
- Resize to 375px — no horizontal overflow
- Run axe accessibility check on chart area

**Acceptance Criteria:**

- Timeframe toggles work without pipeline re-run
- Active toggle has distinct visual state
- Chart does not overflow on mobile
- Accessible data table present

**Rollback Strategy:** Revert toggle and label changes

**Estimated Complexity:** Low

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? No
- Required files: `frontend/components/panels/PriceTrendChart.tsx`, `frontend/components/panels/PriceTrendChartClient.tsx`, `frontend/store/index.ts`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Price Trend Chart

---

### Task ID: UI-018

**Title:** Responsive layout audit — verify all breakpoints and touch targets

**Phase:** 4 — Validation

**Subsystem:** Full application layout

**Description:**
Perform a full responsive audit of the application at all three spec-defined breakpoints. Verify all interactive elements meet the 44×44px touch target minimum. Verify single-column stacked order on mobile is logical and matches spec's priority order.

**Scope Boundaries**

Files affected:

- `frontend/components/playground/ReportGrid.tsx` *(adjust if needed)*
- `frontend/app/page.tsx` *(adjust if needed)*

Modules affected: Layout responsiveness

Explicitly NOT touching: Component internals, business logic

**Implementation Steps**

1. Test at 1440px (desktop), 768px (tablet), 375px (mobile) using browser DevTools device emulation
2. Desktop: multi-column Row 1–4 layout (from UI-006) correct
3. Tablet: 2-column grid; Row 2 collapses to equal columns
4. Mobile: single-column stacked in spec priority order (Reasoning Viewer, then Stock, Chart, News, Sentiment, Events, Insight, Data Sources)
5. Verify each clickable/interactive element is ≥ 44px in both dimensions using DevTools box model
6. Fix any identified issues directly in the relevant component

**User Action Steps**

- Resize to 375px — all panels stacked in correct order, no horizontal scroll
- Tap targets on mobile — all comfortable to tap
- Resize from 375px → 1440px — layout transitions correctly

**Data Impact:** None

**Test Plan:**

- DevTools device emulation at 375px, 768px, 1024px, 1440px
- Check no horizontal overflow at any breakpoint
- Measure touch targets for TickerInput, AnalyzeButton, panel toggles, timeframe toggles

**Acceptance Criteria:**

- No horizontal scroll at any defined breakpoint
- All interactive elements ≥ 44×44px
- Panel order logical on mobile

**Rollback Strategy:** Revert any layout fixes applied during audit

**Estimated Complexity:** Medium

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? Yes
- Required files: `frontend/components/playground/ReportGrid.tsx`, `frontend/app/page.tsx`, `frontend/app/layout.tsx`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Responsive Layout

---

### Task ID: UI-019

**Title:** Accessibility audit — WCAG 2.1 AA compliance validation

**Phase:** 4 — Validation

**Subsystem:** Full application

**Description:**
Run a full WCAG 2.1 AA audit across all UI states: empty state, loading state, post-analysis state, error state, docs page, settings modal. Verify color contrast, focus management, ARIA labels, keyboard navigation, live regions, and skip links.

**Scope Boundaries**

Files affected:

- Any component failing the audit

Modules affected: ARIA attributes, focus management, color contrast

Explicitly NOT touching: Business logic, data flow

**Implementation Steps**

1. Run axe browser extension or `npm run test:accessibility` (if configured) against each page state
2. Verify color contrast ≥ 4.5:1 for all text (use DevTools Accessibility panel)
3. Verify all non-text elements have ARIA labels (chart, icons, status indicators)
4. Verify focus management: modal opens → focus moves into modal; modal closes → focus returns to trigger
5. Verify `aria-live="polite"` on ReasoningViewer is present (already in code — confirm not removed)
6. Verify skip-to-content link in `layout.tsx` functions (already present — confirm target `#main-content` exists)
7. Fix any identified violations — document each fix as a comment

**User Action Steps**

- Tab through entire page: logical focus order
- Open settings modal: focus moves to modal; close: focus returns to gear icon
- Run analysis: Reasoning Viewer steps announced to screen reader

**Data Impact:** None

**Test Plan:**

- axe DevTools or Playwright accessibility test suite
- Keyboard-only navigation through entire app
- VoiceOver/NVDA smoke test on ReasoningViewer

**Acceptance Criteria:**

- Zero critical axe violations
- Keyboard navigation complete and logical
- Modal focus management correct

**Rollback Strategy:** Revert any ARIA/focus changes if they cause regression

**Estimated Complexity:** Medium

**LLM Execution Assignment:**

Recommended Model: Claude Sonnet (Fast)

Context Strategy:

- Start new chat? Yes
- Required files: `frontend/app/layout.tsx`, `frontend/components/settings/SettingsModal.tsx`, `frontend/components/playground/ReasoningViewer.tsx`
- Docs to reference: `docs/00_PRODUCT_SPECIFICATION.md` §Accessibility

---

## 7. PHASES

### Phase 0 — Design Tokens & Theme

**Objective:** Establish the CSS animation keyframes that later phases depend on. No visible UI change yet.

**Tasks:** UI-001

**Risks:** None significant — additive CSS only

**Completion Criteria:**

- `animate-fade-in-up` and `animate-slide-in-left` utility classes functional
- `npm run build` passes

---

### Phase 1 — Core Components

**Objective:** Refine foundational interactive components (input, button, new banner) before screen-level work begins.

**Tasks:** UI-002, UI-003, UI-004, UI-005

**Risks:**

- Ticker regex change could over-permissively accept invalid tickers — validate against known valid/invalid cases

**Completion Criteria:**

- Ticker input accepts alphanumeric + period tickers, max 12 chars
- Analyze button shows "Analyze Another Ticker" after completion
- GlobalFailureBanner renders correctly for partial failures
- Empty state landing page displays system description + example hint

---

### Phase 2 — Screen Refactor

**Objective:** Implement all spec-defined screen layouts, panel arrangements, copy strings, and missing UI elements.

**Tasks:** UI-006, UI-007, UI-008, UI-009, UI-010, UI-011, UI-012, UI-013, UI-014, UI-015

**Risks:**

- Row 1–4 layout rewrite (UI-006) could affect panel render order — test with live SSE stream
- Docs page sidebar (UI-015) must remain a Server Component

**Completion Criteria:**

- All panels in correct Row 1–4 arrangement at desktop
- All panel copy strings match spec
- Docs sidebar functional with anchor navigation
- Settings modal shows active model
- Reasoning Viewer has model indicator and step animation

---

### Phase 3 — Visual Polish

**Objective:** Layer in animations and micro-interactions that give the app the responsive, progressive feel the spec describes.

**Tasks:** UI-016, UI-017

**Risks:**

- Panel fade-in animation must not interfere with SSE-driven progressive rendering timing
- `prefers-reduced-motion` must be respected

**Completion Criteria:**

- All panels fade in as data arrives
- Price Trend Chart timeframe toggles work with correct active state
- Trend direction label present as text (not color-only)
- All animations respect `prefers-reduced-motion`

---

### Phase 4 — Validation

**Objective:** Ensure the complete UI is responsive, accessible, and regression-free before delivery.

**Tasks:** UI-018, UI-019

**Risks:**

- Issues discovered in validation may require fixes across multiple earlier tasks

**Completion Criteria:**

- Zero horizontal overflow at 375px, 768px, 1024px, 1440px
- All touch targets ≥ 44×44px
- Zero critical axe WCAG violations
- Keyboard navigation complete
- All existing Playwright E2E tests pass (`npm run test:e2e`)
- All Vitest unit tests pass (`npm run test`)

---

## VERIFICATION (End-to-End)

1. **Start dev server:** `npm run dev` in `frontend/`
2. **Empty state check:** Open `http://localhost:3000` — verify system description, example hint, disclaimer visible
3. **Analysis flow:** Enter `AAPL`, click Analyze — verify:
   - Button disables with spinner
   - Reasoning Viewer appears, steps slide in
   - Panels appear in Row 1–4 order, each fading in
   - "Analyze Another Ticker" button appears on completion
4. **Panel content:** Verify all panels show correct data, N/A fallbacks, labels, links open in new tab
5. **Settings:** Click gear → modal opens → model name shown → enter test key → save
6. **Docs:** Navigate to `/docs` → sidebar present → click link → smooth scroll
7. **Responsive:** DevTools at 375px, 768px — verify layout adapts correctly
8. **Run tests:**

   ```
   cd frontend
   npm run test           # Vitest unit tests
   npm run test:e2e       # Playwright E2E tests
   ```

9. **Accessibility:** Run axe browser extension on each page state — zero critical violations
