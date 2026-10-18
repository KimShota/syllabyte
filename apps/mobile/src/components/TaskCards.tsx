import { useEffect } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { api } from "@syllabyte/core/api/client";
import type { StudyTaskView } from "@syllabyte/core/api/types";
import { track } from "@syllabyte/core/events";
import type { PrecheckView, SittingView } from "@syllabyte/core/types";
import { Icon, type IconName } from "./Icon";
import { T } from "./T";
import { useQuery } from "@/state/app";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

/** What's waiting for the student, above the course list on Home: the baseline, a lecture check, questionnaires. */
export function TaskCards({ onboarded }: { onboarded: boolean }) {
  const baseline = useQuery(() => api.getSitting("week0"));
  const playlist = useQuery(() => api.getPlaylist());
  const tasks = useQuery(() => api.getStudyTasks());
  const shownIds = (tasks ?? []).map((t) => t.battery_id).join(",");
  useEffect(() => {
    for (const id of shownIds ? shownIds.split(",") : []) track("study_shown", { type: "battery", id });
  }, [shownIds]);

  const cards = [
    !onboarded && baseline ? <BaselineCard key="baseline" sitting={baseline} /> : null,
    playlist?.precheck ? <PrecheckCard key="precheck" check={playlist.precheck} /> : null,
    ...(tasks ?? []).map((t) => <StudyTaskCard key={t.battery_id} task={t} />),
  ].filter(Boolean);
  if (!cards.length) return null;
  return <View style={styles.list}>{cards}</View>;
}

/** The baseline is still open (the student left the first run before it): a way back into it. */
function BaselineCard({ sitting }: { sitting: SittingView }) {
  const started = sitting.answered > 0;
  return (
    <TaskCard
      icon="psychology-alt"
      eyebrow="Quick check"
      title={started ? "Finish your quick check" : "Take the quick check"}
      body={`${started ? `${sitting.answered} of ${sitting.total} answered.` : `${sitting.total} questions, no grade.`} It tunes your videos to what you know.`}
      action={started ? "Continue" : "Start"}
      onPress={() => router.push(started ? "/quiz/question" : "/quiz")}
    />
  );
}

/** The check before a lecture's videos (plan D8): short, adaptive, not graded, and it can wait. */
export function PrecheckCard({ check }: { check: PrecheckView }) {
  const started = check.answered > 0;
  const minutes = Math.max(1, Math.round(check.total / 3));
  return (
    <TaskCard
      icon="fact-check"
      tone="secondary"
      eyebrow={`Before Lecture ${check.lecture_n}`}
      title={started ? "Finish the lecture check" : "A quick check before this lecture"}
      body={`${check.total} questions, about ${minutes} ${minutes === 1 ? "minute" : "minutes"}. It tunes “${check.title}” to what you know now. Not graded.`}
      action={started ? "Continue" : "Start"}
      onPress={() =>
        started
          ? router.push({ pathname: "/quiz/question", params: { sitting: check.sitting_id } })
          : router.push({ pathname: "/quiz", params: { sitting: check.sitting_id } })
      }
      onLater={() => void api.skipSitting(check.sitting_id)}
    />
  );
}

/** A questionnaire that is due (plan/study-instruments-plan.md I9). It never blocks learning; "Not now" hides it until the next launch. */
function StudyTaskCard({ task }: { task: StudyTaskView }) {
  return (
    <TaskCard
      icon="assignment"
      eyebrow="For the study"
      title={task.title}
      body={`About ${task.minutes} ${task.minutes === 1 ? "minute" : "minutes"}. Not graded, and you can skip any question.`}
      action={task.started ? "Continue" : "Start"}
      onPress={() => router.push({ pathname: "/study/[id]", params: { id: task.battery_id } })}
      onLater={() => void api.snoozeBattery(task.battery_id)}
    />
  );
}

function TaskCard({
  icon,
  tone = "primary",
  eyebrow,
  title,
  body,
  action,
  onPress,
  onLater,
}: {
  icon: IconName;
  tone?: "primary" | "secondary";
  eyebrow: string;
  title: string;
  body: string;
  action: string;
  onPress: () => void;
  onLater?: () => void;
}) {
  const fg = tone === "secondary" ? colors.secondary : colors.primary;
  return (
    <View style={[styles.card, { borderColor: tone === "secondary" ? "rgba(0,107,93,0.3)" : "rgba(91,63,214,0.3)" }]}>
      <View style={styles.top}>
        <View style={[styles.icon, { backgroundColor: tone === "secondary" ? colors.secondaryContainer : colors.primaryFixed }]}>
          <Icon name={icon} size={22} color={tone === "secondary" ? colors.onSecondaryContainer : colors.primary} />
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <T variant="codeSm" color={fg} style={{ fontFamily: fonts.monoSemibold, textTransform: "uppercase", letterSpacing: 1, fontSize: 11 }}>
            {eyebrow}
          </T>
          <T variant="bodySemibold">{title}</T>
          <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 13, lineHeight: 18 }}>
            {body}
          </T>
        </View>
      </View>
      <View style={styles.actions}>
        {onLater ? (
          <Pressable accessibilityRole="button" accessibilityLabel={`Not now: ${title}`} onPress={onLater} hitSlop={6} style={styles.later}>
            <T variant="caption" color={colors.onSurfaceVariant} style={{ fontFamily: fonts.semibold }}>
              Not now
            </T>
          </Pressable>
        ) : null}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${action}: ${title}`}
          onPress={onPress}
          style={({ pressed }) => [styles.go, { backgroundColor: pressed ? colors.primaryPressed : fg }]}
        >
          <T variant="caption" color={colors.onPrimary} style={{ fontFamily: fonts.semibold }}>
            {action}
          </T>
          <Icon name="arrow-forward" size={16} color={colors.onPrimary} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  list: { marginTop: 20, gap: 12 },
  card: {
    gap: 12,
    padding: 16,
    borderRadius: radius.xl,
    backgroundColor: colors.surfaceContainerLowest,
    borderWidth: 1,
    ...shadow.card,
  },
  top: { flexDirection: "row", gap: 12 },
  icon: { width: 40, height: 40, borderRadius: radius.lg, alignItems: "center", justifyContent: "center" },
  actions: { flexDirection: "row", justifyContent: "flex-end", alignItems: "center", gap: 16 },
  later: { minHeight: 40, justifyContent: "center", paddingHorizontal: 4 },
  go: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 40, paddingHorizontal: 16, borderRadius: radius.lg },
});
