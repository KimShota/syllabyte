---
name: Academic Clarity
colors:
  surface: '#fbf8ff'
  surface-dim: '#dad9e4'
  surface-bright: '#fbf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f4f2fe'
  surface-container: '#eeecf8'
  surface-container-high: '#e8e7f3'
  surface-container-highest: '#e3e1ed'
  on-surface: '#1a1b23'
  on-surface-variant: '#484554'
  inverse-surface: '#2f3039'
  inverse-on-surface: '#f1effb'
  outline: '#797586'
  outline-variant: '#c9c4d7'
  surface-tint: '#5e42d9'
  primary: '#431ebe'
  on-primary: '#ffffff'
  primary-container: '#5b3fd6'
  on-primary-container: '#d7cfff'
  inverse-primary: '#c9bfff'
  secondary: '#006b5d'
  on-secondary: '#ffffff'
  secondary-container: '#98f3e0'
  on-secondary-container: '#007163'
  tertiary: '#733100'
  on-tertiary: '#ffffff'
  tertiary-container: '#984300'
  on-tertiary-container: '#ffcaae'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e5deff'
  primary-fixed-dim: '#c9bfff'
  on-primary-fixed: '#1a0063'
  on-primary-fixed-variant: '#4522c0'
  secondary-fixed: '#98f3e0'
  secondary-fixed-dim: '#7cd7c5'
  on-secondary-fixed: '#00201b'
  on-secondary-fixed-variant: '#005046'
  tertiary-fixed: '#ffdbca'
  tertiary-fixed-dim: '#ffb68e'
  on-tertiary-fixed: '#331200'
  on-tertiary-fixed-variant: '#763300'
  background: '#fbf8ff'
  on-background: '#1a1b23'
  surface-variant: '#e3e1ed'
typography:
  title:
    fontFamily: Manrope
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 38px
  title-mobile:
    fontFamily: Manrope
    fontSize: 26px
    fontWeight: '700'
    lineHeight: 32px
  card-title:
    fontFamily: Manrope
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 26px
  body:
    fontFamily: Manrope
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-semibold:
    fontFamily: Manrope
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 22px
  caption:
    fontFamily: Manrope
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  eyebrow:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.08em
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 2.5rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system establishes an environment of scholarly composure, intellectual depth, and deliberate focus. Tailored for higher-education students navigating dense lecture material, the interface eliminates juvenile gamification mechanisms—eschewing arbitrary XP counters, streaks, badge rituals, and synthetic urgency in favor of quiet academic utility.

The aesthetic philosophy sits at the intersection of modern utilitarian minimalism and refined editorial restraint. Visual structure is disciplined, spacious, and systematic. The experience evokes the feeling of an immaculate university reading room: tactile clarity, deliberate breathing room, high legibility under cognitive load, and visual confidence. Interactions are swift and purposeful, framing AI video generation not as a novelty, but as a rigorous comprehension instrument.

## Colors

The palette is engineered for prolonged scholarly engagement, balancing deep informational contrast against quiet, restful canvas tones:

- **Primary Canvas (`#F2F3F7`)**: An ambient, tinted neutral foundation that mitigates screen glare compared to pure white, establishing high-comfort reading environments.
- **Surface / Card (`#FFFFFF`)**: Pure crisp containers that lift key content blocks cleanly off the neutral background canvas.
- **Ink Primary (`#15161E`)**: High-contrast, dense neutral for maximum typographic sharpness across all display densities.
- **Ink Secondary (`#606474`)**: Muted slate for secondary metadata, structural labels, and supportive captions.
- **Line & Border (`#DADCE5`)**: Subtle structural dividers ensuring spatial discipline without visual noise.
- **Primary Scholastic Violet (`#5B3FD6`)**: The single focal interactive hue, supported by `#4B32B8` (pressed/hover state) and `#ECE8FC` (subtle tint for selection plates and active path tracks).
- **Academic Emerald / Success (`#0B7A6B`)** resting on light tint (`#E0F4F1`): Clear completion and mastery indicator.
- **Scholastic Amber / Alert (`#B45309`)** resting on soft amber tint (`#FBE7D0`): Contextual notices and processing states.

