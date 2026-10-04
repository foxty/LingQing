# LingQing Design System

**Product:** LingQing (tenant app portal)  
**Operator:** Analyst and agent user — business operator, data analyst, leadership asking questions of data.  
**Direction:** `tech-utility` (cool paper, ink, one green accent). Tokens bound verbatim.  
**Stack:** React + Tailwind + shadcn/ui. Do not introduce Ant Design.

Agent **contract**: classify the job → pick layout surface → pick feedback channels → compose from §6 → pass §8 lint. No route inventory. Map to a layout surface — not a product noun.

---

## How an agent uses this file

1. **Classify** (table below).
2. **Bind tokens** (§2). Never invent hex or shadcn default blue `--primary`.
3. **One shell** (§3). Embed/unauthenticated = no chrome.
4. **One layout surface** (§4). Detail views: one modifier (`prose` | `metrics`).
5. **Feedback** (§5): one channel per event.
6. **Compose** (§6). No one-off control language.
7. **Lint** (§8) pass/fail.

Do not copy screenshot-specific fixes.

### Classification

| Job | Layout surface | Variant / modifier | Key components |
|---|---|---|---|
| Conversation + artifact side-by-side | Workbench | — | composer, split panes |
| Scan capabilities (card grid) | Catalog | — | drawer for long body |
| Browse/create containers | Table | list index | `ListIndexToolbar`, `ContainerRowActions` |
| Operate on records in one container | Table | list detail | `ContainerDetailHeader`, `ListDetailToolbar` |
| One-off configuration | Form | — | label + help under field |
| Tenant admin (`/settings/*`) | Settings stack | settings job (§4) | `SettingsPageShell`, `SettingsSection` |
| Read analysis artifact | Detail view | prose | provenance header, Share |
| Charts / usage / KPIs | Detail view | metrics | KPI tiles, one chart story |
| Confirm or short create (≤ ~6 fields) | — | — | Dialog (§5) |
| Inspect or edit a large object | — | — | Drawer (§5) |

---

## 1. Product rules

Workbench that happens to have admin — not admin that happens to have chat.

| Rule | Meaning |
|---|---|
| **Job** | Ask → analysis artifact → share / pin / follow up. |
| **Session** | Conversation may produce a document; leadership opens the document. |
| **Bilingual** | Chrome = one locale (`i18n`). Data may differ. No EN/ZH in one summary line. |

**IA:** Primary rail = operator jobs (conversation, artifacts, knowledge, skills, search). Secondary = one Settings destination — never many equal admin rail buttons. No second persistent sidebar in Settings; in-page tabs/list in canvas ok.

---

## 2. Visual foundation

OKLch verbatim. Append CJK fallbacks to sans stacks: `"PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei"`.

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

One sans for UI + documents. Mono for SQL, ids, field names, URLs, hashes. No display serif.

**shadcn mapping** — product accent = `--primary`; shadcn `--accent` = neutral hover only (`bg-accent` is **not** brand):

| Token | shadcn slot | Token | shadcn slot |
|---|---|---|---|
| `--bg` | `--background` | `--accent` | **`--primary`** |
| `--surface` | `--card`, `--popover` | `--accent-fg` | `--primary-foreground` |
| `--fg` | `--foreground` | `--danger` | `--destructive` |
| `--muted` | `--muted-foreground` | `--focus-ring` | `--ring` |
| `--border` | `--border`, `--input` | hover wash | `--accent` / `--secondary` |

Forbidden: Ant `#1890ff`, Tailwind indigo, leftover shadcn blue `--primary`, raw `bg-emerald-*`. If `.dark` exists, derive from the same recipe.

**Layers:** neutrals 70–90% · accent ≤2 visible hits/screen · semantic 0–5% · no gradient/glow. Charts: `--chart-1`…`--chart-10`; first stop = product accent.

**Type:** scale 1.25, weights 400/500/600 only. CJK: no negative tracking; LH 1.35 for headings/body.

| Role | Size | Role | Size |
|---|---|---|---|
| H1 / H2 / H3 | 32 / 24 / 20px | UI / label / button | 14px |
| Body | 16px | Help / Caption | 13 / 12px |

Comparing numbers: `tabular-nums` + unit + period.

