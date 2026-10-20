import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { LectureStateView, UploadChoice, UploadView } from "@syllabyte/core/api/types";
import { Button } from "@/components/Button";
import { BackButton, Header } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { Spin } from "@/components/Motion";
import { T } from "@/components/T";
import { refreshCourse, useMyCourse } from "@/state/course";
import { courseCalls } from "@/state/session";
import { pickAndAddSlides } from "@/state/uploads";
import { colors, fonts, radius, shadow, space } from "@/theme/tokens";

/** how often to look again while files are being read */
const POLL_MS = 3000;

type Kind = NonNullable<UploadChoice["kind"]>;

/**
 * Placing slide files in lectures (plan/slide-uploads-plan.md U13), the same for one file or a whole course at once.
 * Each file is read on the server first; then it shows the lecture it looks like. A file nobody has placed yet is
 * placed by this student (U11); one a classmate already added is already in its lecture. A lecture that already has
 * slides asks whether the file is an extra part or an updated version (U12). "Confirm all" sends every choice.
 */
export default function ReviewUploads() {
  const { courseId } = useLocalSearchParams<{ courseId: string }>();
  const insets = useSafeAreaInsets();
  const myCourse = useMyCourse();
  const lectures = myCourse?.status === "ready" ? myCourse.course.lectures : [];
  const scheduleFound = myCourse?.status === "ready" ? myCourse.course.schedule_found : true;
  const [rows, setRows] = useState<UploadView[] | null>(null);
  const [lectureOf, setLectureOf] = useState<Record<string, number | undefined>>({});
  const [kindOf, setKindOf] = useState<Record<string, Kind | undefined>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((next: UploadView[]) => {
    setRows(next);
    // the suggestion is the starting choice; the student's own choice stays
    setLectureOf((cur) => {
      const out = { ...cur };
      for (const u of next) if (out[u.id] === undefined && u.suggested_lecture_n !== null) out[u.id] = u.suggested_lecture_n;
      return out;
    });
  }, []);
  const load = useCallback(async () => {
    if (courseCalls) apply(await courseCalls.uploads(courseId));
  }, [courseId, apply]);

  useEffect(() => {
    courseCalls?.uploads(courseId).then(apply, () => {});
  }, [courseId, apply]);
  const reading = rows?.some((u) => u.status === "reading") ?? false;
  useEffect(() => {
    if (!reading) return;
    const id = setInterval(() => courseCalls?.uploads(courseId).then(apply, () => {}), POLL_MS);
    return () => clearInterval(id);
  }, [reading, courseId, apply]);

  if (!rows) return <View style={styles.screen} />;

  // a course without a schedule grows a lecture per file: the next number is on offer
  const options: { n: number; title: string; isNew: boolean }[] = [
    ...lectures.map((l) => ({ n: l.n, title: l.title, isNew: false })),
    ...(scheduleFound ? [] : [{ n: lectures.length + 1, title: "New lecture", isNew: true }]),
  ];
  const hasSlides = (n: number | undefined) => lectures.some((l) => l.n === n && l.decks.length > 0);
  const needsKind = (u: UploadView) => u.can_place && hasSlides(lectureOf[u.id]);
  const unsure = (u: UploadView) => u.status === "read" && u.can_place && (u.suggested_lecture_n === null || !u.suggestion_sure);
  // the ones to check come first (U13)
  const ordered = [...rows].sort((a, b) => Number(unsure(b)) - Number(unsure(a)));
  const toConfirm = rows.filter((u) => u.status === "read");
  const missing = toConfirm.filter((u) => u.can_place && (lectureOf[u.id] === undefined || (needsKind(u) && !kindOf[u.id])));
  const canConfirm = !busy && !reading && toConfirm.length > 0 && missing.length === 0;

  async function confirm() {
    if (!courseCalls) return;
    setError(null);
    setBusy(true);
    try {
      await courseCalls.confirmUploads(
        courseId,
        toConfirm.map((u) => ({
          upload_id: u.id,
          ...(u.can_place ? { lecture_n: lectureOf[u.id] } : {}),
          ...(u.can_place && needsKind(u) ? { kind: kindOf[u.id] } : {}),
        })),
      );
      await refreshCourse();
      if (router.canGoBack()) router.back();
      else router.replace({ pathname: "/course/[courseId]", params: { courseId } });
    } catch (e) {
      setError(e instanceof Error ? e.message : "The slides could not be placed.");
      setBusy(false);
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
    <View style={styles.screen}>
      <Header
        bordered
        left={<BackButton />}
        center={
          <T variant="cardTitle" accessibilityRole="header">
            Place your slides
          </T>
        }
      />
      <ScrollView contentContainerStyle={styles.content}>
        <T variant="body" color={colors.onSurfaceVariant}>
          {reading
            ? "Reading your files. This takes a few seconds each."
            : toConfirm.length
              ? "Check the lecture for each file, then confirm. The ones we weren't sure about are first."
              : "Nothing left to place."}
        </T>

        <View style={styles.list}>
          {ordered.map((u) => (
            <UploadRow
              key={u.id}
              u={u}
              options={options}
              lectures={lectures}
              chosen={lectureOf[u.id]}
              onChoose={(n) => setLectureOf({ ...lectureOf, [u.id]: n })}
              kind={kindOf[u.id]}
              onKind={(k) => setKindOf({ ...kindOf, [u.id]: k })}
              askKind={needsKind(u)}
              flagged={unsure(u)}
            />
          ))}
        </View>
        <Button label="Add more files" icon="upload-file" kind="secondary" height={44} onPress={addMore} style={{ marginTop: 12 }} />
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + 12 }]}>
        {error ? (
          <T variant="caption" color={colors.error} style={{ textAlign: "center" }} accessibilityLiveRegion="polite">
            {error}
          </T>
        ) : missing.length ? (
          <T variant="caption" color={colors.onSurfaceVariant} style={{ textAlign: "center" }}>
            {missing.length === 1 ? "One file still needs an answer." : `${missing.length} files still need an answer.`}
          </T>
        ) : null}
        <Button
          label={busy ? "Placing…" : toConfirm.length > 1 ? "Confirm all" : "Confirm"}
          trailingIcon="check"
          disabled={!canConfirm}
          onPress={confirm}
        />
      </View>
    </View>
  );
}