All foreground-background pairs satisfy strict WCAG 2.2 AA standards (minimum 4.5:1 for body copy and 3:1 for graphical components). Information is never conveyed via hue alone; semantic indicators pair iconographic glyphs with explicit textual copy.

## Typography

The typographic hierarchy establishes clear informational cadence through intentional contrast between contemporary humanist geometry and technical monospaced discipline:

- **Manrope** serves as the primary typographic engine. Its open counters and geometric proportion deliver rapid scannability for video lecture outlines, dense syllabus overviews, and contextual notes.
- **JetBrains Mono** operates as an intellectual counterpoint. Applied strictly to eyebrows, chapter markers, timestamps, slide page counters, and metadata tags, it injects structured academic rhythm. Eyebrow roles are consistently styled in uppercase with intentional tracking (`0.08em`).
- **Hierarchy Scaling**: Primary display titles scale smoothly to `26px / 32px` on mobile viewports below 768px, safeguarding layout integrity and preventing awkward line wraps on compact phone displays. Body text remains fixed at `15px / 22px` to protect reading endurance and academic legibility.

## Layout & Spacing

Layouts follow a fluid 12-column grid system on desktop (`min-width: 1024px`) with a maximum page content bound of `1280px`, collapsing to an 8-column layout on tablet (`768px - 1023px`) and a 4-column layout on mobile (`< 768px`).

Grid gutters scale dynamically from `1.5rem` (`24px`) on desktop to `1rem` (`16px`) on mobile devices. The outer canvas padding transitions from `2.5rem` (`40px`) down to `1rem` (`16px`), ensuring full tactile economy on hand-held devices without feeling cramped.

Element spacing strictly leverages an 8pt base modular rhythm (`space-xs: 4px`, `space-sm: 8px`, `space-md: 16px`, `space-lg: 24px`, `space-xl: 40px`). Generous vertical margins surround card modules and lecture sequences to prevent visual clutter and reduce student cognitive fatigue.

## Elevation & Depth

Visual hierarchy relies on structural tonal stacking rather than dramatic spatial projection:

- **Base Ground**: Surface tint `#F2F3F7`.
- **Raised Module (Cards & Containers)**: Flat `#FFFFFF` backed by an ultra-subtle, diffused ambient drop shadow: `0px 2px 8px rgba(21, 22, 30, 0.04), 0px 1px 2px rgba(21, 22, 30, 0.02)` coupled with a delicate `1px solid #DADCE5` border to anchor edges on various displays.
- **Active / Interactive Focus**: On interaction or active node state, cards elevate through a clean accent contour (`border-color: #5B3FD6`) with a refined focus aura: `0px 8px 24px rgba(91, 63, 214, 0.12)`.
- **Tooltips, Floating Popovers & Bubbles**: Elevated using clean ambient shadows: `0px 10px 30px rgba(21, 22, 30, 0.08)` bordered with crisp `1px solid #DADCE5`.
- **Next Up Path Aura**: Next-up path nodes utilize a continuous, gentle dual-ring pulsing aura (`box-shadow: 0 0 0 4px #ECE8FC, 0 0 0 8px rgba(236, 232, 252, 0.5)`) that gently signals readiness without loud, gamified flashing.

## Shapes

The design system adopts a calibrated shape hierarchy tailored to academic software:

- **Cards & Major Content Modules**: Set to a proprietary `20px` corner radius, creating soft, welcoming frames that house video viewports, slide analysis decks, and syllabus summaries.
- **Buttons, Action Controls, and Inputs**: Uniformly styled with a `16px` corner radius, matching the curvature of card corners while retaining strong button affordance.
- **Pills, Badges & Chips**: Styled with fully rounded pill edges (`9999px`) to immediately distinguish them from clickable structural modules and form inputs.
- **Learning Path Nodes**: Circular geometry (`48px x 48px` or `56px x 56px`, `border-radius: 50%`) to create fluid visual flow along curved SVG connectors.

## Components

