# Design System Inspired by Wise & Pintrest

## 1. Visual Theme & Atmosphere

Wise's website is a bold, confident fintech platform that communicates "money without borders" through massive typography and a distinctive lime-green accent. The design operates on a warm off-white canvas with near-black text (`#0e0f0c`) and a signature Wise Green (`#9fe870`) — a fresh, lime-bright color that feels alive and optimistic, unlike the corporate blues of traditional banking.

The typography uses Noto Sans SC (思源黑体) as the primary UI typeface — a Pan‑CJK grotesque that provides excellent legibility across Chinese, Latin, and numeric glyphs. It serves all default UI surfaces, navigation, buttons, cards, and data‑dense views. Noto Serif SC (思源宋体) is reserved for long‑form reading contexts such as research reports and analysis pages, lending classical authority to extended prose. Both fonts should be loaded from Google Fonts or a local hosting solution with comprehensive CJK + Latin fallbacks. At display scale (70px, weight 700), Noto Sans SC creates large, inviting headlines with a tight line‑height of 0.85. At smaller sizes, the system is compact: buttons at 12px, captions at 12–14px.

What distinguishes Wise is its green-on-white-on-black material palette. Lime Green (`#9fe870`) appears on buttons with dark green text (`#163300`), creating a nature-inspired CTA that feels fresh. Hover states use `scale(1.05)` expansion rather than color changes — buttons physically grow on interaction. The border-radius system uses 9999px for buttons (pill), 30px–40px for cards, and the shadow system is minimal — just `rgba(14,15,12,0.12) 0px 0px 0px 1px` ring shadows.

**Key Characteristics:**
- Autaut Grotesk for English UI and as the global fallback; Noto Sans SC (思源黑体) for Chinese UI and cards
- Noto Serif SC (思源宋体) for long‑form reports and extended reading content
- Google Fonts (or locally hosted) with comprehensive CJK + Latin fallback stacks
- Lime Green (`#9fe870`) accent with dark green text (`#163300`) — nature‑inspired fintech
- Noto Sans SC body at weight 500 as default — confident, not light
- Near-black (`#0e0f0c`) primary with warm green undertone
- Scale(1.05) hover animations — buttons physically grow
- OpenType `"calt"` on all text
- Semantic color system with comprehensive state management

## 2. Color Palette & Roles

### Primary Brand
- **Near Black** (`#0e0f0c`): Primary text, background for dark sections
- **Wise Green** (`#9fe870`): Primary CTA button, brand accent
- **Dark Green** (`#163300`): Button text on green, deep green accent
- **Light Mint** (`#e2f6d5`): Soft green surface, badge backgrounds
- **Pastel Green** (`#cdffad`): `--color-interactive-contrast-hover`, hover accent

### Semantic
- **Positive Green** (`#054d28`): `--color-sentiment-positive-primary`, success
- **Danger Red** (`#d03238`): `--color-interactive-negative-hover`, error/destructive
- **Warning Yellow** (`#ffd11a`): `--color-sentiment-warning-hover`, warnings
- **Background Cyan** (`rgba(56,200,255,0.10)`): `--color-background-accent`, info tint
- **Bright Orange** (`#ffc091`): `--color-bright-orange`, warm accent

### Neutral
- **Warm Dark** (`#454745`): Secondary text, borders
- **Gray** (`#868685`): Muted text, tertiary
- **Light Surface** (`#e8ebe6`): Subtle green-tinted light surface

## 3. Typography Rules

-### Font Family
- **UI / Cards / Default** (`--font-ui`): Prefer 'Autaut Grotesk' for English content, fall back to 'Noto Sans SC' for Chinese; full stack: 'Autaut Grotesk', 'Noto Sans SC', -apple-system, system-ui, 'Segoe UI', PingFang SC, Microsoft YaHei, Helvetica Neue, Arial, sans-serif
- **Long‑form Reports** (`--font-report`): 'Noto Serif SC', fallbacks: Georgia, 'Times New Roman', STSong, SimSun, 宋体, serif

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|------|------|------|--------|-------------|----------------|-------|
| Display Hero | Noto Sans SC / Autaut Grotesk (en) | 70px (4.38rem) | 700 | 0.85 | normal | Maximum impact, `--font-ui` (zh: Noto Sans SC; en: Autaut Grotesk) |
| Section Heading | Noto Sans SC / Autaut Grotesk (en) | 28px (1.75rem) | 700 | normal | -0.5px | Negative tracking, `--font-ui` (language dependent) |
| Body / UI | Noto Sans SC / Autaut Grotesk (en) | 16px (1.00rem) | 500 | 1.60 | normal | Cards, nav, data; use Autaut Grotesk for English, Noto Sans SC for Chinese (`--font-ui`) |
| Caption Bold | Noto Sans SC | 14px (0.88rem) | 700 | normal | normal | Strong metadata, `--font-ui` |
| Caption | Noto Sans SC | 12px (0.75rem) | 400–500 | 1.50 | normal | Small text, tags, `--font-ui` |
| Button | Noto Sans SC | 12px (0.75rem) | 500 | normal | normal | Button labels, `--font-ui` |
| Report Body | Noto Serif SC | 16px (1.00rem) | 400 | 1.80 | 0.02em | Long‑form reports, `--font-report` |
| Report Heading | Noto Serif SC | 22px (1.375rem) | 600 | 1.30 | -0.3px | Report section titles, `--font-report` |

