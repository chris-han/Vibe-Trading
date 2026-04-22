# Design System — Wise & Pinterest Inspired

## 1. Visual Theme & Atmosphere

Wise's website is a bold, confident fintech platform that communicates "money without borders" through massive typography and a distinctive lime-green accent. The design operates on a warm off-white canvas with near-black text (`#0e0f0c`) and a signature Wise Green (`#9fe870`) — a fresh, lime-bright color that feels alive and optimistic, unlike the corporate blues of traditional banking.

The typography uses **Autaut Grotesk** and **Noto Sans SC** (思源黑体) as the primary UI typeface. Autaut Grotesk is for English, Noto Sans SC is a Pan‑CJK grotesque that provides excellent legibility across Chinese, Latin, and numeric glyphs. They serve all default UI surfaces, navigation, buttons, cards, and data‑dense views. Noto Serif SC (思源宋体) is reserved for long‑form reading contexts such as research reports and analysis pages, lending classical authority to extended prose. Both fonts should be loaded from Google Fonts or a local hosting solution with comprehensive CJK + Latin fallbacks.

**Key Characteristics:**
- Autaut Grotesk for English UI and as the global fallback; Noto Sans SC (`--font-ui`) for Chinese UI and cards
- Noto Serif SC only inside `.report` / `.long-form` page wrappers — never in cards or nav
- Lime Green (`#9fe870`) for primary CTAs with Dark Green (`#163300`) text — nature‑inspired fintech
- Noto Sans SC body at weight 500 as default — confident, not light
- Near-black (`#0e0f0c`) primary with warm green undertone
- Scale(1.05) hover and scale(0.95) active on buttons
- OpenType `"calt"` on all text
- Minimal shadow philosophy — depth comes from bold green accent against neutral canvas

---

## 2. Color Palette & Roles

### Primary Brand (Hex)
| Token | Hex | Role |
|-------|-----|------|
| `--near-black` | `#0e0f0c` | Primary text, code surface bg, deep shadows |
| `--semantier-green` | `#9fe870` | Primary CTA, brand accent, keyword highlights |
| `--dark-green` | `#163300` | Button text on green, deep green accent, active nav indicator |
| `--light-mint` | `#e2f6d5` | Soft green surface, badge backgrounds |
| `--pastel-green` | `#cdffad` | Interactive contrast hover, code title/class colors |
| `--bright-orange` | `#ffc091` | Code string/attr colors |
| `--warning-yellow` | `#ffd11a` | Code number/literal colors |
| `--focus-blue` | `#435ee5` | Focus rings, outer focus border |

### Neutral (Hex)
| Token | Hex | Role |
|-------|-----|------|
| `--warm-dark` | `#454745` | Secondary text, borders |
| `--warm-gray` | `#868685` | Muted text, tertiary |
| `--light-surface` | `#e8ebe6` | Subtle green-tinted light surface, code surface text base |

### Semantic Colors (HSL CSS Variables)
These are the core shadcn/ui-style tokens. **Light mode values are HSL triplets** (used as `hsl(var(--token))`).

| Token | Light Mode | Dark Mode | Tailwind Utility |
|-------|-----------|-----------|-----------------|
| `--background` | `80 9% 96%` | `80 6% 10%` | `bg-background` |
| `--foreground` | `100 8% 5%` | `60 10% 94%` | `text-foreground` |
| `--card` | `0 0% 100%` | `80 5% 13%` | `bg-card` |
| `--card-foreground` | `100 8% 5%` | `60 10% 94%` | `text-card-foreground` |
| `--primary` | `96 75% 67%` | `96 75% 67%` | `bg-primary` |
| `--primary-foreground` | `96 100% 10%` | `96 100% 10%` | `text-primary-foreground` |
| `--muted` | `80 9% 91%` | `80 5% 18%` | `bg-muted` |
| `--muted-foreground` | `100 3% 40%` | `60 5% 55%` | `text-muted-foreground` |
| `--destructive` | `356 65% 51%` | `356 55% 55%` | `bg-destructive` |
| `--destructive-foreground` | `0 0% 100%` | `0 0% 100%` | `text-destructive-foreground` |
| `--border` | `80 5% 80%` | `80 5% 22%` | `border-border` |
| `--success` | `152 88% 17%` | `96 60% 55%` | `text-success` |
| `--danger` | `356 65% 51%` | `356 55% 60%` | `text-danger` |
| `--warning` | `48 100% 55%` | `48 90% 55%` | `text-warning` |
| `--info` | `197 100% 61%` | `197 70% 60%` | `text-info` |