**Shape:** `--radius-control` (controls), `--radius-pane` (panes). Hairline borders. Row hover = darker `--bg`; no zebra. Focus: `:focus-visible` + `--focus-ring`. Disabled ≈45% opacity. Hit targets ≥44px. Icons: Lucide, `currentColor`, no emoji. Button fills: §6.

---

## 3. Application shell

Header (mark, tenant control, locale, user menu with Profile/Settings/Logout) + rail + canvas. Workbench edge-to-edge; other surfaces use page padding. Rail: one active treatment. Search = rail item **or** `⌘K`, not both.

| Surface | Canvas width |
|---|---|
| Workbench | Full; split panes |
| Browse / Configure | Full remaining |
| Detail view | Full, left-aligned; no prose measure cap |

---

## 4. Layout surfaces

Exactly **one** per page. Two jobs → workbench panes or list+drawer. Six surfaces: Workbench · Catalog · Table · Form · Settings stack · Detail view. Overlays/empty/loading = §5, not surfaces.

### Workbench

Split ~40/60 toward artifact. Closed artifact → full column; reopen from pane header. Composer sticky; one solid CTA (Send). Share on artifact = outline if Send is solid. Destructive actions in overflow.

### Catalog

Card/row: name · one-line job · scope chip · owner caption · overflow. Long body in **drawer**. Segmented filters; hide empty segments. One page-level primary.

### Table

Record operations. Two layouts only — **list index** and **list detail**.

**Shared:** identity/status/truncated values/actions columns; ghost or overflow actions; badge **or** switch (not both); 40–44px rows; sticky header; table in `--card` shell; destructive via confirm dialog only; wide tables `table-fixed` + truncate identity col.

**List index:** Page header = identity only (`text-2xl` title + muted description, **no buttons**). Toolbar below: search left, refresh outline + one solid Create/Add right (`ListIndexToolbar`). Row actions: `ContainerRowActions` (Share/Tags/Edit/Delete). Optional filter/tabs between toolbar and table.

**List detail:** `ContainerDetailHeader` = breadcrumb + title + meta only (no CTAs). Toolbar: search, batch outline when selected, one solid Upload/Add, ⋯ for infrequent ops (`ListDetailToolbar`). Optional status bar (e.g. Drive sync) between header and toolbar — no duplicate refresh in header and bar. Container catalog actions stay on parent index only.

**Parent → child routing:** parent = list index, child = list detail; two routes when table is wide (≥~6 cols). No persistent container sidebar.

**Skip list layouts for:** Catalog card grids, Workbench, Detail view.

### Form

Label above field; 13px help under field. Group related fields; compact numerics; no full-bleed 40px inputs. Secrets masked in control with reveal/replace. Save primary; Test outline with in-form result (§5).

### Settings stack

In-page section nav only (tabs/compact list). Policy row: title, consequence, control right. Incomplete/risky counts use `--warn`. One `--card` section chrome: `text-lg` title, muted description, optional header action, body in same card — never loose title + separate card. `text-2xl` reserved for KPI values (Detail metrics) and list index headers only.

**Scaffold:** `SettingsPageShell` + one or more `SettingsSection` cards.

| Settings job | Layout | Primary | Create flow |
|---|---|---|---|
| Record list | section + table (`p-0`) | header or `SettingsListToolbar` | dialog/drawer |
| Config form | section + form body | Save in card | — |
| Multi-domain | tabs + sections/tab | one primary/section | dialog |
| Metrics section | section + Detail metrics modifier | filters in header | — |

**Forbidden on `/settings/*`:** loose `text-2xl` page titles; page-level `ListIndexToolbar`; inline create form below list; bare tables. Table rows: `SettingsRowActions`; status = `Switch` only (+ label in header/`aria-label`).

### Detail view

Read or interpret one artifact/dataset. One modifier per view.

**Shared:** full width, left-aligned; no list toolbar.

**prose:** H1/H2, 16px body, mono for SQL/fields; provenance header; Share = primary when chat hidden; no trust chip.

**metrics:** one quantitative story; KPI tiles same period + unit family (`text-2xl tabular-nums` ok); incomplete series hidden or labelled; chart = trend or single number; filters in page/section header; no invented metrics.

---

## 5. Interaction patterns

On top of §4 surfaces — not layout types.

**Overlay:** Dialog = confirm, short create (≤~6 fields), ~400–480px, verb title, primary + Cancel, dismiss Esc / overlay click if non-destructive. Drawer = inspect/edit large object, ~480–560px, object title, Save in footer, list stays visible. No long documents in dialog. No equal-weight Save + Delete.

