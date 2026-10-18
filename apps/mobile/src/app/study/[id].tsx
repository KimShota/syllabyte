import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, TextInput, View, type ScrollViewInstance } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@syllabyte/core/api/client";
import type { BatteryView } from "@syllabyte/core/api/types";
import type { Instrument, InstrumentItem, ResponseFormat } from "@syllabyte/core/content/instruments";
import { visibleItems } from "@syllabyte/core/logic/instruments";
import type { BatteryRecord } from "@syllabyte/core/types";
import { Button } from "@/components/Button";
import { IconButton } from "@/components/Header";
import { T } from "@/components/T";
import { colors, fonts, radius, shadow, type } from "@/theme/tokens";

type Answers = BatteryRecord["answers"];
type Value = number | string | null;

function close() {
  if (router.canGoBack()) router.back();
  else router.replace("/");
}

/**
 * A questionnaire battery (plan/study-instruments-plan.md): one instrument per page, one tap per item, and any
 * question can be skipped, but on purpose (I10). Answers save as they are given, so leaving and coming back resumes.
 */
export default function Study() {
  const { id } = useLocalSearchParams<{ id: string }>();
  // read once: the page keeps its own copy of the answers while the student works through it
  const [battery, setBattery] = useState<BatteryView | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    api.getBattery(id).then(
      (b) => live && setBattery(b),
      () => live && setBattery(null),
    );
    return () => {
      live = false;
    };
  }, [id]);

  if (battery === undefined) return <View style={styles.screen} />;
  if (battery === null) return <Message title="Nothing to answer here" body="This questionnaire isn't open for you." />;
  return <Battery battery={battery} />;
}

function firstOpenPage(instruments: Instrument[], answers: Answers): number {
  const i = instruments.findIndex((ins) => visibleItems(ins, answers).some((it) => !(it.id in answers)));
  return i === -1 ? instruments.length - 1 : i;
}

function Battery({ battery }: { battery: BatteryView }) {
  const insets = useSafeAreaInsets();
  const { instruments } = battery;
  const [answers, setAnswers] = useState<Answers>(battery.answers);
  const [page, setPage] = useState(() => firstOpenPage(instruments, battery.answers));
  const [finished, setFinished] = useState(battery.submitted);
  const [busy, setBusy] = useState(false);
  const scroll = useRef<ScrollViewInstance>(null);
  const instrument = instruments[page];
  const items = useMemo(() => visibleItems(instrument, answers), [instrument, answers]);
  const blank = items.filter((it) => answers[it.id] === undefined);
  const last = page === instruments.length - 1;

  function answer(itemId: string, value: Value) {
    setAnswers((a) => ({ ...a, [itemId]: value }));
    void api.saveBatteryAnswers(battery.id, { [itemId]: value });
  }

  async function advance() {
    if (!last) {
      setPage((p) => p + 1);
      scroll.current?.scrollTo({ y: 0, animated: false });
      return;
    }
    setBusy(true);
    await api.submitBattery(battery.id);
    setBusy(false);
    setFinished(true);
  }

  async function skipBlankAndAdvance() {
    const skipped = Object.fromEntries(blank.map((it) => [it.id, null]));
    setAnswers((a) => ({ ...a, ...skipped }));
    await api.saveBatteryAnswers(battery.id, skipped);
    await advance();
  }

  function next() {
    if (!blank.length) return void advance();
    const n = blank.length;
    Alert.alert(`Skip ${n} ${n === 1 ? "question" : "questions"}?`, "Skipping is fine. You left these blank; we'll record them as skipped.", [
      { text: "Go back", style: "cancel" },
      { text: n === 1 ? "Skip it" : "Skip them", onPress: () => void skipBlankAndAdvance() },
    ]);
  }

  if (finished) {
    return <Message title="Thank you" body="Your answers are saved for the study. They don't affect your videos or your grade." eyebrow="For the study" />;
  }

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      <View style={styles.bar}>
        <IconButton icon="close" label="Close, your answers are saved" onPress={close} style={styles.close} color={colors.onSurfaceVariant} size={20} />
        <T variant="codeSm" color={colors.onSurfaceVariant}>
          Page {page + 1} of {instruments.length}
        </T>
      </View>
      {instruments.length > 1 ? (
        <View style={styles.pages} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          {instruments.map((ins, i) => (
            <View key={ins.id} style={[styles.pageSeg, { backgroundColor: i <= page ? colors.primary : colors.surfaceContainerHighest }]} />
          ))}
        </View>
      ) : null}

      <ScrollView ref={scroll} contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]} keyboardShouldPersistTaps="handled">
        <T variant="codeSm" color={colors.primary} style={styles.eyebrow}>
          For the study · {battery.title}
        </T>
        <T variant="titleMobile" accessibilityRole="header">
          {instrument.title}
        </T>
        <T variant="body" color={colors.onSurfaceVariant} style={{ marginTop: 6 }}>
          {instrument.intro} Not graded. You can skip any question.
        </T>

        <View style={styles.questions}>
          {items.map((it, i) => (
            <Question key={it.id} n={i + 1} item={it} value={answers[it.id]} onAnswer={(v) => answer(it.id, v)} />
          ))}
        </View>

        <Button label={last ? "Finish" : "Next"} trailingIcon={last ? undefined : "arrow-forward"} disabled={busy} onPress={next} style={{ marginTop: 32 }} />
      </ScrollView>
    </View>
  );
}

