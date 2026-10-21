import { useCallback, useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { LectureStateView, UploadOrderEntry, UploadView } from "@syllabyte/core/api/types";
import { Button } from "@/components/Button";
import { BackButton, Header, IconButton } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { Spin } from "@/components/Motion";
import { T } from "@/components/T";
import { refreshCourse, useMyCourse } from "@/state/course";
import { courseCalls } from "@/state/session";
import { pickAndAddSlides } from "@/state/uploads";
import { colors, fonts, radius, shadow, space, type } from "@/theme/tokens";

/** how often to look again while files are being read and placed */
const POLL_MS = 3000;

/** A row of the order: a lecture already in the course (fixed), or a new deck this student places. */
type Key = `lecture:${number}` | `upload:${string}`;

/**
 * Placing slide files (plan/slide-uploads-plan.md V1, V2), the same for one file or a whole course at once. Each file
 * is read on the server for what it teaches (file names don't matter), then the new ones are put in order among the
 * course's lectures. The student who uploads a deck first checks that order and the titles, moves a deck up or down
 * if needed, and confirms; the lectures already in the course stay where they are. Files already in the course, and
 * updated versions of slides already in it, need nothing.
 */
export default function ReviewUploads() {
  const { courseId } = useLocalSearchParams<{ courseId: string }>();
  const insets = useSafeAreaInsets();
  const myCourse = useMyCourse();
  const lectures = myCourse?.status === "ready" ? myCourse.course.lectures : [];
  const [rows, setRows] = useState<UploadView[] | null>(null);
  // null until the student moves something: the suggested order
  const [moved, setOrder] = useState<Key[] | null>(null);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (courseCalls) setRows(await courseCalls.uploads(courseId));
  }, [courseId]);

  useEffect(() => {
    courseCalls?.uploads(courseId).then(setRows, () => {});
  }, [courseId]);
  const working = rows?.some((u) => u.placing) ?? false;
  useEffect(() => {
    if (!working) return;
    const id = setInterval(() => courseCalls?.uploads(courseId).then(setRows, () => {}), POLL_MS);
    return () => clearInterval(id);
  }, [working, courseId]);

  if (!rows) return <View style={styles.screen} />;

  const placeable = rows.filter((u) => u.can_place && !u.placing);
  const byId = new Map(rows.map((u) => [u.id, u]));
  const suggested: Key[] = [
    ...lectures.map((l) => ({ at: l.position, key: `lecture:${l.n}` as Key })),
    ...placeable.map((u) => ({ at: u.suggested_position ?? Infinity, key: `upload:${u.id}` as Key })),
  ]
    .sort((a, b) => a.at - b.at)
    .map((r) => r.key);
  // a moved order is kept while it lists the same rows (new files or a classmate's lecture reset it)
  const order = moved && moved.length === suggested.length && moved.every((k) => suggested.includes(k)) ? moved : suggested;
  const others = rows.filter((u) => !u.can_place || u.placing);
  const toConfirm = rows.filter((u) => u.status === "read");
  const titleOf = (u: UploadView) => titles[u.id] ?? u.title ?? "";
  const blank = placeable.some((u) => !titleOf(u).trim());
  const canConfirm = !busy && !working && toConfirm.length > 0 && !blank;

  const move = (key: Key, by: -1 | 1) => {
    const i = order.indexOf(key);
    const j = i + by;
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[i], next[j]] = [next[j], next[i]];
    setOrder(next);
  };

  async function confirm() {
    if (!courseCalls) return;
    setError(null);
    setBusy(true);
    try {
      const entries: UploadOrderEntry[] = order.map((k) =>
        k.startsWith("lecture:") ? { lecture_n: Number(k.slice(8)) } : { upload_id: k.slice(7), title: titleOf(byId.get(k.slice(7))!).trim() },
      );
      await courseCalls.confirmUploads(courseId, entries);
      await refreshCourse();
      if (router.canGoBack()) router.back();
      else router.replace({ pathname: "/course/[courseId]", params: { courseId } });
    } catch (e) {
      setError(e instanceof Error ? e.message : "The slides could not be placed.");
      setBusy(false);
      setOrder(null);
      await refreshCourse().catch(() => null);
      void load().catch(() => {});
    }
  }

  async function addMore() {
    setError(null);
    try {
      if (await pickAndAddSlides(courseId)) await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The files could not be uploaded.");
    }
  }

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Header
        bordered
        left={<BackButton />}
        center={
          <T variant="cardTitle" accessibilityRole="header">
            Place your slides
          </T>
        }
      />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <T variant="body" color={colors.onSurfaceVariant}>
          {working
            ? "Reading your files to see what each one teaches, then putting them in order. This takes a few seconds each."
            : placeable.length
              ? "This is the order we think your lectures go in. Check the new ones and their titles, move any that are out of place, then confirm."
              : toConfirm.length
                ? "Nothing to place: these slides are already in your course."
                : "Nothing left to place."}
        </T>

        {placeable.length ? (
          <View style={styles.list}>
            {order.map((key, i) => {
              if (key.startsWith("lecture:")) {
                const l = lectures.find((x) => `lecture:${x.n}` === key);
                return l ? <LectureRow key={key} at={i + 1} lecture={l} /> : null;
              }
              const u = byId.get(key.slice(7))!;
              return (
                <NewDeckRow
                  key={key}
                  at={i + 1}
                  u={u}
                  title={titleOf(u)}
                  onTitle={(t) => setTitles({ ...titles, [u.id]: t })}
                  onUp={i > 0 ? () => move(key, -1) : null}
                  onDown={i < order.length - 1 ? () => move(key, 1) : null}
                />
              );
            })}
          </View>
        ) : null}

        {others.length ? (
          <View style={styles.list}>
            {others.map((u) => (
              <OtherRow key={u.id} u={u} lectures={lectures} />
            ))}
          </View>
        ) : null}
        <Button label="Add more files" icon="upload-file" kind="secondary" height={44} onPress={addMore} style={{ marginTop: 12 }} />
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + 12 }]}>
        {error ? (
          <T variant="caption" color={colors.error} style={{ textAlign: "center" }} accessibilityLiveRegion="polite">
            {error}
          </T>
        ) : blank ? (
          <T variant="caption" color={colors.onSurfaceVariant} style={{ textAlign: "center" }}>
            Every lecture needs a title.
          </T>
        ) : null}
        <Button label={busy ? "Placing…" : placeable.length > 1 ? "Confirm all" : "Confirm"} trailingIcon="check" disabled={!canConfirm} onPress={confirm} />
      </View>
    </KeyboardAvoidingView>
  );
}

