import { StyleSheet, View } from "react-native";
import Svg, { Circle, Path, Text as SvgText } from "react-native-svg";
import { Icon } from "../Icon";
import { T } from "../T";
import type { Ku } from "@/data/types";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

const P = colors.player;

/** The frame the player draws for a KU without a rendered file (the design's "micro-lecture" graphic). */
export function SceneView({ ku }: { ku: Ku }) {
  const [a, b] = ku.slides;
  const scene = ku.scene;
  return (
    <View style={styles.wrap} pointerEvents="none">
      <View style={styles.slidePill}>
        <Icon name="description" size={13} color={colors.secondaryContainer} />
        <T variant="codeSm" color={P.textMuted} style={{ fontSize: 11 }}>
          {a === b ? `Slide ${a}` : `Slides ${a}–${b}`}
        </T>
        <T variant="codeSm" color="rgba(255,255,255,0.4)" style={{ fontSize: 11 }}>
          •
        </T>
        <T variant="codeSm" color={colors.secondaryContainer} style={{ fontSize: 11 }}>
          Micro-Lecture
        </T>
      </View>

      {scene.kind === "equation" ? (
        <View style={styles.center}>
          <T variant="codeSm" color={colors.secondaryContainer} style={styles.framework}>
            {scene.framework}
          </T>
          <T variant="caption" color={P.textMuted}>
            {scene.subtitle}
          </T>
          <View style={styles.terms}>
            {scene.terms.map((term, i) => (
              <View key={term.symbol} style={styles.termRow}>
                <View style={[styles.term, term.highlight && styles.termHot]}>
                  <T variant="codeSm" color={term.highlight ? "#fff" : colors.secondaryContainer} style={{ fontSize: 14, fontFamily: fonts.monoBold }}>
                    {term.symbol}
                  </T>
                  <T variant="caption" color={term.highlight ? colors.onPrimaryContainer : P.textMuted} style={{ fontSize: 11, marginTop: 2 }}>
                    {term.label}
                  </T>
                </View>
                {scene.ops[i] ? (
                  <T variant="bodySemibold" color="#94a3b8" style={{ fontSize: 18, marginHorizontal: 6 }}>
                    {scene.ops[i]}
                  </T>
                ) : null}
              </View>
            ))}
          </View>
          {scene.diagram ? (
            <View style={styles.diagram}>
              <Svg width="100%" height={80} viewBox="0 0 240 64">
                <Path d="M 30 18 C 80 18, 90 48, 120 48 C 150 48, 160 18, 210 18" stroke={colors.secondaryFixedDim} strokeDasharray="3 3" strokeWidth={2.5} fill="none" />
                <Circle cx={30} cy={18} r={5} fill={colors.secondaryFixedDim} />
                <Circle cx={120} cy={48} r={6} fill={colors.secondaryContainer} stroke={colors.onSecondaryFixed} strokeWidth={2} />
                <Circle cx={210} cy={18} r={5} fill={colors.tertiaryFixedDim} />
                <SvgText x={120} y={34} fill="#fff" fontSize={10} fontWeight="600" fontFamily={fonts.monoSemibold} textAnchor="middle">
                  {scene.diagram.middle}
                </SvgText>
                <SvgText x={34} y={32} fill={colors.secondaryFixedDim} fontSize={9} fontFamily={fonts.mono} textAnchor="middle">
                  {scene.diagram.left}
                </SvgText>
                <SvgText x={206} y={32} fill={colors.tertiaryFixedDim} fontSize={9} fontFamily={fonts.mono} textAnchor="middle">
                  {scene.diagram.right}
                </SvgText>
              </Svg>
            </View>
          ) : null}
        </View>
      ) : (
        <View style={styles.center}>
          {scene.framework ? (
            <T variant="codeSm" color={colors.secondaryContainer} style={styles.framework}>
              {scene.framework}
            </T>
          ) : null}
          <T variant="titleMobile" color="#fff" style={{ textAlign: "center", marginTop: 4 }}>
            {scene.headline}
          </T>
          <View style={styles.points}>
            {scene.points.map((p) => (
              <View key={p} style={styles.point}>
                <T variant="caption" color={P.textMuted} style={{ textAlign: "center" }}>
                  {p}
                </T>
              </View>
            ))}
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { width: "100%", maxWidth: 340, paddingHorizontal: 24, alignItems: "center", transform: [{ translateY: -24 }] },
  slidePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: radius.full,
    backgroundColor: "rgba(255,255,255,0.1)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    marginBottom: 32,
  },
  center: { width: "100%", alignItems: "center", gap: 4 },
  framework: { fontSize: 11, fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 4 },
  terms: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: 16 },
  termRow: { flexDirection: "row", alignItems: "center" },
  term: {
    minWidth: 70,
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: radius.xl,
    backgroundColor: P.glass,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
  },
  termHot: { backgroundColor: colors.primary, borderColor: "rgba(91,63,214,0.4)", ...shadow.glow },
  diagram: {
    width: "100%",
    marginTop: 20,
    padding: 14,
    borderRadius: radius.xl,
    backgroundColor: "rgba(0,0,0,0.4)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
  },
  points: { gap: 8, marginTop: 20, alignItems: "center" },
  point: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.lg, backgroundColor: P.glass, borderWidth: 1, borderColor: "rgba(255,255,255,0.1)" },
});