### Dark-Mode-Only Hex Tokens (Tailwind Config)
| Token | Hex | Role |
|-------|-----|------|
| `warm-white` | `#f5f5f0` | Warm off-white reference |
| `dark-surface` | `#1a1a16` | Dark surface layer |
| `dark-surface-2` | `#22221e` | Elevated dark surface |
| `dark-border` | `#2d2d28` | Dark mode border reference |
| `dark-muted` | `#91918c` | Dark mode muted text reference |

### Positive / Semantic Hex Aliases
| Token | Hex | Role |
|-------|-----|------|
| `--positive-green` | `#054d28` | Success states |
| `--danger-red` | `#d03238` | Error / destructive |

### Semantier Morandi Swatch Principle
- Large surfaces stay muted and warm: near-black, off-white, light-surface, warm-dark, and warm-gray carry structure.
- Accent color is reserved for decisive interaction only: `--semantier-green` is the active state, selected state, and primary CTA in both light and dark themes.
- Accent-adjacent UI must keep a dark structural edge: when `--semantier-green` sits on a light or dark field, pair it with `--dark-green` for borders, icon strokes, or label text so the state remains legible at a glance.
- Focus indication is not green: interactive focus rings use `--focus-blue` so focus and selection do not collapse into the same signal.
- When a component needs an unselected fill that the base palette does not explicitly name, use the quiet surface swatch first: `--light-surface` in light mode and the dark card/card2 family in dark mode.

---

## 3. Typography Rules

### Font Family
```css
/* UI / Cards / Default */
--font-ui: 'Autaut Grotesk', 'Times New Roman', -apple-system, system-ui,
           'Noto Sans SC', 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei',
           'Hiragino Kaku Gothic Pro', 'Meiryo', 'MS PGothic', Arial, sans-serif;

/* Reports / Long-form */
--font-report-ui: 'Autaut Grotesk', 'Times New Roman', -apple-system, system-ui,
                  'Noto Sans SC', 'Segoe UI', Roboto, 'PingFang SC',
                  'Microsoft YaHei', Arial, sans-serif;
```

**Loading strategy:**
- **Noto Sans SC**: Google Fonts `@import` with weights 400, 500, 700, `display=swap`
- **Autaut Grotesk**: Self-hosted `/font/AutautGrotesk-Regular.woff2`, `font-weight: 400`, `font-display: swap`
- **JetBrains Mono**: Google Fonts or self-hosted for monospace

### ⚠️ Autaut Grotesk Weight Limitation
**Only weight 400 (Regular) is loaded.** The `@font-face` declaration loads a single static file:
```css
@font-face {
  font-family: "Autaut Grotesk";
  src: url("/font/AutautGrotesk-Regular.woff2") format("woff2");
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
```

The variable font file (`AutautGrotesk-VF.woff2`) exists in `public/font/` but is **not currently loaded**.
`Monument Grotesk` files also exist in `public/font/` but are **unused** in the current codebase.

**Result:** `font-medium` (500), `font-semibold` (600), and `font-bold` (700) are **browser-synthesized** (faux bold). The browser algorithmically thickens the 400 glyphs. This is intentional in the current implementation — all UI text uses these weights extensively.

### Hierarchy

