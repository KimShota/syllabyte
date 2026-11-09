import type { ReactNode } from "react";
import { ScrollView, View, type AccessibilityRole, type StyleProp, type TextStyle, type ViewStyle } from "react-native";
import { questionLabel, questionParts } from "@syllabyte/core/questionContent";
import { T } from "./T";
import { colors, fonts, type } from "@/theme/tokens";

/** Symbols remain Unicode text. Code/data blocks keep indentation and scroll without shrinking. */
export function QuestionText({ children, variant = "body", color = colors.onSurface, style, textStyle, accessibilityRole }:
  { children: string; variant?: keyof typeof type; color?: string; style?: StyleProp<ViewStyle>; textStyle?: StyleProp<TextStyle>; accessibilityRole?: AccessibilityRole }) {
  const parts = questionParts(children);
  const rows: ReactNode[] = [];
  let inline: ReactNode[] = [];
  const flush = () => {
    if (!inline.length) return;
    rows.push(<T key={rows.length} variant={variant} color={color} style={textStyle}>{inline}</T>);
    inline = [];
  };
  for (const [index, part] of parts.entries()) {
    if (part.kind === "code") {
      flush();
      rows.push(
        <ScrollView key={`code-${index}`} horizontal style={{ maxWidth: "100%" }} contentContainerStyle={{ paddingVertical: 8 }}>
          <T color={color} style={{ fontFamily: fonts.mono, fontSize: 14, lineHeight: 22 }}>{part.text}</T>
        </ScrollView>,
      );
    } else {
      inline.push(<T key={index} variant={variant} color={color} style={[textStyle, part.kind === "inlineCode" && { fontFamily: fonts.mono }]}>{part.text}</T>);
    }
  }
  flush();
  return <View accessible={accessibilityRole ? true : undefined} accessibilityRole={accessibilityRole}
    accessibilityLabel={accessibilityRole ? questionLabel(children) : undefined}
    style={[{ minWidth: 0, flexShrink: 1 }, style]}>{rows}</View>;
}