**Feedback:** **One channel per event** — never toast + inline/banner for the same outcome. Severity: error (`--danger`), warning (inline `--warn`, not toast), info (muted), success (toast ok for mutations). Persistence: transient = toast; contextual = until edit/retry/navigate; page = until refetch/route change.

| Situation | Channel |
|---|---|
| Field invalid (client) | Inline under control — 13px `text-destructive`, border `--destructive` |
| Form submit rejected (server) | `Alert destructive` top of form/dialog |
| Connection / diagnostic test | Inline next to control — not toast-only |
| Mutation success | Toast via `useNotification` |
| Mutation fail (no form anchor) | Toast: `showError(getApiErrorMessage(err, fallback))` |
| Page/section load fail | `Alert destructive` in canvas |
| Background job queued | Toast info/success |
| Recoverable caution | Inline warn text/badge |
| High-impact / irreversible | `ConfirmationDialog` |
| Permission denied | Page banner |

API errors: **`getApiErrorMessage` only** — no ad-hoc `response.data.detail`. All strings via **`i18n`**; fallbacks name the failed operation. No stack traces in UI. No direct `sonner` imports. Anti-patterns: toast for field validation; toast-only connection tests; `window.confirm` for destructive work; hardcoded English errors.

**Empty / loading:** empty = what/why/next action (no `"—"`). Loading = reuse shell; one spinner language.

---

## 6. Component lookup

| Component | When | How |
|---|---|---|
| `Button` | §4 CTAs | One `default`/view; `destructive` = confirm modal only |
| `Input` / `Select` / `Textarea` / `Checkbox` | forms | label + control + help; invalid = `errorMsg` or rhf message |
| `useNotification` | §5 transient | success/error/info/warning; + `getApiErrorMessage` before error toast |
| `Alert` | §5 persistent | `destructive` errors; neutral inline success (e.g. test ok) |
| `Table` | §4 Table | sticky header; overflow row actions |
| `Card` | forms, metrics tiles | not every table row |
| `SettingsSection` / `SettingsPageShell` | §4 Settings | section chrome; `space-y-6` shell |
| `SettingsListToolbar` | settings searchable lists | in-card; not page-level `ListIndexToolbar` |
| `SettingsRowActions` | settings table rows | ghost edit/delete |
| `ListIndexToolbar` / `ListDetailToolbar` | §4 Table layouts | shared toolbar components |
| `ContainerDetailHeader` | list detail | identity only |
| `ContainerRowActions` | list index rows | Share/Tags/Edit/Delete |
| `Badge` / `Switch` / `Tabs` / `Dropdown` | status, peers, overflow | neutral badges; destructive in menu → confirm |

**Button fills:** primary = accent fill; outline/secondary = surface+border; ghost = quiet wash; destructive = danger fill confirm-only; link = underline. Hover: OKLch L ±0.08; never fade text to muted on hover.

---

## 7. Content

All user-visible strings via `i18n` (`en` + `zh`). Catalog summaries in UI locale; raw multilingual source in drawer. No lorem/fake metrics. Buttons = verbs; page titles = nouns/short jobs.

---

## 8. Lint list

1. ≤2 product-accent hits per screen.
2. ≤1 solid primary per view (list Create/Upload in toolbar, not page header).
3. No solid destructive control in table rows.
4. No raw prompt, policy wall, or secret full value in lists.
5. No second persistent app sidebar.
6. One layout surface per view; Detail = one modifier (`prose` | `metrics`).
7. Metrics: tabular nums + unit + period; no incomparable or invented KPIs.
8. One active-rail treatment product-wide.
9. Logout only in user menu.
10. `:focus-visible` on every control.
11. Hover never lowers text contrast.
12. Lucide icons only; `currentColor`.
13. No gradient wash or colored left-bar on cards.
14. Tokens from §2 only — no raw hex.
15. Settings: `SettingsPageShell` + `SettingsSection`; no loose `text-2xl` titles or page-level `ListIndexToolbar`.
16. One feedback channel per event; `getApiErrorMessage`; toasts via `useNotification` only.
17. Field validation and connection tests inline — not toast-only.

---

## 9. One-sentence system

LingQing is a light, dense, green-accent **analysis workbench**: one shell, one layout surface per view, one primary action, two accent hits, long text in drawers, admin on the full remaining canvas.