**Note on weights:** Only 400 is loaded for Autaut Grotesk. 500/600/700 are browser-synthesized. Noto Sans SC and Noto Serif SC load real weights from Google Fonts.

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|------|------|------|--------|-------------|----------------|-------|
| Display Hero | Noto Sans SC / Autaut Grotesk (en) | 70px (4.38rem) | 700 | 0.85 | normal | Maximum impact, `--font-ui`. 700 is synthesized for Autaut Grotesk. |
| Section Heading | Noto Sans SC / Autaut Grotesk (en) | 28px (1.75rem) | 700 | normal | -0.5px | Negative tracking. 700 is synthesized for Autaut Grotesk. |
| Body / UI | Noto Sans SC / Autaut Grotesk (en) | 16px (1.00rem) | 500 | 1.60 | normal | Cards, nav, data; `--font-ui`. 500 is synthesized for Autaut Grotesk. |
| Caption Bold | Noto Sans SC | 14px (0.88rem) | 700 | normal | normal | Strong metadata. Real 700 from Google Fonts. |
| Caption | Noto Sans SC | 12px (0.75rem) | 400–500 | 1.50 | normal | Small text, tags |
| Button | Noto Sans SC | 12px (0.75rem) | 500 | normal | normal | Button labels. 500 is synthesized for Autaut Grotesk. |
| Report Body | Noto Serif SC | 16px (1.00rem) | 400 | 1.80 | 0.02em | Long‑form reports. Real 400 from Google Fonts. |
| Report Heading | Noto Serif SC | 22px (1.375rem) | 600 | 1.30 | -0.3px | Report section titles. Real 600 from Google Fonts. |

### Implementation Patterns
```css
body {
  font-family: var(--font-ui);
  font-feature-settings: "calt" 1;
}

.report, .long-form {
  font-family: var(--font-report-ui);
  font-feature-settings: normal;
  line-height: 1.8;
}
```

### Compact Type Scale
- Range: 12px–70px with dramatic jump
- Most functional text: 12–16px
- Heavy use of explicit sizes: `text-[11px]`, `text-[13px]`, `text-[10px]`, `text-[9px]` for UI chrome
- Standard scale: `text-xs`, `text-sm`, `text-base`, `text-xl`, `text-3xl`, `text-5xl`

---

## 4. Brand Identity & Logo

### Logo Assets

| File | Size | Usage | Notes |
|------|------|-------|-------|
| `logo.svg` | 32×32px (`h-8 w-8`) | Sidebar brand mark | Primary navigation logo. `rounded-button object-contain shrink-0 bg-transparent` |
| `logo-wireframe.svg` | 56×56px (`h-14 w-14`) | Welcome screen hero | Centered inside a `rounded-button bg-primary shadow-sm` container |
| `favicon.svg` | — | Browser tab icon | Standard SVG favicon |

### Dead Assets (unused in current build)
The following files exist in `public/` but are **not referenced** anywhere in the source:
- `semantier-logo.png`
- `semantier-logo-text-light.png`
- `smantier-logo-text.png`

### Wordmark
The brand name "semantier" is rendered as **plain text**, not as an image.

Wordmark rules:
- Always render it as lowercase `semantier`
- Always use Autaut Grotesk for the wordmark on UI surfaces
- Never title-case or uppercase the wordmark in navigation, splash, auth, or empty states

**Sidebar (expanded)**
- Layout: `flex items-center gap-2`
- Mark: `h-8 w-8 rounded-button object-contain shrink-0 bg-transparent`
- Wordmark: lowercase `semantier` in Autaut Grotesk, `font-bold text-base text-foreground`

**Sidebar (collapsed)**
- Layout: `flex items-center justify-center`
- Mark: `h-8 w-8 rounded-button object-contain shrink-0 bg-transparent`
- Wordmark hidden

**Welcome / Hero screen**
- Container: `mx-auto flex h-14 w-14 items-center justify-center rounded-button bg-primary shadow-sm`
- Mark: `block h-14 w-14 object-contain object-center`
- Wordmark: lowercase `semantier` in Autaut Grotesk, `text-xl font-bold tracking-tight text-foreground md:text-2xl`

### Logo Styling Rules
- **Never** use a PNG logo for the UI wordmark — always use plain text with `font-bold`
- Sidebar mark is `32px` inside a flex row with `gap-2`
- Welcome mark is `56px` inside a `64px` primary-green rounded square (`rounded-button` = 16px radius)
- Both marks use `object-contain` and `bg-transparent`
- `alt` text: `"semantier logo"`

---

## 5. Component Stylings

### Buttons

