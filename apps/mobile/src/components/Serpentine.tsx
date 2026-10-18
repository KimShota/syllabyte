import { useState, type ReactNode } from "react";
import { StyleSheet, View } from "react-native";
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
export function Serpentine({ rows, segments }: { rows: SerpentineRow[]; segments: SpineSegment[] }) {
  const [width, setWidth] = useState(0);
  const centers: { x: number; y: number }[] = [];
  let y = 0;
  for (const row of rows) {
    centers.push({ x: row.nodeX * width, y: y + (row.nodeY ?? row.height / 2) });
    y += row.height;
  }
  const totalHeight = y;

  return (
    <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)} style={{ height: totalHeight }}>
      {width > 0 ? (
        <Svg width={width} height={totalHeight} style={StyleSheet.absoluteFill} pointerEvents="none">
          {centers.slice(0, -1).map((a, i) => {
            const b = centers[i + 1];
            const mid = (a.y + b.y) / 2;
            const seg = segments[i] ?? segments[segments.length - 1];
            if (!seg) return null;
            return (
              <Path
                key={i}
                d={`M ${a.x} ${a.y} C ${a.x} ${mid}, ${b.x} ${mid}, ${b.x} ${b.y}`}
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
        ? rows.map((row) => (
            <View key={row.key} style={{ height: row.height }}>
              {row.render(width)}
            </View>
          ))
        : null}
    </View>
  );
}