### Buttons & Interactive Controls
- **Primary Action**: Background `#5B3FD6`, text `#FFFFFF`, border-radius `16px`, height `48px`, font `Manrope 15px/600`. Hover state transitions to `#4B32B8`. Focus ring: `2px solid #5B3FD6` with a `2px` offset.
- **Secondary Action**: Background `#ECE8FC`, text `#5B3FD6`, border-radius `16px`, height `48px`. Hover state: `#E0DBFA`.
- **Outline / Ghost**: Background transparent, border `1px solid #DADCE5`, text `#15161E`. Hover state: background `#FFFFFF`, border `#15161E`.

### Cards
- Surface `#FFFFFF`, border-radius `20px`, border `1px solid #DADCE5`, padding `24px` (desktop) or `16px` (mobile). Includes top eyebrow label (`JetBrains Mono`, tracking `0.08em`, `#606474`), followed by a `card-title` (`Manrope 20px/600`, `#15161E`), body copy, and explicit action targets.

### Status Chips & Badges
- Pill-shaped (`border-radius: 9999px`), padding `6px 14px`, combining a leading 14px SVG icon alongside uppercase/small-caps text (`JetBrains Mono 12px/500`).
- **Success Chip**: Text and icon `#0B7A6B`, background `#E0F4F1`, border `1px solid rgba(11, 122, 107, 0.2)`. Icon: Checkmark circle.
- **Warning / Review Chip**: Text and icon `#B45309`, background `#FBE7D0`, border `1px solid rgba(180, 83, 9, 0.2)`. Icon: Alert triangle.
- **Neutral / Draft Chip**: Text and icon `#606474`, background `#ECEEF3`, border `1px solid #DADCE5`. Icon: Document or dash circle.

### 3-Segment Progress / Level Bars
- Academic milestone bar split cleanly into 3 discrete segments separated by `4px` gaps.
- Total bar height: `8px`. Each segment features `4px` corner radii.
- **Segment States**:
  - *Completed*: Filled with `#5B3FD6`.
  - *In Progress*: Filled with `#ECE8FC` accompanied by an embedded primary bar indicator or strip.
  - *Unreached*: Filled with `#DADCE5`.
- Textual milestone count (e.g., "Segment 2 of 3 • Core Synthesis") sits directly above or below in `JetBrains Mono 12px`, strictly avoiding XP or leveling jargon.

### Winding Learning Path Nodes
Circular node indicators positioned along an SVG spine line (`2px solid #DADCE5` or `#ECE8FC`):
1. **Watched / Completed**: Background `#0B7A6B`, border none, centered white checkmark icon (`#FFFFFF`). Connected spine trailing behind turns `#0B7A6B`.
2. **Next Up (Active)**: Background `#5B3FD6`, centered white play icon. Surrounded by a gentle non-intrusive dual-aura (`box-shadow: 0 0 0 4px #ECE8FC, 0 0 0 8px rgba(236, 232, 252, 0.5)`). Anchored directly beside or above is a callout bubble (`#15161E` background, `#FFFFFF` text, `border-radius: 8px`, padding `4px 10px`, reading "UP NEXT" or "START" in `JetBrains Mono 11px/600`).
3. **Available / Not Watched**: Background `#FFFFFF`, border `2px solid #5B3FD6`, centered Violet node dot (`8px`) or topic number in `JetBrains Mono 13px`.
4. **Skipped**: Background `#ECEEF3`, border `1px solid #DADCE5`, centered subtle skip/forward arrow glyph in `#606474`.
5. **Not Made Yet / Processing**: Background `#F2F3F7`, border `2px dashed #DADCE5`, centered clock or sparkles-loader icon in `#606474`. Accessible tooltip indicates "Awaiting Slide Ingestion".

### Input Fields & Lecture Slide Dropzones
- **Inputs**: Background `#FFFFFF`, border `1px solid #DADCE5`, radius `16px`, height `48px`, padding `0 16px`, font `Manrope 15px`. Focus state shifts border to `#5B3FD6` with a soft violet shadow outline.
- **Slide Dropzone**: Surface `#FFFFFF`, border `2px dashed #DADCE5`, border-radius `20px`, padding `40px 24px`. Transitions to `border-color: #5B3FD6` and background `#ECE8FC` on drag hover. Accompanying instructional text in `Manrope 15px` with metadata format badges in `JetBrains Mono 12px`.