### Principles
- **Compact type scale**: The range is 12px–70px with a dramatic jump — most functional text is 12–16px, creating a dense, app-like information hierarchy.
- **Warm weight distribution**: 600–700 for headings, 400–500 for body. No ultra-light weights — the type always feels substantial.
- **Negative tracking on headings**: -0.5px on 28px UI headings; -0.3px on report section headings.
- **Dual‑font system with language preference**: prefer Autaut Grotesk for English UI; switch to Noto Sans SC for Chinese UI surfaces. Noto Serif SC remains for long‑form reports.
- **Generous CJK line‑height**: Report body uses 1.80 line‑height to accommodate Noto Serif SC's vertical rhythm for Chinese characters.

## 4. Component Stylings

### Buttons

**Primary Green**
- Background: `#9fe870` (Wise Green)
- Text: `#163300` (Dark Green)
- Padding: 5px 16px
- Radius: 16px (generously rounded, not pill)
- Hover: scale(1.05) — button physically grows
- Active: scale(0.95) — button compresses
- Focus: inset ring + outline

**Secondary Subtle**
- Background: `rgba(22, 51, 0, 0.08)` (dark green at 8% opacity)
- Text: `#0e0f0c`
- Padding: 8px 12px 8px 16px
- Radius: 16px (generously rounded, not pill)
- Same scale hover/active behavior

### Cards & Containers
- Radius: 12px (small), 16px (medium), 30px (large cards/tables)
- Border: `1px solid rgba(14,15,12,0.12)` or `1px solid #9fe870` (green accent)
- Shadow: `rgba(14,15,12,0.12) 0px 0px 0px 1px` (ring shadow)

### Navigation
- Green-tinted navigation hover: `rgba(211,242,192,0.4)`
- Clean header with Wise wordmark
- Pill CTAs right-aligned

## 5. Layout Principles

### Spacing System
- Base unit: 8px
- Scale: 1px, 2px, 3px, 4px, 5px, 8px, 10px, 11px, 12px, 16px, 18px, 19px, 20px, 22px, 24px

### Border Radius Scale
- Minimal (2px): Links, inputs
- Standard (10px): Comboboxes, inputs
- Card (12px): Small cards, buttons, radio
- Medium (16px): Links, medium cards, images
- Large (30px): Feature cards
- Section (40px): Tables, large cards
- Mega (1000px): Presentation elements
- Pill (9999px): All badges
- Circle (50%): Icons, badges

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat (Level 0) | No shadow | Default |
| Ring (Level 1) | `rgba(14,15,12,0.12) 0px 0px 0px 1px` | Card borders |
| Inset (Level 2) | `rgb(134,134,133) 0px 0px 0px 1px inset` | Input focus |

**Shadow Philosophy**: Wise uses minimal shadows — ring shadows only. Depth comes from the bold green accent against the neutral canvas.

### Do's and Don'ts

### Do
- Prefer Autaut Grotesk for English UI and body text; use Noto Sans SC (`--font-ui`) for Chinese UI and cards when content is Chinese
- Use Noto Serif SC (`--font-report`) only inside `.report` / `.long-form` page wrappers
- Apply line-height 0.85 on Noto Sans SC display — ultra-tight is intentional
- Use Lime Green (#9fe870) for primary CTAs with Dark Green (#163300) text
- Apply scale(1.05) hover and scale(0.95) active on buttons
- Load both fonts from Google Fonts or a local host with full CJK weight sets

### Don't
- Don't use Noto Serif SC in cards, navigation, or data-dense UI — serif is for reports only
- Don't use thin font weights — Noto Sans SC at 400 minimum
- Don't use pill-shaped buttons — 16px radius is rounded but not pill
- Don't relax the 0.85 line-height on display — the density is the identity
- Don't use the Wise Green as background for large surfaces — it's for buttons and accents
- Don't skip the scale animation on buttons
- Don't use traditional shadows — ring shadows only

## 8. Responsive Behavior

### Breakpoints
| Name | Width | Key Changes |
|------|-------|-------------|
| Mobile | <576px | Single column |
| Tablet | 576–992px | 2-column |
| Desktop | 992–1440px | Full layout |
| Large | >1440px | Expanded |

## 9. Agent Prompt Guide

### Quick Color Reference
- Text: Near Black (`#0e0f0c`)
- Background: White (`#ffffff` / off-white)
- Accent: Wise Green (`#9fe870`)
- Button text: Dark Green (`#163300`)
- Secondary: Gray (`#868685`)

### Example Component Prompts
- "Create hero: white background. Headline at 96px Noto Sans SC weight 700, line-height 0.85, #0e0f0c text. Green CTA (#9fe870, 16px radius, 5px 16px padding, #163300 text). Hover: scale(1.05)."
- "Build a card: 30px radius, 1px solid rgba(14,15,12,0.12). Title at 22px Noto Sans SC weight 600, body at 16px weight 500. Use `--font-ui`."
- "Build a report page: font-family var(--font-report) (Noto Serif SC). Body 16px weight 400, line-height 1.80. Section headings 22px weight 600. Use `--font-report` on .report wrapper."

### Iteration Guide
1. Noto Sans SC 700 at 0.85 line-height for display — the weight IS the brand
2. Noto Serif SC only on `.report` / `.long-form` page wrappers — never in cards or nav
3. Lime Green for buttons only — dark green text on green background
4. Scale animations (1.05 hover, 0.95 active) on all interactive elements
5. Noto Sans SC weight 500 for body — confident reading weight
6. Load both fonts from Google Fonts: `?family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@400;600`
