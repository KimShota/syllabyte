import { useState, type ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@syllabyte/core/api/client";
import { ApiError } from "@syllabyte/core/api/remote";
import type { ProblemReportInput } from "@syllabyte/core/api/types";
import { REPORT_CATEGORIES, REPORT_NOTE_MAX, REPORT_TARGETS, reportNeedsNote } from "@syllabyte/core/content/reports";
import type { ProblemCategory, ReportTarget } from "@syllabyte/core/types";
import { Button } from "@/components/Button";
import { IconButton } from "@/components/Header";
import { T } from "@/components/T";
import { formatClock, parseClock, stemPreview } from "@/data/report";
import { useQuery } from "@/state/app";
import { colors, fonts, radius, type } from "@/theme/tokens";

/** How many videos or questions the pickers show before "Show all". */
const FIRST_SHOWN = 6;

function close() {
  if (router.canGoBack()) router.back();
  else router.replace("/");
}

/**
 * Report a problem (settings → Help). The consent text promises "if something in a video seems wrong ... you can
 * report the error in the app"; a quiz question or the app itself can be reported the same way. Opened with
 * `target`, `videoId`, `itemId` or `t`, the form starts filled in (a shortcut from a video or question can use them).
 */
export default function Report() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ target?: string; videoId?: string; itemId?: string; t?: string }>();
  const targets = useQuery(() => api.getReportTargets(), []);
  const [target, setTarget] = useState<ReportTarget | null>(
    REPORT_TARGETS.some((t) => t.id === params.target) ? (params.target as ReportTarget) : params.videoId ? "video" : params.itemId ? "question" : null,
  );
  const [videoId, setVideoId] = useState<string | null>(params.videoId ?? null);
  const [itemId, setItemId] = useState<string | null>(params.itemId ?? null);
  const [at, setAt] = useState(params.t && Number.isFinite(Number(params.t)) ? formatClock(Number(params.t)) : "");
  const [category, setCategory] = useState<ProblemCategory | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const time = parseClock(at);
  const needsNote = !!target && !!category && reportNeedsNote(target, category);
  const picked = target === "video" ? !!videoId : target === "question" ? !!itemId : target === "app";
  const ready = picked && !!category && (!needsNote || note.trim().length > 0) && (target !== "video" || time !== undefined);

  function choose(next: ReportTarget) {
    if (next === target) return;
    setTarget(next);
    setCategory(null);
    setError(null);
  }

  async function send() {
    if (!ready || !target || !category) return;
    const text = note.trim();
    const report: ProblemReportInput =
      target === "video"
        ? { target, video_id: videoId!, category: category as Extract<ProblemReportInput, { target: "video" }>["category"], video_t: time ?? null, note: text }
        : target === "question"
          ? { target, item_id: itemId!, category: category as Extract<ProblemReportInput, { target: "question" }>["category"], note: text }
          : { target, category: category as Extract<ProblemReportInput, { target: "app" }>["category"], note: text, screen: "settings" };
    setBusy(true);
    setError(null);
    try {
      await api.reportProblem(report);
      setSent(true);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 0
          ? "You seem to be offline. Your report wasn't sent; try again when you're connected."
          : "Your report couldn't be sent. Try again in a moment.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <View style={[styles.screen, styles.message, { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 16 }]}>
        <View style={{ gap: 8 }}>
          <T variant="codeSm" color={colors.primary} style={styles.eyebrow}>
            Report sent
          </T>
          <T variant="title" accessibilityRole="header">
            Thanks for telling us
          </T>
          <T variant="body" color={colors.onSurfaceVariant}>
            The research team will look at it. Until then, if something in a video or question seems wrong, rely on your course materials and your instructor.
          </T>
        </View>
        <Button label="Done" onPress={close} />
      </View>
    );
  }

  return (
    <View style={[styles.screen, { paddingTop: insets.top }]}>
      <View style={styles.bar}>
        <IconButton icon="close" label="Close without sending" onPress={close} style={styles.close} color={colors.onSurfaceVariant} size={20} />
      </View>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]} keyboardShouldPersistTaps="handled">
        <T variant="codeSm" color={colors.primary} style={styles.eyebrow}>
          Help
        </T>
        <T variant="titleMobile" accessibilityRole="header">
          Report a problem
        </T>
        <T variant="body" color={colors.onSurfaceVariant} style={{ marginTop: 6 }}>
          Videos and questions are made by AI from your slides, so they can contain mistakes. Tell us what you found; your report goes to the research team under your study code, not your name.
        </T>

        <Section title="What is it about?">
          <View accessibilityRole="radiogroup" style={styles.cards}>
            {REPORT_TARGETS.map((t) => (
              <Choice key={t.id} on={target === t.id} onPress={() => choose(t.id)} label={t.label} hint={t.hint} />
            ))}
          </View>
        </Section>

        {target === "video" ? (
          <Section title="Which video?">
            <Picker
              loading={!targets}
              empty="There are no videos in your course yet."
              rows={(targets?.videos ?? []).map((v) => ({
                id: v.video_id,
                label: v.title,
                hint: `Lecture ${v.lecture_n}${v.last_seen_at ? " · Watched recently" : ""}`,
              }))}
              selected={videoId}
              onSelect={setVideoId}
              noun="videos"
            />
            <T variant="bodySemibold" style={{ marginTop: 16 }} nativeID="report-at">
              Roughly when in the video? <T variant="body" color={colors.onSurfaceVariant}>(optional, like 1:05)</T>
            </T>
            <TextInput
              accessibilityLabelledBy="report-at"
              accessibilityLabel="Roughly when in the video, minutes and seconds, optional"
              value={at}
              onChangeText={setAt}
              placeholder="m:ss"
              placeholderTextColor={colors.outline}
              keyboardType="numbers-and-punctuation"
              returnKeyType="done"
              maxLength={7}
              style={[styles.input, styles.time, time === undefined && styles.invalid]}
            />
            {time === undefined ? (
              <T variant="caption" color={colors.error} style={{ marginTop: 4 }}>
                Write the time as minutes:seconds, like 1:05, or leave it empty.
              </T>
            ) : null}
          </Section>
        ) : null}

        {target === "question" ? (
          <Section title="Which question?">
            <Picker
              loading={!targets}
              empty="You haven't answered any questions yet. Choose “Something else” and describe it instead."
              rows={(targets?.questions ?? []).map((q) => ({ id: q.item_id, label: stemPreview(q.stem), lines: 3 }))}
              selected={itemId}
              onSelect={setItemId}
              noun="questions"
            />
          </Section>
        ) : null}

        {target ? (
          <Section title="What's wrong?">
            <View accessibilityRole="radiogroup" style={styles.cards}>
              {REPORT_CATEGORIES[target].map((c) => (
                <Choice key={c.id} on={category === c.id} onPress={() => setCategory(c.id)} label={c.label} />
              ))}
            </View>
          </Section>
        ) : null}

        {target && category ? (
          <Section title={needsNote ? "What happened?" : "Anything to add?"} subtitle={needsNote ? undefined : "(optional)"}>
            <TextInput
              accessibilityLabel={needsNote ? "What happened" : "Anything to add, optional"}
              value={note}
              onChangeText={setNote}
              placeholder={target === "app" ? "What you were doing, and what went wrong" : "For example, what the slide says instead"}
              placeholderTextColor={colors.outline}
              multiline
              maxLength={REPORT_NOTE_MAX}
              textAlignVertical="top"
              style={[styles.input, styles.note]}
            />
          </Section>
        ) : null}

        {error ? (
          <T variant="body" color={colors.error} style={{ marginTop: 20 }} accessibilityLiveRegion="polite">
            {error}
          </T>
        ) : null}
        <Button label={busy ? "Sending…" : "Send report"} icon="flag" disabled={!ready || busy} onPress={() => void send()} style={{ marginTop: 28 }} />
      </ScrollView>
    </View>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <View style={styles.section}>
      <T variant="bodySemibold" accessibilityRole="header">
        {title} {subtitle ? <T variant="body" color={colors.onSurfaceVariant}>{subtitle}</T> : null}
      </T>
      {children}
    </View>
  );
}

