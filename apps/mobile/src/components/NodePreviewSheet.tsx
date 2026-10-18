import { StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { Button } from "./Button";
import { IconButton } from "./Header";
import { Sheet, SheetHandle } from "./Sheet";
import { T } from "./T";
import { precheckHref } from "./TaskCards";
import { kuMinutes } from "@/data/selectors";
import type { Ku, KuStatus } from "@/data/types";
import type { PrecheckView } from "@syllabyte/core/types";
import { toggleNotify, usePrefs } from "@/state/app";
import { colors, fonts, radius } from "@/theme/tokens";

function slideSpan(ku: Ku) {
  const [a, b] = ku.slides;
  return a === b ? `slide ${a}` : `slides ${a}–${b}`;
}

/** Tapping a node on the lecture roadmap: what it is, and watch / review / get notified. */
export function NodePreviewSheet({
  ku,
  status,
  check,
  onClose,
}: {
  ku: Ku | null;
  status: KuStatus | null;
  /** the check due before the upcoming lecture's videos: it locks that lecture's videos until it is done */
  check: PrecheckView | null;
  onClose: () => void;
}) {
  const prefs = usePrefs();
  const visible = !!ku && !!status;

  const locked = !!check && !!ku && ku.lectureN === check.lecture_n && status !== "drafting";

  const play = () => {
    if (!ku) return;
    onClose();
    router.push(locked ? precheckHref(check) : { pathname: "/player/[kuId]", params: { kuId: ku.id } });
  };

  let badge: { text: string; bg: string; fg: string } = { text: "", bg: colors.primaryFixed, fg: colors.onPrimaryFixed };
  let description = "";
  let action = null;
  if (ku && status) {
    switch (status) {
      case "watched":
        badge = { text: "Completed · Review", bg: colors.secondaryContainer, fg: colors.onSecondaryFixedVariant };
        description = `You've watched this one. Watch it again, or go back to ${slideSpan(ku)} of the lecture deck.`;
        action = <Button label="Review Concept" icon="replay" kind="success" onPress={play} style={styles.action} />;
        break;
      case "drafting": {
        const on = prefs.notifyKuIds.includes(ku.id);
        badge = { text: "Being made from slides", bg: colors.surfaceContainerHigh, fg: colors.onSurfaceVariant };
        description = `SyllaByte is turning ${slideSpan(ku)} into a short video. It will appear here when it's ready.`;
        action = (
          <Button
            label={on ? "We'll Notify You" : "Notify When Ready"}
            icon={on ? "notifications-active" : "notifications-none"}
            kind="tonal"
            onPress={() => toggleNotify(ku.id)}
            style={styles.action}
          />
        );
        break;
      }
      case "next":
      case "available":
        badge = { text: status === "next" ? "Recommended Next" : "Available Now", bg: colors.primaryFixed, fg: colors.onPrimaryFixed };
        description = `${ku.title}. A ${kuMinutes(ku)}-minute video from ${slideSpan(ku)}, with captions and a transcript.`;
        action = <Button label={`Watch Video (${kuMinutes(ku)} min)`} icon="play-arrow" onPress={play} style={styles.action} />;
        break;
    }
  }

  if (ku && locked) {
    description = `Lecture ${ku.lectureN}'s videos open after a quick check (${check.total} questions, no grade) that tunes them to what you know now.`;
    action = <Button label="Take the check first" icon="lock" onPress={play} style={styles.action} />;
  }

  return (
    <Sheet visible={visible} onClose={onClose} accessibilityLabel={ku?.shortTitle}>
      {ku ? (
        <View style={styles.body}>
          <SheetHandle />
          <View style={styles.top}>
            <View style={[styles.badge, { backgroundColor: badge.bg }]}>
              <T variant="codeSm" color={badge.fg} style={{ fontFamily: fonts.monoSemibold, textTransform: "uppercase" }}>
                {badge.text}
              </T>
            </View>
            <IconButton icon="close" label="Close" size={20} color={colors.onSurfaceVariant} onPress={onClose} />
          </View>
          <T variant="cardTitle" accessibilityRole="header">
            {ku.shortTitle}
          </T>
          <T variant="body" color={colors.onSurfaceVariant}>
            {description}
          </T>
          <View style={styles.actions}>{action}</View>
        </View>
      ) : null}
    </Sheet>
  );
}

const styles = StyleSheet.create({
  body: { paddingHorizontal: 20, paddingBottom: 16, gap: 10 },
  top: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.sm },
  actions: { flexDirection: "row", marginTop: 8 },
  action: { flex: 1 },
});
