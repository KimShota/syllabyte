/**
 * Design tokens from the "Academic Clarity" design system
 * (syllabyte_mobile_design/academic_clarity/DESIGN.md and the screens' Tailwind configs).
 */
import type { TextStyle } from "react-native";

export const colors = {
  surface: "#fbf8ff",
  surfaceDim: "#dad9e4",
  surfaceContainerLowest: "#ffffff",
  surfaceContainerLow: "#f4f2fe",
  surfaceContainer: "#eeecf8",
  surfaceContainerHigh: "#e8e7f3",
  surfaceContainerHighest: "#e3e1ed",
  surfaceVariant: "#e3e1ed",
  onSurface: "#1a1b23",
  onSurfaceVariant: "#484554",
  inverseSurface: "#2f3039",
  inverseOnSurface: "#f1effb",
  outline: "#797586",
  outlineVariant: "#c9c4d7",

  /** the single interactive hue */
  primary: "#5b3fd6",
  /** deeper violet used for avatars, the quiz's selected state and the drawer's CTA */
  primaryDeep: "#431ebe",
  primaryPressed: "#4b32b8",
  onPrimary: "#ffffff",
  onPrimaryContainer: "#d7cfff",
  primaryFixed: "#e5deff",
  primaryFixedDim: "#c9bfff",
  primaryTint: "#ece8fc",
  onPrimaryFixed: "#1a0063",

  secondary: "#006b5d",
  secondaryContainer: "#98f3e0",
  onSecondaryContainer: "#007163",
  secondaryFixedDim: "#7cd7c5",
  onSecondaryFixedVariant: "#005046",
  onSecondaryFixed: "#00201b",

  tertiary: "#733100",
  tertiaryFixed: "#ffdbca",
  tertiaryFixedDim: "#ffb68e",

  error: "#ba1a1a",
  errorSoft: "#ff8a80",

  /** the dark, immersive player */
  player: {
    bg: "#0a0a0a",
    panel: "rgba(23,23,23,0.96)",
    glass: "rgba(255,255,255,0.08)",
    glassStrong: "rgba(255,255,255,0.2)",
    border: "rgba(255,255,255,0.12)",
    borderStrong: "rgba(255,255,255,0.3)",
    scrim: "rgba(0,0,0,0.5)",
    text: "#ffffff",
    textMuted: "#cbd5e1",
    textFaint: "rgba(255,255,255,0.6)",
  },
} as const;

export const fonts = {
  regular: "Manrope_400Regular",
  medium: "Manrope_500Medium",
  semibold: "Manrope_600SemiBold",
  bold: "Manrope_700Bold",
  extraBold: "Manrope_800ExtraBold",
  mono: "JetBrainsMono_400Regular",
  monoMedium: "JetBrainsMono_500Medium",
  monoSemibold: "JetBrainsMono_600SemiBold",
  monoBold: "JetBrainsMono_700Bold",
} as const;

/** Type roles. Mono roles are for eyebrows, timestamps, slide counters and tags only. */
export const type = {
  title: { fontFamily: fonts.bold, fontSize: 30, lineHeight: 36, letterSpacing: -0.4 },
  titleMobile: { fontFamily: fonts.bold, fontSize: 26, lineHeight: 32, letterSpacing: -0.3 },
  cardTitle: { fontFamily: fonts.semibold, fontSize: 20, lineHeight: 26 },
  body: { fontFamily: fonts.regular, fontSize: 15, lineHeight: 22 },
  bodySemibold: { fontFamily: fonts.semibold, fontSize: 15, lineHeight: 22 },
  caption: { fontFamily: fonts.regular, fontSize: 13, lineHeight: 18 },
  eyebrow: { fontFamily: fonts.monoMedium, fontSize: 13, lineHeight: 18, letterSpacing: 1, textTransform: "uppercase" },
  codeSm: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 16, letterSpacing: 0.5 },
} satisfies Record<string, TextStyle>;

export const radius = { sm: 4, md: 8, lg: 12, xl: 16, card: 20, sheet: 28, full: 9999 } as const;

export const space = { xs: 4, sm: 8, md: 16, lg: 24, xl: 40, gutter: 16 } as const;

/** Shadows from DESIGN.md "Elevation & Depth" (boxShadow is native on iOS and Android since RN 0.76). */
export const shadow = {
  /** raised module: an ultra-subtle ambient shadow */
  card: { boxShadow: "0px 2px 8px rgba(21,22,30,0.05)" },
  /** active / interactive focus */
  raised: { boxShadow: "0px 4px 16px rgba(91,63,214,0.12)" },
  glow: { boxShadow: "0px 8px 20px rgba(91,63,214,0.3)" },
  /** popovers, sheets, floating controls */
  float: { boxShadow: "0px 10px 30px rgba(0,0,0,0.25)" },
} as const;
