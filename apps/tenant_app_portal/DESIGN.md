# LingQing Design System

**Product:** LingQing (tenant app portal)  
**Operator:** Analyst and agent user — business operator, data analyst, leadership asking questions of data.  
**Direction:** `tech-utility` (cool paper, ink, one green accent). Tokens bound verbatim.  
**Stack:** React + Tailwind + shadcn/ui. Do not introduce Ant Design.

This file is the **contract for agents**. It defines how every screen is built. It does not inventory routes, pages, or source files. Classify the job, pick a surface type, compose from component contracts, then pass the lint list.

---

## How an agent uses this file

Before writing or restyling UI:

1. **Bind tokens** to the existing shadcn CSS variables. Never invent hex. Never keep the shadcn default blue `--primary`.
2. **Keep one shell.** Authenticated work lives in one chrome (header + rail + canvas). Embed and unauthenticated canvases have no chrome.
3. **Pick one surface type** for the canvas (section 4). Do not mix densities on one view.
4. **Compose from component contracts** (section 5). Do not invent a one-off control language.
5. **Ship only if the lint list passes** (section 7).

Do not copy screenshot-specific fixes. A new screen still maps to a surface type.

---

## 1. Product rules (not pixels)

LingQing is a **workbench that happens to have admin**, not an admin that happens to have chat.

| Rule | Meaning |
|---|---|
| **Job** | Ask → analysis artifact → share / pin / follow up. |
| **Session** | A conversation may produce a document. The document is what leadership opens. |
| **Bilingual** | Chrome language is one locale (`i18n`). Data may be another language. Do not mix EN/ZH inside one summary line. |

**Information architecture (visual weight, not a route dump)**

- **Primary** (operator jobs): conversation, artifacts (reports / dashboards), knowledge & data, skills, search.
- **Secondary** (tenant keep-alive): settings, users, SSO, usage, subscription, tags/ABAC, model config.
- Primary items may appear on the rail. Secondary items share **one** Admin / Settings destination. They never compete as many equal rail buttons.
- A second persistent sidebar inside Settings is forbidden. In-page section nav (tabs or a compact stacked list in the **canvas**) is allowed; it is not a second app rail.

IA collapse can ship later. New UI must not add rail peers for admin tasks.

---

## 2. Tokens

Source of truth is OKLch. Bind these verbatim. Append CJK fallbacks to both sans stacks: `"PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei"`.

```css
:root {
  --bg:      oklch(98% 0.005 250);
  --surface: oklch(100% 0 0);
  --fg:      oklch(22% 0.02 240);
  --muted:   oklch(50% 0.018 240);
  --border:  oklch(90% 0.008 240);
  --accent:  oklch(58% 0.16 145);

  --font-display: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif;
  --font-body:    -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif;
  --font-mono:    'JetBrains Mono', 'IBM Plex Mono', ui-monospace, Menlo, monospace;

  --success: oklch(48% 0.12 145);
  --warn:    oklch(62% 0.14 75);
  --danger:  oklch(54% 0.18 25);
  --accent-fg: oklch(98% 0.01 145);
  --danger-fg: oklch(99% 0.01 25);

  --radius-control: 6px;
  --radius-pane:    10px;
  --focus-ring:    0 0 0 2px var(--bg), 0 0 0 4px var(--accent);
}
```

**Utility exception:** One sans family for UI and documents. Mono only for SQL, ids, field names, URLs, hashes. Do not add a display serif.

### Bind to shadcn (do not confuse names)

The portal binds these as OKLch channels on the existing shadcn slots (`oklch(var(--background) / <alpha-value>)`). Do not revert to leftover HSL blue. Mapping:

| System token | shadcn slot | Role |
|---|---|---|
| `--bg` | `--background` | Page |
| `--surface` | `--card`, `--popover` | Panes, menus |
| `--fg` | `--foreground` | Text |
| `--muted` | `--muted-foreground` | Meta (not `--muted` wash) |
| `--border` | `--border`, `--input` | Hairlines |
| `--accent` | **`--primary`** | Brand / CTA fill |
| `--accent-fg` | `--primary-foreground` | Text on CTA |
| Hover wash | shadcn `--accent` / `--secondary` | Quiet fill; **not** the brand color |
| `--danger` | `--destructive` | Confirm-only destructive fill |
| `--focus-ring` | `--ring` | Focus |

Product accent = `--primary`. shadcn `--accent` stays a neutral hover surface. Using `--accent` (Tailwind class `bg-accent`) as the brand color is a mapping error.

If a `.dark` class exists, derive it from the same recipe. Do not leave leftover blue `--primary`.

**Forbidden palettes:** Ant `#1890ff`, Tailwind indigo (`#6366f1` and siblings), leftover shadcn blue `--primary: 221.2 83.2% 53.3%`, raw `bg-emerald-*`.

### Layers

| Layer | Share | Rule |
|---|---|---|
| Neutrals | 70–90% | Page, panes, text, meta, hairlines |
| Accent | 5–10% | **≤2 visible uses per screen** (typical: active rail + one solid CTA) |
| Semantic | 0–5% | Validation, destructive **confirm** |
| Effect | &lt;1% | None. No gradient wash, glow, or blob background |

Charts: `--chart-1`…`--chart-10` is the categorical band (distinct hues, same density). Pie slices and multi-series charts cycle it. Single-series bar charts color each category from the band. No Ant/indigo. First stop is the product accent.

### Type

Scale 1.25, seven sizes max. Three weights only: **400** read · **500** UI/nav · **600** titles and primary buttons. No 700+ for extra emphasis.

| Role | Size | LH Latin | LH CJK | Tracking |
|---|---|---|---|---|
| H1 | 32px | 1.15 | **1.35** | Latin −0.02em; CJK 0 |
| H2 | 24px | 1.2 | **1.35** | CJK 0 |
| H3 | 20px | 1.25 | 1.35 | 0 |
| Body | 16px | 1.55 | **1.75** | 0 |
| UI / label / button | 14px | 1.5 | 1.5 | 0.02em; ALL CAPS 0.08em |
| Help | 13px | 1.5 | 1.5 | 0.01em |
| Caption | 12px | 1.5 | 1.5 | 0.02em |

CJK never inherits negative tracking. Numbers that compare: `font-variant-numeric: tabular-nums` plus **unit and period**. Do not present unlike magnitudes as peer KPIs.

### Shape and motion

- Controls: `--radius-control`. Panes/dialogs: `--radius-pane`.
- Hairline `1px solid var(--border)`. Table row hover: slightly darker `--bg`. No zebra. No rounded card + colored left border.
- Hover on fills: shift OKLch L by ±0.08. **Never** fade text to `--muted` on hover.
- Every focusable control: `:focus-visible` with `--focus-ring`.
- Disabled: opacity ~0.45. Only disabled may drop contrast.
- Primary hit targets ≥ 44px. Icon-only table actions: 32px icon, 44px hit area.
- Icons: Lucide (already in the app), 1.5–1.75 stroke, `currentColor`. No emoji as icons.

| Control | Default | Hover |
|---|---|---|
| Primary (`Button` default) | accent fill, accent-fg | accent L −0.08 |
| Secondary / outline | surface, fg, border | bg L −0.06 |
| Ghost | transparent, fg | quiet wash |
| Destructive | danger fill — **modal confirm only** | danger L −0.08 |
| Link / tertiary | fg or muted underline | underline; not a third solid |

---

## 3. Application shell

One chrome for every authenticated, non-embed page.

```
┌──────────────────────────────────────────────┐
│ Mark · tenant · locale · user menu           │
├────────┬─────────────────────────────────────┤
│ Rail   │ Page header (title + purpose)       │
│        ├─────────────────────────────────────┤
│        │ List toolbar or canvas body       │
└────────┴─────────────────────────────────────┘
```

