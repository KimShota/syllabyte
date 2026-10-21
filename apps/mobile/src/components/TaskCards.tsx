import { useEffect } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { router, type Href } from "expo-router";
import { api } from "@syllabyte/core/api/client";
import type { StudyTaskView } from "@syllabyte/core/api/types";
import { track } from "@syllabyte/core/events";
import type { PrecheckView } from "@syllabyte/core/types";
import { Icon, type IconName } from "./Icon";
import { T } from "./T";
import { useQuery } from "@/state/app";
import { colors, fonts, radius, shadow } from "@/theme/tokens";
import { lectureNumber } from "@/data/course";

/** What's waiting for the student, above the course list on Home: questionnaires. (The lecture check isn't here: it is reached from its lecture, see PrecheckCard. The baseline isn't a card either: it can't be put off, see BaselineGate.) */
export function TaskCards() {
  const tasks = useQuery(() => api.getStudyTasks());
  const shownIds = (tasks ?? []).map((t) => t.battery_id).join(",");
  useEffect(() => {
    for (const id of shownIds ? shownIds.split(",") : []) track("study_shown", { type: "battery", id });
  }, [shownIds]);

  const cards = (tasks ?? []).map((t) => <StudyTaskCard key={`battery:${t.battery_id}`} task={t} />);
  if (!cards.length) return null;
  return <View style={styles.list}>{cards}</View>;
}

/** Where a lecture check goes: its intro, or straight to the question it is on once started. */
export function precheckHref(check: PrecheckView): Href {
  return check.answered > 0
    ? { pathname: "/quiz/question", params: { sitting: check.sitting_id } }
    : { pathname: "/quiz", params: { sitting: check.sitting_id } };
}

/**
 * The check before a lecture's videos (plan D8): short, adaptive, not graded. The student must finish it before
 * that lecture's videos open, so there is no way to put it off; the player and the roadmap enforce that.
 */
export function PrecheckCard({ check }: { check: PrecheckView }) {
  const started = check.answered > 0;
  return (
    <TaskCard
      icon="fact-check"
      tone="secondary"
      eyebrow={`Before Lecture ${lectureNumber(check.lecture_n)}`}
      title={started ? "Finish your quick test" : "Take a quick test to get started"}
      body="We'll use your answers to personalize your videos."
      action={started ? "Continue" : "Start"}
      onPress={() => router.push(precheckHref(check))}
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