function UploadRow({
  u,
  options,
  lectures,
  chosen,
  onChoose,
  kind,
  onKind,
  askKind,
  flagged,
}: {
  u: UploadView;
  options: { n: number; title: string; isNew: boolean }[];
  lectures: LectureStateView[];
  chosen: number | undefined;
  onChoose: (n: number) => void;
  kind: Kind | undefined;
  onKind: (k: Kind) => void;
  askKind: boolean;
  flagged: boolean;
}) {
  const placed = u.placed_lecture_n !== null ? lectures.find((l) => l.n === u.placed_lecture_n) : null;
  return (
    <View style={[styles.card, flagged && styles.cardFlagged]}>
      <View style={styles.cardHead}>
        <Icon name={u.status === "failed" ? "error-outline" : "description"} size={20} color={u.status === "failed" ? colors.error : colors.primary} />
        <View style={{ flex: 1 }}>
          <T variant="bodySemibold" numberOfLines={1}>
            {u.file_name}
          </T>
          {u.deck ? (
            <T variant="codeSm" color={colors.onSurfaceVariant} numberOfLines={1}>
              {u.deck.page_count} pages{u.deck.first_title ? ` · ${u.deck.first_title}` : ""}
            </T>
          ) : null}
        </View>
        {flagged ? (
          <View style={styles.flag}>
            <T variant="codeSm" color={colors.tertiary} style={{ fontFamily: fonts.monoSemibold, fontSize: 10 }}>
              CHECK THIS
            </T>
          </View>
        ) : null}
      </View>

      {u.status === "reading" ? (
        <View style={styles.status}>
          <Spin>
            <Icon name="autorenew" size={16} color={colors.primary} />
          </Spin>
          <T variant="caption" color={colors.onSurfaceVariant}>
            Reading…
          </T>
        </View>
      ) : null}

      {u.status === "failed" ? (
        <T variant="caption" color={colors.error} style={{ marginTop: 8 }}>
          {u.error ?? "This file could not be read."}
        </T>
      ) : null}

      {u.status === "read" && !u.can_place ? (
        <View style={styles.status}>
          <Icon name="check-circle" size={16} color={colors.secondary} />
          <T variant="caption" color={colors.onSurfaceVariant} style={{ flex: 1 }}>
            {placed ? `Already in Lecture ${placed.n}: ${placed.title}. A classmate added these slides.` : "Already in your course."}
          </T>
        </View>
      ) : null}

      {u.status === "read" && u.can_place ? (
        <>
          <T variant="caption" color={colors.onSurfaceVariant} style={{ marginTop: 10 }}>
            {u.suggested_lecture_n === null ? "Which lecture is this?" : u.suggestion_sure ? "Lecture" : "Our guess. Is it right?"}
          </T>
          <LecturePicker options={options} chosen={chosen} onChoose={onChoose} />
          {askKind ? (
            <View style={{ marginTop: 10 }}>
              <T variant="caption" color={colors.onSurfaceVariant}>
                Lecture {chosen} already has slides. Is this file…
              </T>
              <View style={styles.kinds}>
                {(
                  [
                    ["extra_part", "An extra part"],
                    ["updated_version", "An updated version"],
                  ] as const
                ).map(([k, label]) => (
                  <Pressable
                    key={k}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: kind === k }}
                    onPress={() => onKind(k)}
                    style={[styles.kind, kind === k && styles.chipOn]}
                  >
                    <T variant="caption" color={kind === k ? colors.onPrimary : colors.onSurface} style={{ fontFamily: fonts.semibold }}>
                      {label}
                    </T>
                  </Pressable>
                ))}
              </View>
              {kind === "updated_version" ? (
                <T variant="caption" color={colors.onSurfaceVariant} style={{ marginTop: 6 }}>
                  The lecture keeps its current videos and questions. We{"'"}ll note the new version for the research team.
                </T>
              ) : null}
            </View>
          ) : null}
        </>
      ) : null}
    </View>
  );
}

