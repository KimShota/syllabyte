import { Text, type StyleProp, type TextProps, type TextStyle } from "react-native";
import { colors, type } from "@/theme/tokens";

type Variant = keyof typeof type;

/** Text in one of the design system's type roles. */
export function T({
  variant = "body",
  color = colors.onSurface,
  style,
  ...rest
}: TextProps & { variant?: Variant; color?: string; style?: StyleProp<TextStyle> }) {
  return <Text {...rest} style={[type[variant], { color }, style]} />;
}