function Question({ n, item, value, onAnswer }: { n: number; item: InstrumentItem; value: Value | undefined; onAnswer: (v: Value) => void }) {
  const labelId = `q-${item.id}`;
  return (
    <View style={{ gap: 10 }}>
      <T variant="bodySemibold" nativeID={labelId} accessibilityLabel={`Question ${n}: ${item.text}`}>
        {item.text}
      </T>
      <Answer format={item.response} labelId={labelId} value={value} onAnswer={onAnswer} />
      {value === null ? (
        <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 12 }}>
          Skipped. Answer it any time before you finish.
        </T>
      ) : null}
    </View>
  );
}

function Answer({ format, labelId, value, onAnswer }: { format: ResponseFormat; labelId: string; value: Value | undefined; onAnswer: (v: Value) => void }) {
  if (format.kind === "choice") {
    return (
      <View style={styles.pills} accessibilityRole="radiogroup" accessibilityLabelledBy={labelId}>
        {format.options.map((o) => {
          const on = value === o.value;
          const muted = o.value === "prefer_not";
          return (
            <Pressable
              key={o.value}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
              onPress={() => onAnswer(o.value)}
              style={[styles.pill, muted && styles.pillMuted, on && styles.on]}
            >
              <T variant="caption" color={muted && !on ? colors.onSurfaceVariant : colors.onSurface} style={{ fontFamily: fonts.semibold, fontSize: 14 }}>
                {o.label}
              </T>
            </Pressable>
          );
        })}
      </View>
    );
  }
  if (format.kind === "text") return <TextAnswer labelId={labelId} placeholder={format.placeholder} value={typeof value === "string" ? value : ""} onAnswer={onAnswer} />;
  if (format.max - format.min > 10) return <SliderAnswer format={format} labelId={labelId} value={typeof value === "number" ? value : null} onAnswer={onAnswer} />;
  const points = Array.from({ length: (format.max - format.min) / format.step + 1 }, (_, i) => format.min + i * format.step);
  return (
    <View>
      <View style={styles.scale} accessibilityRole="radiogroup" accessibilityLabelledBy={labelId}>
        {points.map((p, i) => (
          <Pressable
            key={p}
            accessibilityRole="radio"
            accessibilityState={{ selected: value === p }}
            accessibilityLabel={`${p}${i === 0 ? `, ${format.anchors[0]}` : i === points.length - 1 ? `, ${format.anchors[1]}` : ""}`}
            onPress={() => onAnswer(p)}
            style={[styles.point, value === p && styles.on]}
          >
            <T variant="bodySemibold">{p}</T>
          </Pressable>
        ))}
      </View>
      <Anchors format={format} />
    </View>
  );
}

function Anchors({ format, middle }: { format: Extract<ResponseFormat, { kind: "scale" }>; middle?: string }) {
  return (
    <View style={styles.anchors} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 12, flex: 1 }}>
        {format.anchors[0]}
      </T>
      {middle ? (
        <T variant="caption" style={{ fontSize: 12, fontFamily: fonts.bold }}>
          {middle}
        </T>
      ) : null}
      <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 12, flex: 1, textAlign: "right" }}>
        {format.anchors[1]}
      </T>
    </View>
  );
}

/** Saved when the field loses focus, so typing doesn't write on every key. */
function TextAnswer({ labelId, placeholder, value, onAnswer }: { labelId: string; placeholder?: string; value: string; onAnswer: (v: Value) => void }) {
  const [text, setText] = useState(value);
  return (
    <TextInput
      accessibilityLabelledBy={labelId}
      value={text}
      placeholder={placeholder}
      placeholderTextColor={colors.outline}
      onChangeText={setText}
      onBlur={() => text.trim() !== value && onAnswer(text.trim() || null)}
      returnKeyType="done"
      style={styles.input}
    />
  );
}

/**
 * The TLX's 0-100 scale in steps of 5. It starts with no answer and no thumb, so nothing is preselected; the first
 * touch sets it, and dragging adjusts it.
 */