List index/detail pages put CTAs in the **list toolbar** row below the header, not in the page header (see §4 Table).

**Header**

- Product mark. Subtitle muted. Tenant is a **control** (name + environment), not `user@tenant` concatenated with Logout beside it.
- Locale is a labeled control.
- User opens a menu: Profile, Admin/Settings, Logout. Logout is never a header-level button.
- Product mark is not `text-primary` if the rail already spends an accent hit.

**Rail**

- Icon + label; may collapse to icons.
- **One** active treatment: filled item (secondary/surface + fg). Not left-border + outline + pill in the same product.
- Search is either a rail item **or** a header `⌘K` — not both as primary.
- Workbench canvas is edge-to-edge. Other surfaces use page padding.

**Canvas width**

| Surface | Width |
|---|---|
| Workbench | Full remaining; split panes |
| Catalog / table / dashboard | Full remaining |
| Form / settings stack | Full remaining |
| Document (report) | Full remaining, left-aligned. No prose measure cap and no narrow/wide toggle. |

---

## 4. Surface types

Every page is **exactly one** of these. If a view needs two, it is a workbench (panes) or a list+drawer — not two densities stacked.

Example (classification only): a list of capabilities → Catalog. A conversation beside an artifact → Workbench. Do not keep a route table in this file.

### Workbench

Split workspace: steer on one side, artifact on the other.

- Default split ~40% / ~60% in favor of the artifact. Closed artifact → full remaining single column; reopen from the pane header. Not a leftover strip.
- Shared session identity in both headers.
- Composer sticky. **One** solid CTA in the panes (Send). Share on the artifact is outline if Send is solid.
- Destructive session actions live in overflow, not a danger icon in the header.

### Catalog

Scan a set of **capabilities or resources**.

- Row/card anatomy: name · one-line job in UI language · scope chip (neutral) · owner/version caption · overflow actions.
- Long body (prompt, policy, “do not use”) lives in a **drawer**, never in the list.
- Filters: segmented control. Hide empty segments or omit `(0)` counts that add no information.
- One page-level primary (Add / Upload).

### Table

Operate on records. Use one of the two **list layouts** below — do not invent a third chrome.

**Shared table rules**

- Columns: identity, status, truncated values (`+N`), actions as ghost or overflow.
- Destructive: overflow → **confirm dialog**. Never `Button variant="destructive"` on every row.
- Status: one pattern (badge **or** switch), not dots + switches + solids in one row.
- Rows 40–44px, sticky header. Horizontal scroll for extra columns, never the page.
- Table shell is `--card` (same as Card). Not transparent on page `--background`.
- Wide tables: `table-fixed w-full`; identity column gets `max-w-0` + `truncate` or `line-clamp-2` + full text in `title`.

**List index** — browse/create containers (collections, data sources, API connectors). Reference: knowledge base collections index.

```
┌ Title + one-line purpose (identity only — no buttons) ────────────┐
├ Search (sm:w-72) ──────── [Refresh outline] [Primary: Create/Add] ┤
├ optional: filters / tabs (segmented, full width)                    ┤
└ Table in card shell — row click navigates to detail               ┘
```

- **Page header** = identity only: `text-2xl` title, `text-sm text-muted-foreground` description. No buttons in the header row.
- **List toolbar** (row below header): search left; **refresh outline** then **one solid primary** (Create / New / Add) on the right. Use **`ListIndexToolbar`**.
- Container catalog actions (Share, Tags, Edit, Delete) on row via **`ContainerRowActions`** only — not in the page header.
- Optional filter/tabs row sits between toolbar and table (Skills tabs, scheduled-task status filters).

**List detail** — operate on records inside one container (documents in a collection, assets in a data source). Reference: collection documents page.

```
┌ Breadcrumb → container name + meta (identity only — no CTAs) ────┐
├ optional: in-context status bar (e.g. Drive sync — status + ⋯)   ┤
├ Search ── [Batch outline if selected] [Primary] [⋯ overflow]   ┤
└ Table in card shell — row ⋯ for record actions                   ┘
```

