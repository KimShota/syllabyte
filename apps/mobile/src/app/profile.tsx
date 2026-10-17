import type { ReactNode } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { BackButton, Header } from "@/components/Header";
import { Icon, type IconName } from "@/components/Icon";
import { T } from "@/components/T";
import { api } from "@syllabyte/core/api/client";
import { COURSE } from "@/data/course";
import { SPEEDS, setPrefs, signOut, speedLabel, usePrefs, useQuery } from "@/state/app";
import { colors, fonts, radius, shadow, space } from "@/theme/tokens";

/** Mock student until sign-in exists (Phase 1). */
const STUDENT = { name: "Alex Rivera" };

export default function Profile() {
  const insets = useSafeAreaInsets();
  const { speed } = usePrefs();
  const captions = useQuery(() => api.getMe())?.settings.captions ?? true;
  const initials = STUDENT.name
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
            <View style={styles.avatar}>
              <T variant="bodySemibold" color={colors.primaryDeep} style={{ fontFamily: fonts.bold }}>
                {initials}
              </T>
            </View>
            <T variant="cardTitle">{STUDENT.name}</T>
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
            <Group label="Methodology & Privacy" />
            <Row
              icon="shield"
              label="Consent and data"
              chevron
              onPress={() => Alert.alert("Consent and data", "The consent text and data controls move over from the web app in a later step.")}
            />
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                signOut();
                if (router.canDismiss()) router.dismissAll();
                router.replace("/welcome");
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
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.primaryFixed, alignItems: "center", justifyContent: "center" },
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
