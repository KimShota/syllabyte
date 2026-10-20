import { Pressable, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { Button } from "./Button";
import { IconButton } from "./Header";
import { Icon } from "./Icon";
import { ProgressBar } from "./ProgressBar";
import { Sheet } from "./Sheet";
import { T } from "./T";
import { REMOTE } from "@/data/backend";
import { COURSE, OTHER_COURSES, useCourseVersion } from "@/data/course";
import { courseProgress } from "@/data/selectors";
import { useProgress } from "@/state/progress";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter((w) => /^[A-Z]/.test(w))
    .slice(0, 2)
    .map((w) => w[0])
    .join("");
}

/** "My Courses" dropping from the top of the course roadmap: switch course or add one. */
export function CoursesDrawer({ visible, onClose, currentId }: { visible: boolean; onClose: () => void; currentId: string }) {
  useCourseVersion();
  const main = courseProgress(COURSE, useProgress());
  const all = [
    { id: COURSE.id, name: COURSE.name, meta: [COURSE.code, COURSE.term].filter(Boolean).join(" · "), progress: main.fraction, done: false, activeLecture: main.activeLecture?.n ?? null, planned: COURSE.lecturesPlanned },
    ...OTHER_COURSES.filter((c) => !c.analyzing).map((c) => ({
      id: c.id,
      name: c.name,
      meta: c.progress >= 1 ? `${c.code} · Completed • 100%` : `${c.code} · ${c.lecturesDone} of ${c.lecturesPlanned} lectures`,
      progress: c.progress,
      done: c.progress >= 1,
      activeLecture: null as number | null,
      planned: c.lecturesPlanned,
    })),
  ];

  function go(id: string) {
    onClose();
    if (id !== currentId) router.replace({ pathname: "/course/[courseId]", params: { courseId: id } });
  }

  return (
    <Sheet visible={visible} onClose={onClose} edge="top" dismissOnBackdrop={false} accessibilityLabel="My courses">
      <View style={styles.head}>
        <IconButton
          icon="home"
          label="Go to Home"
          color={colors.primary}
          size={18}
          style={styles.roundBtn}
          onPress={() => {
            onClose();
            router.dismissTo("/");
          }}
        />
        {/* the title is the way out: tap "My Courses" again to close the drawer */}
        <Pressable accessibilityRole="button" accessibilityLabel="Close My Courses" onPress={onClose} hitSlop={8} style={styles.headTitle}>
          <Icon name="menu-book" size={20} color={colors.primary} />
          <T variant="cardTitle" style={{ fontFamily: fonts.bold, fontSize: 18 }}>
            My Courses
          </T>
          <Icon name="expand-less" size={20} color={colors.onSurface} />
        </Pressable>
        {/* balances the Home button so the title stays centred */}
        <View style={styles.headSpacer} />
      </View>

      <View style={styles.body}>
        <View style={styles.listHead}>
          <T variant="codeSm" color={colors.onSurfaceVariant} style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1, fontFamily: fonts.monoMedium }}>
            Enrolled Courses ({all.length})
          </T>
          <T variant="codeSm" color={colors.onSurfaceVariant}>
            {COURSE.term}
          </T>
        </View>

        {all.map((c) => {
          const current = c.id === currentId;
          return (
            <Pressable
              key={c.id}
              accessibilityRole="button"
              accessibilityState={{ selected: current }}
              accessibilityLabel={`${c.name}, ${current ? "current course" : c.meta}`}
              onPress={() => go(c.id)}
              style={({ pressed }) => [styles.row, current && styles.rowCurrent, pressed && { backgroundColor: colors.surfaceContainerLow }]}
            >
              <View style={styles.rowTop}>
                <View style={[styles.mono, current && { backgroundColor: colors.primaryDeep }]}>
                  <T variant="codeSm" color={current ? colors.onPrimary : colors.onSurfaceVariant} style={{ fontFamily: fonts.monoSemibold }}>
                    {initials(c.name)}
                  </T>
                </View>
                <View style={{ flex: 1 }}>
                  <T variant="bodySemibold" style={{ fontSize: 14, lineHeight: 18 }}>
                    {c.name}
                  </T>
                  <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 11, lineHeight: 15, marginTop: 2 }}>
                    {c.meta}
                  </T>
                </View>
                {current ? (
                  <View style={styles.active}>
                    <Icon name="check" size={11} color={colors.secondary} />
                    <T variant="codeSm" color={colors.secondary} style={{ fontSize: 10, fontFamily: fonts.monoSemibold }}>
                      Active
                    </T>
                  </View>
                ) : c.done ? (
                  <Icon name="check-circle" size={20} color={colors.secondary} />
                ) : (
                  <Icon name="chevron-right" size={20} color={colors.outlineVariant} />
                )}
              </View>
              {current ? (
                <View style={{ gap: 4, marginTop: 6 }}>
                  <View style={styles.rowProgress}>
                    <T variant="codeSm" color={colors.primary} style={{ fontFamily: fonts.monoMedium }}>
                      {c.activeLecture ? `Lecture ${c.activeLecture} of ${c.planned} in progress` : "All lectures done"}
                    </T>
                    <T variant="codeSm" color={colors.primary} style={{ fontFamily: fonts.monoMedium }}>
                      {Math.round(c.progress * 100)}%
                    </T>
                  </View>
                  <ProgressBar value={c.progress} height={6} />
                </View>
              ) : null}
            </Pressable>
          );
        })}

        {/* one course per student while uploads are real (plan/slide-uploads-plan.md U4) */}
        {REMOTE ? null : (
        <View style={styles.add}>
          <Button
            label="Add New Course"
            icon="add"
            height={44}
            style={{ backgroundColor: colors.primaryDeep }}
            onPress={() => {
              onClose();
              router.dismissTo({ pathname: "/", params: { upload: String(Date.now()) } });
            }}
          />
          <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 11, textAlign: "center" }}>
            Upload syllabus or slides to generate learning roadmaps
          </T>
        </View>
        )}
      </View>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  head: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: colors.surfaceContainerLow,
    borderBottomWidth: 1,
    borderBottomColor: colors.surfaceContainer,
  },
  roundBtn: { width: 36, minWidth: 36, minHeight: 36, borderRadius: 18, backgroundColor: colors.surfaceContainer },
  headTitle: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 36 },
  headSpacer: { width: 36 },
  body: { padding: 16, gap: 8 },
  listHead: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 4, marginBottom: 4 },
  row: { padding: 12, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.surfaceContainer },
  rowCurrent: { backgroundColor: colors.surfaceContainerLow, borderColor: "rgba(67,30,190,0.4)", ...shadow.card },
  rowTop: { flexDirection: "row", alignItems: "center", gap: 10 },
  mono: { width: 32, height: 32, borderRadius: radius.md, backgroundColor: colors.surfaceContainer, alignItems: "center", justifyContent: "center" },
  active: { flexDirection: "row", alignItems: "center", gap: 2, backgroundColor: colors.secondaryContainer, paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.full },
  rowProgress: { flexDirection: "row", justifyContent: "space-between" },
  add: { marginTop: 8, paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.surfaceContainer, gap: 6 },
});
