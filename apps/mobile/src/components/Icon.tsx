import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import type { ComponentProps } from "react";

export type IconName = ComponentProps<typeof MaterialIcons>["name"];

/** Material icons, the set the designs use (Material Symbols Outlined). */
export function Icon({ name, size = 20, color }: { name: IconName; size?: number; color: string }) {
  return <MaterialIcons name={name} size={size} color={color} accessibilityElementsHidden importantForAccessibility="no" />;
}