**Primary Green CTA**
- Background: `bg-primary` (`var(--primary)`, `#9fe870`)
- Text: `text-primary-foreground` (`var(--primary-foreground)`, `#163300`)
- Padding: `px-5 py-2`
- Radius: `rounded-button` (16px)
- Typography: `text-sm font-medium`
- Transition: `transition-colors`
- Hover: `hover:bg-primary/90 hover:scale-105`
- Active: `active:scale-95`
- Cursor: `cursor-pointer`

**Secondary / Outline**
- Background: `bg-background`
- Border: `border border-border`
- Text: `text-sm font-medium text-foreground`
- Padding: `px-4 py-2.5`
- Radius: `rounded-button` (16px)
- Hover: `hover:bg-muted`
- Transition: `transition-colors`

**Ghost / Icon**
- Background: `bg-muted/80` → `hover:bg-muted`
- Text: `text-muted-foreground` → `hover:text-foreground`
- Padding: `p-1.5`
- Radius: `rounded-button` (16px)
- Transition: `transition-opacity`

**Destructive Circular**
- Size: `w-9 h-9`
- Shape: `rounded-full`
- Background: `bg-destructive`
- Text: `text-destructive-foreground font-medium`
- Hover: `hover:bg-destructive/90`
- Transition: `transition-colors`

**Send Circular**
- Size: `w-9 h-9`
- Shape: `rounded-full`
- Background: `bg-primary`
- Text: `text-primary-foreground font-medium`
- Disabled: `disabled:opacity-40`
- Hover: `hover:bg-primary/90`
- Transition: `transition-colors`

### Toggle / Switch

**Switch Track — Off**
- Background: light mode uses `--light-surface`; dark mode uses the elevated dark card swatch, not pure black
- Border: `--warm-gray` in light mode, `--warm-dark` in dark mode
- Purpose: the off state must remain visible against the page background without borrowing accent color

**Switch Track — On**
- Background: `--semantier-green` in both light and dark modes
- Border: `--dark-green`
- Purpose: the active state should read as a branded affirmative control, not a generic neutral toggle

**Switch Thumb**
- Fill: white or card-white equivalent
- Border: a subtle neutral edge so the thumb stays visible on warm light surfaces
- Motion: translate only; avoid glow effects and decorative gradients

**Switch Focus**
- Ring: `--focus-blue`
- Do not reuse the green active state for keyboard focus

### Cards & Containers

**Standard Card**
- Radius: `rounded-card` (20px)
- Border: `border border-border`
- Background: `bg-card`
- Padding: `p-6`
- Gap: `space-y-3`
- Shadow: `shadow-sm` (optional)

**Message Bubble (User)**
- Radius: `rounded-card rounded-tr-sm`
- Background: `bg-primary`
- Text: `text-primary-foreground text-sm`
- Padding: `px-4 py-2.5`

**Error Card**
- Radius: `rounded-card`
- Border: `border border-destructive/30`
- Background: `bg-destructive/10`
- Padding: `px-4 py-3`

**Metrics Card**
- Layout: `grid gap-1.5`
- Radius: `rounded-card`
- Border: `border border-border`
- Background: `bg-muted/50`
- Padding: `p-3`

### Navigation

**Nav Item (Base)**
- Layout: `flex items-center`
- Radius: `rounded-button`
- Typography: `text-sm font-medium`
- Transition: `transition-all duration-150`

**Nav Item — Expanded**
- Layout: `gap-3 px-3 py-2.5`

**Nav Item — Collapsed**
- Layout: `justify-center p-2`

**Nav Item — Active State**
- Background: `bg-primary`
- Text: `text-primary-foreground`

**Nav Item — Inactive State**
- Text: `text-muted-foreground`
- Hover: `hover:bg-muted hover:text-foreground hover:scale-[1.02]`

### Do's and Don'ts