const Badge = ({ at, muted }: { at: number; muted?: boolean }) => (
  <View style={[styles.badge, muted && { backgroundColor: colors.surfaceContainerHigh }]}>
    <T variant="codeSm" color={muted ? colors.onSurfaceVariant : colors.onPrimary} style={{ fontFamily: fonts.monoSemibold }}>
      {String(at).padStart(2, "0")}
    </T>
  </View>
);

/** A lecture already in the course: it stays where it is. */
function LectureRow({ at, lecture }: { at: number; lecture: LectureStateView }) {
  return (
    <View style={styles.fixed} accessible accessibilityLabel={`Lecture ${at}: ${lecture.title}, already in the course`}>
      <Badge at={at} muted />
      <T variant="body" color={colors.onSurfaceVariant} numberOfLines={1} style={{ flex: 1 }}>
        {lecture.title}
      </T>
      <Icon name="lock-outline" size={16} color={colors.outline} />
    </View>
  );
}

/** A new deck: its title (editable), what it teaches, and arrows to move it. */
function NewDeckRow({
  at,
  u,
  title,
  onTitle,
  onUp,
  onDown,
}: {
  at: number;
  u: UploadView;
  title: string;
  onTitle: (t: string) => void;
  onUp: (() => void) | null;
  onDown: (() => void) | null;
}) {
  const unsure = !u.suggestion_sure;
  const name = title || u.file_name;
  return (
    <View style={[styles.card, unsure && styles.cardFlagged]}>
      <View style={styles.cardHead}>
        <Badge at={at} />
        <TextInput
          value={title}
          onChangeText={onTitle}
          placeholder="Lecture title"
          placeholderTextColor={colors.outline}
          maxLength={120}
          style={styles.input}
          accessibilityLabel={`Lecture ${at} title`}
        />
        <View style={styles.moves}>
          {onUp ? <IconButton icon="keyboard-arrow-up" label={`Move ${name} earlier`} onPress={onUp} color={colors.primary} size={22} /> : <View style={styles.noMove} />}
          {onDown ? <IconButton icon="keyboard-arrow-down" label={`Move ${name} later`} onPress={onDown} color={colors.primary} size={22} /> : <View style={styles.noMove} />}
        </View>
      </View>
      {u.summary ? (
        <T variant="caption" color={colors.onSurfaceVariant} numberOfLines={3} style={{ marginTop: 6 }}>
          {u.summary}
        </T>
      ) : null}
      <View style={styles.meta}>
        <T variant="codeSm" color={colors.onSurfaceVariant} numberOfLines={1} style={{ flex: 1 }}>
          {u.file_name}
          {u.deck ? ` · ${u.deck.page_count} pages` : ""}
        </T>
        {unsure ? (
          <View style={styles.flag}>
            <T variant="codeSm" color={colors.tertiary} style={{ fontFamily: fonts.monoSemibold, fontSize: 10 }}>
              CHECK THE ORDER
            </T>
          </View>
        ) : null}
      </View>
    </View>
  );
}

