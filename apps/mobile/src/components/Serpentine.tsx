import { useState, type ReactNode, type Ref } from "react";
import { StyleSheet, View, type HostInstance } from "react-native";
import Svg, { Path } from "react-native-svg";

export interface SpineSegment {
  color: string;
  dashed?: boolean;
  width?: number;
}

export interface SerpentineRow {
  key: string;
  height: number;
  /** horizontal centre of this row's node, 0 (left edge) .. 1 (right edge) */
  nodeX: number;
  /** vertical centre of the node from the row's top; defaults to the middle */
  nodeY?: number;
  render: (width: number) => ReactNode;
}

/**
 * Rows stacked top to bottom with a curved spine drawn behind them, through each row's node centre.
 * `segments[i]` styles the curve between row i and row i + 1.
 */
export function Serpentine({
  rows,
  segments,
  turnGap = 0,
  focusKey,
  focusRef,
  onFocusLayout,
}: {
  rows: SerpentineRow[];
  segments: SpineSegment[];
  /** Bend across the empty space at each row boundary, keeping the spine clear of cards. */
  turnGap?: number;
  /** the row a screen opens on (see useScrollToFocus): it gets `focusRef` and reports its layout */
  focusKey?: string | null;
  focusRef?: Ref<HostInstance>;
  onFocusLayout?: () => void;
}) {
  const [width, setWidth] = useState(0);
  const centers: { x: number; y: number }[] = [];
  const boundaries: number[] = [];
  let y = 0;
  for (const row of rows) {
    centers.push({ x: row.nodeX * width, y: y + (row.nodeY ?? row.height / 2) });
    y += row.height;
    boundaries.push(y);
  }
  const totalHeight = y;

  return (
    <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)} style={{ height: totalHeight }}>
      {width > 0 ? (
        <Svg width={width} height={totalHeight} style={StyleSheet.absoluteFill} pointerEvents="none">
          {centers.slice(0, -1).map((a, i) => {
            const b = centers[i + 1];
            const mid = (a.y + b.y) / 2;
            const boundary = boundaries[i];
            const path = turnGap > 0
              ? `M ${a.x} ${a.y} L ${a.x} ${Math.max(a.y, boundary - turnGap / 2)} C ${a.x} ${boundary}, ${b.x} ${boundary}, ${b.x} ${Math.min(b.y, boundary + turnGap / 2)} L ${b.x} ${b.y}`
              : `M ${a.x} ${a.y} C ${a.x} ${mid}, ${b.x} ${mid}, ${b.x} ${b.y}`;
            const seg = segments[i] ?? segments[segments.length - 1];
            if (!seg) return null;
            return (
              <Path
                key={i}
                d={path}
                stroke={seg.color}
                strokeWidth={seg.width ?? 3}
                strokeDasharray={seg.dashed ? "6 6" : undefined}
                strokeLinecap="round"
                fill="none"
              />
            );
          })}
        </Svg>
      ) : null}
      {width > 0
        ? rows.map((row) => {
            const focus = row.key === focusKey;
            return (
              <View key={row.key} style={{ height: row.height }} ref={focus ? focusRef : undefined} onLayout={focus ? onFocusLayout : undefined}>
                {row.render(width)}
              </View>
            );
          })
        : null}
    </View>
  );
}