function Choice({ on, onPress, label, hint, lines }: { on: boolean; onPress: () => void; label: string; hint?: string; lines?: number }) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected: on }}
      accessibilityLabel={hint ? `${label}. ${hint}` : label}
      onPress={onPress}
      style={({ pressed }) => [styles.card, on && styles.on, pressed && !on && { backgroundColor: colors.surfaceContainerLow }]}
    >
      <T variant="body" numberOfLines={lines} style={{ fontFamily: on ? fonts.semibold : fonts.regular }}>
        {label}
      </T>
      {hint ? (
        <T variant="caption" color={colors.onSurfaceVariant}>
          {hint}
        </T>
      ) : null}
    </Pressable>
  );
}

function Picker({
  loading,
  empty,
  rows,
  selected,
  onSelect,
  noun,
}: {
  loading: boolean;
  empty: string;
  rows: { id: string; label: string; hint?: string; lines?: number }[];
  selected: string | null;
  onSelect: (id: string) => void;
  noun: string;
}) {
  const [all, setAll] = useState(false);
  if (loading) {
    return (
      <T variant="body" color={colors.onSurfaceVariant}>
        Loading…
      </T>
    );
  }
  if (!rows.length) {
    return (
      <T variant="body" color={colors.onSurfaceVariant}>
        {empty}
      </T>
    );
  }
  // the chosen one stays visible even when it is past the first few
  const shown = all ? rows : rows.filter((r, i) => i < FIRST_SHOWN || r.id === selected);
  return (
    <View accessibilityRole="radiogroup" style={styles.cards}>
      {shown.map((r) => (
        <Choice key={r.id} on={selected === r.id} onPress={() => onSelect(r.id)} label={r.label} hint={r.hint} lines={r.lines ?? 2} />
      ))}
      {!all && rows.length > shown.length ? (
        <Pressable accessibilityRole="button" onPress={() => setAll(true)} style={styles.more} hitSlop={6}>
          <T variant="bodySemibold" color={colors.primary}>
            Show all {rows.length} {noun}
          </T>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  message: { paddingHorizontal: 20, justifyContent: "space-between" },
  bar: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, height: 56 },
  close: { backgroundColor: colors.surfaceContainer, borderRadius: radius.full, minWidth: 40, minHeight: 40 },
  content: { paddingHorizontal: 20, paddingTop: 12 },
  eyebrow: { fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1, fontSize: 11, marginBottom: 6 },
  section: { marginTop: 28, gap: 10 },
  cards: { gap: 8 },
  card: {
    minHeight: 48,
    justifyContent: "center",
    gap: 2,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderColor: colors.outlineVariant,
    backgroundColor: colors.surfaceContainerLowest,
  },
  on: { borderColor: colors.primary, backgroundColor: colors.primaryTint },
  more: { minHeight: 44, justifyContent: "center", alignSelf: "flex-start" },
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
  time: { width: 120, marginTop: 8 },
  invalid: { borderColor: colors.error },
  note: { minHeight: 120, paddingTop: 12 },
});