/** A file that needs no placing: being read, already in the course, an updated version, or one that failed. */
function OtherRow({ u, lectures }: { u: UploadView; lectures: LectureStateView[] }) {
  const i = u.placed_lecture_n === null ? -1 : lectures.findIndex((l) => l.n === u.placed_lecture_n);
  const where = i >= 0 ? `Lecture ${i + 1}: ${lectures[i].title}` : null;
  const failed = u.status === "failed";
  const message = u.placing
    ? u.status === "reading"
      ? "Reading…"
      : "Putting it in order…"
    : failed
      ? (u.error ?? "This file could not be read.")
      : u.outcome === "updated_version"
        ? `These look like the slides for ${where ?? "a lecture"}, which are already in. The lecture keeps its questions and videos; we'll note the new version for the research team.`
        : where
          ? `Already in ${where}. A classmate added these slides.`
          : "Already in your course.";
  return (
    <View style={styles.card}>
      <View style={styles.cardHead}>
        <Icon name={failed ? "error-outline" : "description"} size={20} color={failed ? colors.error : colors.primary} />
        <T variant="bodySemibold" numberOfLines={1} style={{ flex: 1 }}>
          {u.file_name}
        </T>
      </View>
      <View style={styles.status}>
        {u.placing ? (
          <Spin>
            <Icon name="autorenew" size={16} color={colors.primary} />
          </Spin>
        ) : failed ? null : (
          <Icon name="check-circle" size={16} color={colors.secondary} />
        )}
        <T variant="caption" color={failed ? colors.error : colors.onSurfaceVariant} style={{ flex: 1 }}>
          {message}
        </T>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: space.gutter, paddingTop: 16, paddingBottom: 24 },
  list: { marginTop: 16, gap: 8 },
  fixed: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 44, paddingHorizontal: 10, borderRadius: radius.lg, backgroundColor: colors.surfaceContainerLow },
  card: { padding: 12, borderRadius: radius.lg, backgroundColor: colors.surfaceContainerLowest, ...shadow.card },
  cardFlagged: { borderWidth: 1.5, borderColor: colors.tertiaryFixedDim },
  cardHead: { flexDirection: "row", alignItems: "center", gap: 10 },
  input: { ...type.bodySemibold, flex: 1, minHeight: 44, color: colors.onSurface },
  moves: { flexDirection: "row" },
  noMove: { width: 44, height: 44 },
  meta: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 8 },
  flag: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.full, backgroundColor: colors.tertiaryFixed },
  status: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 10 },
  badge: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center", backgroundColor: colors.primary },
  footer: { paddingHorizontal: space.gutter, paddingTop: 12, gap: 8, borderTopWidth: 1, borderTopColor: colors.surfaceContainerHigh, backgroundColor: colors.surface },
});