function SliderAnswer({ format, labelId, value, onAnswer }: { format: Extract<ResponseFormat, { kind: "scale" }>; labelId: string; value: number | null; onAnswer: (v: Value) => void }) {
  const [width, setWidth] = useState(1);
  const [drag, setDrag] = useState<number | null>(null);
  const span = format.max - format.min;
  const at = (x: number) => {
    const raw = format.min + Math.min(1, Math.max(0, x / width)) * span;
    return Math.round(raw / format.step) * format.step;
  };
  const shown = drag ?? value;
  const pct = shown === null ? null : ((shown - format.min) / span) * 100;
  const step = (dir: 1 | -1) => onAnswer(Math.min(format.max, Math.max(format.min, (value ?? (format.min + format.max) / 2) + dir * format.step)));

  return (
    <View>
      <View
        onStartShouldSetResponder={() => true}
        onMoveShouldSetResponder={() => true}
        onResponderTerminationRequest={() => false}
        onResponderGrant={(e) => setDrag(at(e.nativeEvent.locationX))}
        onResponderMove={(e) => setDrag(at(e.nativeEvent.locationX))}
        onResponderRelease={() => {
          if (drag !== null) onAnswer(drag);
          setDrag(null);
        }}
        onResponderTerminate={() => setDrag(null)}
        onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
        style={styles.sliderHit}
        accessible
        accessibilityRole="adjustable"
        accessibilityLabelledBy={labelId}
        accessibilityValue={{ text: value === null ? "Not answered" : `${value} of ${format.max}` }}
        accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
        onAccessibilityAction={(e) => step(e.nativeEvent.actionName === "increment" ? 1 : -1)}
      >
        <View style={styles.sliderTrack} pointerEvents="none">
          {pct !== null ? <View style={[styles.sliderFill, { width: `${pct}%` }]} /> : null}
          {pct !== null ? <View style={[styles.thumb, { left: `${pct}%` }]} /> : null}
        </View>
      </View>
      <Anchors format={format} middle={shown === null ? "Tap the line" : String(shown)} />
    </View>
  );
}

function Message({ title, body, eyebrow }: { title: string; body: string; eyebrow?: string }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.screen, styles.message, { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 16 }]}>
      <View style={{ gap: 8 }}>
        {eyebrow ? (
          <T variant="codeSm" color={colors.primary} style={styles.eyebrow}>
            {eyebrow}
          </T>
        ) : null}
        <T variant="title" accessibilityRole="header">
          {title}
        </T>
        <T variant="body" color={colors.onSurfaceVariant}>
          {body}
        </T>
      </View>
      <Button label="Continue" onPress={close} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  message: { paddingHorizontal: 20, justifyContent: "space-between" },
  bar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 12, height: 56 },
  close: { backgroundColor: colors.surfaceContainer, borderRadius: radius.full, minWidth: 40, minHeight: 40 },
  pages: { flexDirection: "row", gap: 4, paddingHorizontal: 20, marginBottom: 8 },
  pageSeg: { flex: 1, height: 4, borderRadius: 2 },
  content: { paddingHorizontal: 20, paddingTop: 12 },
  eyebrow: { fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1, fontSize: 11, marginBottom: 6 },
  questions: { marginTop: 24, gap: 28 },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  pill: {
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 16,
    borderRadius: radius.full,
    borderWidth: 1.5,
    borderColor: colors.outlineVariant,
    backgroundColor: colors.surfaceContainerLowest,
  },
  pillMuted: { borderStyle: "dashed" },
  on: { borderColor: colors.primary, backgroundColor: colors.primaryTint },
  scale: { flexDirection: "row", gap: 6 },
  point: {
    flex: 1,
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderColor: colors.outlineVariant,
    backgroundColor: colors.surfaceContainerLowest,
  },
  anchors: { flexDirection: "row", justifyContent: "space-between", gap: 12, marginTop: 6 },
  input: {
    ...type.body,
    minHeight: 48,
    paddingHorizontal: 16,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderColor: colors.outlineVariant,
    backgroundColor: colors.surfaceContainerLowest,
    color: colors.onSurface,
  },
  sliderHit: { height: 44, justifyContent: "center" },
  sliderTrack: { height: 8, borderRadius: 4, backgroundColor: colors.surfaceContainerHighest },
  sliderFill: { height: 8, borderRadius: 4, backgroundColor: colors.primary },
  thumb: { position: "absolute", top: -8, width: 24, height: 24, marginLeft: -12, borderRadius: 12, backgroundColor: colors.primary, borderWidth: 3, borderColor: "#fff", ...shadow.card },
});