#### Do
- Prefer Autaut Grotesk for English UI and body text; use Noto Sans SC (`--font-ui`) for Chinese UI and cards when content is Chinese
- Use Noto Serif SC (`--font-report-ui`) only inside `.report` / `.long-form` page wrappers
- Apply line-height 0.85 on Noto Sans SC display — ultra-tight is intentional
- Use Lime Green (#9fe870) for primary CTAs with Dark Green (#163300) text
- Apply scale(1.05) hover and scale(0.95) active on buttons
- Load both fonts from Google Fonts or a local host with full CJK weight sets
- Use `cn()` for all conditional class merging

#### Don't
- Don't use Noto Serif SC in cards, navigation, or data-dense UI — serif is for reports only
- Don't use thin font weights — Noto Sans SC at 400 minimum
- Don't use pill-shaped buttons — 16px radius is rounded but not pill
- Don't relax the 0.85 line-height on display — the density is the identity
- Don't use the Wise Green as background for large surfaces — it's for buttons and accents
- Don't skip the scale animation on buttons
- Don't use traditional shadows — ring shadows only
- Don't load `AutautGrotesk-VF.woff2` or `Monument Grotesk` unless you explicitly intend to use them — they are present in `public/font/` but unused in the current frontend

---

## 6. Border Radius Scale

| Token / Class | Value | Usage |
|---------------|-------|-------|
| `rounded-sm` | `calc(var(--radius) - 8px)` (~4px) | Inputs, small elements |
| `rounded-md` | `calc(var(--radius) - 4px)` (~12px) | Comboboxes, inputs |
| `rounded-lg` | `var(--radius)` (~16px) | Containers, timelines |
| `rounded-button` | **16px** | Buttons, badges, nav items |
| `rounded-card` | **20px** | Cards, message bubbles, modals |
| `rounded-comfortable` | **20px** | Alias for card |
| `rounded-section` | **32px** | Large sections, feature cards |
| `rounded-hero` | **40px** | Hero containers, tables |
| `rounded-full` | 9999px | Circular icons, avatars, send buttons |

---

## 7. Depth & Elevation

The project uses a **very restrained, minimal shadow palette**:

| Value | Usage |
|-------|-------|
| `shadow-sm` | Capability chips, welcome header, feature cards, thinking timeline, scroll-to-bottom button |
| `shadow-sm shadow-black/5` | User auth card in sidebar |
| `shadow-md` | Feature cards on hover |
| `shadow-lg` | Scroll-to-bottom button, upload dropdown menu |
| `shadow-[0_24px_80px_rgba(14,15,12,0.12)]` | Error panel page layout |
| `box-shadow: rgba(14, 15, 12, 0.12) 0 0 0 1px` | Run-code surface border (ring shadow) |

**No custom elevation scale** beyond Tailwind defaults. The design relies more on **border contrast** (`border-border`) than on drop shadows for elevation.

---

## 8. Dark Mode Strategy

### Implementation
- **Strategy**: `class` (manual toggle via CSS class on `<html>`)
- **Hook**: `useDarkMode.ts`
  - Reads `localStorage` key `"qa-theme"` first
  - Falls back to `prefers-color-scheme: dark`
  - Toggles `document.documentElement.classList.toggle("dark", dark)`
  - Persists choice to `localStorage`

### Color Shift Philosophy
Dark mode is **warm-tinted**, not cool/blue:
- Background: `80 6% 10%` (warm dark with olive tint)
- Foreground: `60 10% 94%` (warm off-white)
- Borders: `80 5% 22%` (olive-tinted)
- Primary (`semantier-green`): **identical** in both modes for brand consistency
- Semantic colors soften in dark mode (success: `96 60% 55%`, danger: `356 55% 60%`)

---

## 9. Layout & Spacing

### Base Unit: 8px
### Scale
1px, 2px, 3px, 4px, 5px, 8px, 10px, 11px, 12px, 16px, 18px, 19px, 20px, 22px, 24px

### Common Patterns
| Context | Pattern |
|---------|---------|
| Page padding | `p-6`, `p-8` |
| Sidebar padding | `p-2` (collapsed nav), `p-4` (footer expanded) |
| Card internal | `p-3` (compact), `p-4`, `p-6` |
| Section gaps | `space-y-4`, `gap-4`, `gap-6`, `mt-16` |
| Inline gaps | `gap-1.5`, `gap-2`, `gap-3` |

### Content Width Constraints
- Chat content: `max-w-3xl mx-auto`
- Home hero: `max-w-2xl`
- Feature grid: `max-w-4xl`

---

## 10. Animation & Transition Conventions

### Timing
| Duration | Usage |
|----------|-------|
| `duration-150` | Nav items, session list items, icon buttons |
| `duration-200` | Sidebar collapse/expand, accordion expand, chevron rotate |
| `duration-500` | Swarm progress bar width |

### Motion Patterns
| Pattern | Implementation |
|---------|----------------|
| Hover lift | `hover:scale-[1.02]`, `hover:scale-105` |
| Active press | `active:scale-95` |
| Opacity reveal | `opacity-0 group-hover:opacity-100 transition-opacity` |
| Fade/slide | `transition-all` on height, max-height, opacity, margin |
| Loading | `animate-pulse` (skeletons, streaming cursor) |
| Spin | `animate-spin` (Loader2 icons, refresh) |

### Backdrop Blur
- Chat input form: `bg-background/80 backdrop-blur-sm`
- Upload menu: `bg-background/95 backdrop-blur-sm`

---

## 11. Component Composition Patterns

### `cn()` Utility
```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```
Used ubiquitously for conditional class merging, especially for active/hover/disabled states.

### Conditional State Composition
Pattern for merging conditional states into a single class string:

**Base + conditional layout + conditional state**
```
flex items-center rounded-button text-sm font-medium transition-all duration-150
[expanded]  → gap-3 px-3 py-2.5
[collapsed] → justify-center p-2
[active]    → bg-primary text-primary-foreground
[inactive]  → text-muted-foreground hover:bg-muted hover:text-foreground hover:scale-[1.02]
```

### Group Hover Reveal
Pattern for revealing action buttons on parent hover:

**Parent**
- `group`

**Child (initially hidden)**
- `opacity-0 group-hover:opacity-100 transition-opacity`

---

## 12. Responsive Behavior

### Breakpoints
| Name | Width | Key Changes |
|------|-------|-------------|
| Mobile | <576px | Single column |
| Tablet | 576–992px | 2-column |
| Desktop | 992–1440px | Full layout |
| Large | >1440px | Expanded |

---

## 13. Agent Prompt Guide

### Quick Color Reference
- Text: Near Black (`#0e0f0c`)
- Background: White (`#ffffff` / off-white `80 9% 96%`)
- Accent: Wise Green (`#9fe870`)
- Button text: Dark Green (`#163300`)
- Secondary: Gray (`#868685`)
- Muted surface: `hsl(var(--muted))`
- Border: `hsl(var(--border))`

### Example Component Prompts

**Primary CTA Button**
```
Create a primary button: rounded-button (16px), bg-primary (#9fe870), text-primary-foreground (#163300), px-5 py-2, text-sm font-medium. Hover: hover:bg-primary/90 + hover:scale-105. Active: active:scale-95.
```

**Standard Card**
```
Build a card: rounded-card (20px), border border-border, bg-card, p-6, optional shadow-sm. Title at text-base font-semibold, body at text-sm text-muted-foreground.
```

**Navigation Item**
```
Create a nav link: flex items-center, rounded-button, text-sm font-medium, transition-all duration-150. Active: bg-primary text-primary-foreground. Inactive: text-muted-foreground hover:bg-muted hover:text-foreground hover:scale-[1.02].
```

**Report Page**
```
Build a report page: wrapper with .report class (font-family var(--font-report-ui), line-height 1.8). Body 16px weight 400, section headings 22px weight 600. Use prose for markdown rendering with prose-sm dark:prose-invert.
```

### Iteration Guide
1. Noto Sans SC 700 at tight line-height for display — the weight IS the brand
2. Noto Serif SC only on `.report` / `.long-form` wrappers — never in cards or nav
3. Lime Green for buttons only — dark green text on green background
4. Scale animations (1.05 hover, 0.95 active) on all interactive elements
5. Noto Sans SC weight 500 for body — confident reading weight
6. Prefer `border-border` and `bg-card` over shadows for elevation
7. Use `cn()` for all conditional class merging
8. Load fonts from Google Fonts: `?family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@400;600`
