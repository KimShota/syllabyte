import type { ReactNode } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Avatar } from "@/components/Avatar";
import { BackButton, Header } from "@/components/Header";
import { Icon, type IconName } from "@/components/Icon";
import { T } from "@/components/T";
import { api } from "@syllabyte/core/api/client";
import { endFirstModule, simulateNextDay, simulateNextWeek } from "@syllabyte/core/api/demo";
import { REMOTE } from "@/data/backend";
import { COURSE, useCourseVersion } from "@/data/course";
import { SPEEDS, setPrefs, signOut, speedLabel, usePrefs, useQuery } from "@/state/app";
import { useSession } from "@/state/session";
import { pickProfilePhoto, removeProfilePhoto, type PhotoSource } from "@/state/photo";
import { colors, fonts, radius, shadow, space } from "@/theme/tokens";

/** The student the demo shows when there is no backend to sign in to. */
const DEMO_STUDENT = { name: "Alex Rivera" };

export default function Profile() {
  useCourseVersion();
  const insets = useSafeAreaInsets();
  const { speed, photoUri } = usePrefs();
  const captions = useQuery(() => api.getMe())?.settings.captions ?? true;
  const { email } = useSession();
  // with a backend the student is who signed in; without one, the demo student
  const name = REMOTE ? (email ?? "Signed in") : DEMO_STUDENT.name;
  const initials = REMOTE
    ? (email?.[0] ?? "?").toUpperCase()
    : DEMO_STUDENT.name
        .split(" ")
        .map((w) => w[0])
        .join("");

  return (
    <View style={styles.screen}>
      <Header
        left={
          <>
            <BackButton />
            <T variant="bodySemibold" accessibilityRole="header">
              Student Profile
            </T>
          </>
        }
      />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 40 }]}>
        <View style={styles.card}>
          <View style={styles.identity}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={photoUri ? "Change profile photo" : "Add profile photo"}
              onPress={() => editPhoto(!!photoUri)}
              hitSlop={6}
            >
              <Avatar
                size={64}
                backgroundColor={colors.primaryFixed}
                fallback={
                  <T variant="cardTitle" color={colors.primaryDeep} style={{ fontFamily: fonts.bold }}>
                    {initials}
                  </T>
                }
              />
              <View style={styles.photoBadge}>
                <Icon name="photo-camera" size={13} color={colors.onPrimary} />
              </View>
            </Pressable>
            <View style={{ flex: 1, gap: 2 }}>
              <Pressable onLongPress={REMOTE ? undefined : openDemoMenu} delayLongPress={1000} accessibilityRole="text">
                <T variant="cardTitle" numberOfLines={1}>
                  {name}
                </T>
              </Pressable>
              <Pressable accessibilityRole="button" onPress={() => editPhoto(!!photoUri)} hitSlop={8} style={styles.photoLink}>
                <T variant="caption" color={colors.primary} style={{ fontFamily: fonts.semibold }}>
                  {photoUri ? "Change photo" : "Add a photo"}
                </T>
              </Pressable>
            </View>
          </View>

          <View style={styles.list}>
            <Group label="Academic Preferences" />
            <Row icon="closed-caption" label="Captions on by default">
              <Toggle value={captions} label="Captions on by default" onChange={(on) => void api.updateSettings({ captions: on })} />
            </Row>
            <Row icon="speed" label="Playback speed default">
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Playback speed default, ${speed}x. Tap to change`}
                onPress={() => setPrefs({ speed: SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length] })}
                style={styles.speedChip}
              >
                <T variant="codeSm" color={colors.primaryDeep} style={{ fontFamily: fonts.monoSemibold }}>
                  {speedLabel(speed)}
                </T>
              </Pressable>
            </Row>
            <Row
              icon="calendar-month"
              label="Syllabus & lecture schedule"
              onPress={() => router.push({ pathname: "/course/[courseId]", params: { courseId: COURSE.id } })}
            />
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                removeProfilePhoto();
                signOut();
                if (router.canDismiss()) router.dismissAll();
                router.replace(REMOTE ? "/signin" : "/welcome");
              }}
              style={({ pressed }) => [styles.signOut, pressed && { backgroundColor: colors.surfaceContainerHighest }]}
            >
              <Icon name="logout" size={18} color={colors.onSurfaceVariant} />
              <T variant="bodySemibold" color={colors.onSurfaceVariant}>
                Sign out
              </T>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

async function takeOrChoose(source: PhotoSource) {
  const result = await pickProfilePhoto(source);
  if (result === "denied") {
    Alert.alert("Camera is off", "Allow camera access for SyllaByte in Settings to take a photo, or choose one from your library.");
  } else if (result === "unavailable") {
    Alert.alert(source === "camera" ? "No camera available" : "Couldn't open your photos", "Try the other option.");
  }
}

/** Profile photo: take one, choose one, or (when there is one) remove it. */
function editPhoto(hasPhoto: boolean) {
  Alert.alert("Profile photo", undefined, [
    { text: "Take photo", onPress: () => void takeOrChoose("camera") },
    { text: "Choose from library", onPress: () => void takeOrChoose("library") },
    ...(hasPhoto ? [{ text: "Remove photo", style: "destructive" as const, onPress: removeProfilePhoto }] : []),
    { text: "Cancel", style: "cancel" as const },
  ]);
}

/**
 * Facilitator controls (like apps/web's demo menu), for walking a study session through time: hidden behind a
 * one-second press on the student's name.
 */
function openDemoMenu() {
  Alert.alert("Demo controls", "For facilitators. These move the app's clock.", [
    { text: "Simulate next day", onPress: simulateNextDay },
    { text: "Simulate next week (the next lecture's check)", onPress: simulateNextWeek },
    { text: "End module 1 (its questionnaire)", onPress: endFirstModule },
    { text: "Cancel", style: "cancel" },
  ]);
}

function Group({ label }: { label: string }) {
  return (
    <T variant="codeSm" color={colors.onSurfaceVariant} style={styles.group}>
      {label}
    </T>
  );
}

function Row({ icon, label, children, onPress, chevron }: { icon: IconName; label: string; children?: ReactNode; onPress?: () => void; chevron?: boolean }) {
  const body = (
    <>
      <View style={styles.rowLeft}>
        <View style={styles.rowIcon}>
          <Icon name={icon} size={19} color={colors.onSurfaceVariant} />
        </View>
        <T variant="body">{label}</T>
      </View>
      {children}
      {chevron ? <Icon name="chevron-right" size={18} color={colors.outline} /> : null}
    </>
  );
  if (!onPress) return <View style={styles.row}>{body}</View>;
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.surfaceContainerLow }]}>
      {body}
    </Pressable>
  );
}

function Toggle({ value, onChange, label }: { value: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityState={{ checked: value }}
      onPress={() => onChange(!value)}
      hitSlop={8}
      style={[styles.toggle, { backgroundColor: value ? colors.primaryDeep : colors.surfaceVariant }]}
    >
      <View style={[styles.thumb, { transform: [{ translateX: value ? 20 : 0 }] }]} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: space.gutter, paddingTop: 8 },
  card: { backgroundColor: colors.surfaceContainerLowest, borderRadius: radius.card, overflow: "hidden", ...shadow.card },
  identity: { flexDirection: "row", alignItems: "center", gap: 12, padding: 16, backgroundColor: colors.surfaceContainerLow },
  photoBadge: {
    position: "absolute",
    right: -2,
    bottom: -2,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.primary,
    borderWidth: 2,
    borderColor: colors.surfaceContainerLow,
    alignItems: "center",
    justifyContent: "center",
  },
  photoLink: { alignSelf: "flex-start", minHeight: 24, justifyContent: "center" },
  list: { padding: 16, gap: 4 },
  group: { textTransform: "uppercase", letterSpacing: 1.6, paddingHorizontal: 8, paddingTop: 10, paddingBottom: 4 },
  row: { minHeight: 48, paddingHorizontal: 12, borderRadius: radius.lg, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  rowLeft: { flexDirection: "row", alignItems: "center", gap: 12, flex: 1 },
  rowIcon: { width: 32, height: 32, borderRadius: radius.md, backgroundColor: colors.surfaceContainer, alignItems: "center", justifyContent: "center" },
  speedChip: { minWidth: 48, height: 32, paddingHorizontal: 12, borderRadius: radius.full, backgroundColor: colors.surfaceContainer, alignItems: "center", justifyContent: "center" },
  toggle: { width: 48, height: 28, borderRadius: 14, padding: 4, justifyContent: "center" },
  thumb: { width: 20, height: 20, borderRadius: 10, backgroundColor: colors.surfaceContainerLowest, ...shadow.card },
  signOut: {
    marginTop: 12,
    minHeight: 48,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceContainer,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
});