- Use **`ContainerDetailHeader`** for breadcrumb + title + meta **only**. No primary button, no refresh, no ⋯ in the header.
- **List-scoped CTAs** (Upload, Add record, batch delete, re-parse all) live in the **list toolbar** on the same row as search — not in the page header.
- One solid primary in the toolbar (Upload / Add). Batch actions when rows are selected = **outline** button beside primary.
- Infrequent collection-level ops (re-parse all, re-index all) → toolbar ⋯ overflow.
- In-context infra (Drive sync, schema sync banner) = status bar between header and toolbar; its ⋯ holds **only** that infra’s ops (sync now, disconnect) — never duplicate refresh icons in both header and banner.
- Container Share/Tags/Edit/Delete stay on the **parent index** route only.

**When not to use list layouts**

- **Catalog (cards)** — Skills, agents: card grid + drawer; tabs/filters ok; primary stays in page header.
- **Workbench, Document, Dashboard** — different surface types; no forced table toolbar.

### Form

Configure rarely, fail safely.

- Label above field. Help 13px muted **under** the field.
- Group related fields. Compact related numerics on one row; do not full-bleed a 40px-high input across the canvas.
- Secrets: masked value **inside** the control, with reveal / replace. Do not duplicate the mask as adjacent copy.
- Actions: Save primary · Test outline with **in-form** result · extra operations as text links.

### Settings stack

Several admin sections that share a tenant.

- One canvas column. Section nav is **in-page** (tabs or a compact list), never a second app rail.
- Policy row: title, one-line consequence, control on the right.
- Incomplete / risky counts use `--warn`, not caption gray.
- Full remaining canvas. In-page nav lives in **one** `--card` pane; inactive items are not transparent on page `--background`.
- Tables, cards, and form groups sit on `--card`. Do not mix a transparent table shell with a white card on the same view.
- **One section chrome:** title `text-lg font-semibold`, description `text-sm text-muted-foreground`, optional action on the same header row, body in that card. Do not put the title outside a card and the table/form in a second card. Do not use `text-2xl` for section titles (that size is KPI values only).

### Document

Read an analysis artifact.

- Document density: H1/H2, body 16px, tabular money, mono for SQL/fields. Full canvas width, left-aligned — not a centered reading column.
- Header is title plus provenance (date, author, source session). Do not add a trust / verified chip — AI artifacts are edited by AI or humans as a normal lifecycle.
- Share = primary on this surface when chat is not in view.

### Dashboard

Tell **one** quantitative story.

- KPI tiles share a period and a comparable unit family. Incomplete series: hide or label **incomplete** — never a peer tile of zeros / N/A.
- Chart: enough points to be a trend, or show a number. Time range + refresh live in the **page header**.
- No invented uptime or multipliers.

### Overlay

| | Dialog | Drawer / sheet |
|---|---|---|
| Use | Confirm, short create (≤ ~6 fields) | Inspect or edit a large object |
| Width | ~400–480px | ~480–560px |
| Title | Verb | Object name |
| Actions | One primary + Cancel | Save primary in footer |
| Dismiss | Esc; overlay click if non-destructive | Esc; list stays visible |

Do not read long documents in a dialog. Do not give Save and Delete equal solid weight.

### Empty / error

- Empty: what it is, why empty, next action. No `"—"`.
- Error: what failed, what to do. Connection tests write status next to the control, not toast-only.
- Loading: reuse the shell; do not invent a second spinner language.

### Parent index + Child detail

Default pattern for **container → records** features (knowledge base collections → documents, data sources → assets, API connectors → operations).

- **Parent route** → **List index** layout (section 4, Table).
- **Child route** → **List detail** layout (section 4, Table).
- Two routes when the child table is wide (≥ ~6 columns) or needs full canvas width. No persistent left sidebar for container switching.

**Lint (parent-child)**