/**
 * The chosen lecture as one row, opening the whole list when tapped (a course can have 14 lectures). Open from the
 * start when nothing matched.
 */
function LecturePicker({
  options,
  chosen,
  onChoose,
}: {
  options: { n: number; title: string; isNew: boolean }[];
  chosen: number | undefined;
  onChoose: (n: number) => void;
}) {
  const [open, setOpen] = useState(chosen === undefined);
  const label = (o: { n: number; title: string; isNew: boolean }) => (o.isNew ? `New lecture ${o.n}` : o.title);
  const current = options.find((o) => o.n === chosen);
  if (!open && current) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Lecture ${current.n}: ${label(current)}. Change`}
        onPress={() => setOpen(true)}
        style={({ pressed }) => [styles.choice, pressed && { backgroundColor: colors.surfaceContainer }]}
      >
        <View style={styles.badge}>
          <T variant="codeSm" color={colors.onPrimary} style={{ fontFamily: fonts.monoSemibold }}>
            {String(current.n).padStart(2, "0")}
          </T>
        </View>
        <T variant="bodySemibold" numberOfLines={1} style={{ flex: 1 }}>
          {label(current)}
        </T>
        <T variant="caption" color={colors.primary} style={{ fontFamily: fonts.semibold }}>
          Change
        </T>
        <Icon name="expand-more" size={18} color={colors.primary} />
      </Pressable>
    );
  }
  return (
    <View style={styles.options} accessibilityRole="radiogroup">
      {options.map((o) => {
        const on = chosen === o.n;
        return (
          <Pressable
            key={o.n}
            accessibilityRole="radio"
            accessibilityState={{ selected: on }}
            accessibilityLabel={`Lecture ${o.n}: ${label(o)}`}
            onPress={() => {
              onChoose(o.n);
              setOpen(false);
            }}
            style={({ pressed }) => [styles.option, on && styles.optionOn, pressed && !on && { backgroundColor: colors.surfaceContainer }]}
          >
            <View style={[styles.badge, !on && { backgroundColor: colors.primaryTint }]}>
              <T variant="codeSm" color={on ? colors.onPrimary : colors.primaryDeep} style={{ fontFamily: fonts.monoSemibold }}>
                {o.isNew ? "+" : String(o.n).padStart(2, "0")}
              </T>
            </View>
            <T variant="body" numberOfLines={1} style={{ flex: 1 }}>
              {label(o)}
            </T>
            {on ? <Icon name="check" size={18} color={colors.primary} /> : null}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: space.gutter, paddingTop: 16, paddingBottom: 24 },
  list: { marginTop: 16, gap: 10 },
  card: { padding: 14, borderRadius: radius.lg, backgroundColor: colors.surfaceContainerLowest, ...shadow.card },
  cardFlagged: { borderWidth: 1.5, borderColor: colors.tertiaryFixedDim },
  cardHead: { flexDirection: "row", alignItems: "center", gap: 10 },
  flag: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.full, backgroundColor: colors.tertiaryFixed },
  status: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 10 },
  choice: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 48, marginTop: 8, paddingHorizontal: 10, borderRadius: radius.lg, backgroundColor: colors.surfaceContainerLow },
  options: { marginTop: 8, gap: 4 },
  option: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: 44, paddingHorizontal: 10, borderRadius: radius.lg },
  optionOn: { backgroundColor: colors.primaryTint },
  badge: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center", backgroundColor: colors.primary },
  chipOn: { backgroundColor: colors.primary },
  kinds: { flexDirection: "row", gap: 8, marginTop: 8 },
  kind: { flex: 1, minHeight: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.lg, backgroundColor: colors.surfaceContainer },
  footer: { paddingHorizontal: space.gutter, paddingTop: 12, gap: 8, borderTopWidth: 1, borderTopColor: colors.surfaceContainerHigh, backgroundColor: colors.surface },
});