- Parent index: Create/Add in list toolbar (not page header); Share/Tags/Edit/Delete via **`ContainerRowActions`** on rows only.
- Child detail: **`ContainerDetailHeader`** identity-only; list toolbar holds Upload/Add + batch + ⋯.
- Do not duplicate container catalog actions or duplicate refresh/sync controls across header and status bar.
- Migrate legacy child pages that still put Upload in `ContainerDetailHeader` to the list-detail toolbar pattern when touched.

---

## 5. Component contracts

Use the existing shadcn primitives. Extend variants; do not fork a second button kit.

**Button** — `default` = the one primary per view. `outline` / `secondary` = secondary. `ghost` = row/header utilities. `destructive` = confirm modal only. `link` = tertiary. Adjacent group: at most one `default`.

**Input / Select / Textarea** — label + control + optional help. Invalid: border `--danger` + 13px message, not color-only.

**Table** — table primitive. Overflow menu for row actions. Sticky header.

**Card** — grouping on forms and dashboards, not a wrapper around every table row. Catalog may use a compact card **or** a row; pick one per page.

**Settings section** — one Card: `text-lg` title, muted `text-sm` description, optional header action, body. Table body is flush (`p-0`); form/policy body keeps padding. Not a loose heading above a second surface.

**Badge / chip** — scope and status. Neutral by default. Semantic color only for warn / error. Chips do not consume the accent budget unless they *are* the page’s accent pair (avoid).

**Tabs** — switch peer views of the same object. Not a substitute for IA (do not tab-group unrelated admin products).

**Switch** — instantaneous preference. Policy with consequence uses switch + helper text, not a second explanation heading.

**Dropdown menu** — overflow for ≤ 7 actions. Include destructive as a **menu item**, then confirm.

**Container detail header** — breadcrumb parent link, container title + meta. **Identity only** on list-detail pages — no primary, refresh, or ⋯ (those belong in the list toolbar or an in-context status bar).

**List index toolbar** — search left; refresh outline + one solid Create/Add right. Shared **`ListIndexToolbar`** component.

**List detail toolbar** — search left; optional batch outline + one solid Upload/Add + optional ⋯ right. Shared **`ListDetailToolbar`** component. Infrequent ops (refresh, re-parse, schema sync) go in ⋯ overflow — not in the page header.

**Container row actions** — ghost Share / Tags / Edit / Delete on parent index table rows. Shared component; the only place for container catalog actions in the two-route pattern.

---

## 6. Content

- User-visible strings go through `i18n` (`en` + `zh` resource bundles). Do not hardcode one language in chrome.
- Catalog summaries are written in the **UI locale**. Raw multilingual source stays in the drawer.
- No `lorem`, “feature one”, or fake metrics. Incomplete telemetry stays labelled incomplete.
- Copy tense: verbs on buttons (`Save`, `Upload`, `Share`). Page titles are nouns or short jobs (`Skills`, `Conversation`).

---

## 7. Lint list (pass/fail)

1. ≤2 visible product-accent hits per screen.
2. ≤1 solid primary button per view (list index + list detail: Create/Upload in list toolbar only; repeat once at end of a long scroll only).
3. No solid destructive control in a table row.
4. No raw prompt, policy wall, or secret full value in a list.
5. No second persistent app sidebar.
6. One surface type (and one density) per view.
7. Tabular numbers + unit + period; unlike metrics are not peer KPIs.
8. No invented metrics.
9. One active-rail treatment product-wide.
10. Logout only in the user menu.
11. `:focus-visible` on every control.
12. Hover never lowers text contrast.
13. No emoji icons; Lucide `currentColor`.
14. No gradient wash; no colored left-bar on rounded cards.
15. Tokens from this file only — no raw hex in components.

---

## 8. One-sentence system

LingQing is a light, dense, green-accent **analysis workbench**: one shell, one surface type per view, one primary action, two accent hits, long text in drawers, admin on the full remaining canvas.
