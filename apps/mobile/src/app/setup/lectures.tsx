import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/Button";
import { Header, IconButton } from "@/components/Header";
import { Icon } from "@/components/Icon";
import { T } from "@/components/T";
import { refreshCourse, useMyCourse } from "@/state/course";
import { courseCalls } from "@/state/session";
import { finishSetup } from "@/state/uploads";
import { colors, fonts, radius, shadow, space, type } from "@/theme/tokens";

interface Row {
  key: string;
  title: string;
  week: number | null;
}

let nextKey = 0;
const row = (title: string, week: number | null): Row => ({ key: `r${nextKey++}`, title, week });

/**
 * The lecture list read from the syllabus, for the student who added the course to check once
 * (plan/slide-uploads-plan.md U2, U11): rename, remove or add lectures, then confirm. After that it is the course's
 * list for everyone who adds the same syllabus, and only the researcher can change it.
 */
export default function SetupLectures() {
  const insets = useSafeAreaInsets();
  const myCourse = useMyCourse();
  const course = myCourse?.status === "ready" ? myCourse.course : null;
  // null until the student edits: the list as read from the syllabus
  const [edited, setRows] = useState<Row[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // someone else's course, or already confirmed: nothing to do here
  useEffect(() => {
    if (course && (!course.is_creator || course.lectures_confirmed)) router.replace("/");
  }, [course]);

  if (!course) return <View style={styles.screen} />;
  const rows: Row[] = edited ?? course.lectures.map((l) => ({ key: `l${l.n}`, title: l.title, week: l.week }));

  const update = (key: string, title: string) => setRows(rows.map((r) => (r.key === key ? { ...r, title } : r)));
  const remove = (key: string) => setRows(rows.filter((r) => r.key !== key));
  const blank = rows.some((r) => !r.title.trim());

  async function confirm() {
    if (!courseCalls || !course) return;
    setError(null);
    setSaving(true);
    try {
      await courseCalls.confirmLectures(
        course.id,
        rows.map((r, i) => ({ n: i + 1, title: r.title.trim(), week: r.week })),
      );
      await refreshCourse();
      router.replace(await finishSetup(course.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The lectures could not be saved.");
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Header
        bordered
        center={
          <T variant="cardTitle" accessibilityRole="header">
            Your lectures
          </T>
        }
      />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <T variant="codeSm" color={colors.onSurfaceVariant} style={{ textTransform: "uppercase", letterSpacing: 1.2 }}>
          {[course.code, course.name].filter(Boolean).join(" · ")}
        </T>
        {rows.length ? (
          <T variant="body" color={colors.onSurfaceVariant} style={{ marginTop: 8 }}>
            We read these lectures from your syllabus. Fix any that are off. Classmates who add the same syllabus will see
            this list too.
          </T>
        ) : (
          <View style={styles.note}>
            <Icon name="info-outline" size={18} color={colors.primary} />
            <T variant="body" color={colors.onSurfaceVariant} style={{ flex: 1 }}>
              Your syllabus doesn{"'"}t list its lectures. That{"'"}s fine: each slide file you add becomes a lecture. You can
              also type them in now.
            </T>
          </View>
        )}

        <View style={styles.list}>
          {rows.map((r, i) => (
            <View key={r.key} style={styles.row}>
              <View style={styles.badge}>
                <T variant="codeSm" color={colors.primaryDeep} style={{ fontFamily: fonts.monoSemibold }}>
                  {String(i + 1).padStart(2, "0")}
                </T>
              </View>
              <TextInput
                value={r.title}
                onChangeText={(t) => update(r.key, t)}
                placeholder="Lecture title"
                placeholderTextColor={colors.outline}
                maxLength={120}
                style={styles.input}
                accessibilityLabel={`Lecture ${i + 1} title`}
                returnKeyType="done"
              />
              <IconButton icon="close" label={`Remove lecture ${i + 1}`} onPress={() => remove(r.key)} color={colors.onSurfaceVariant} size={20} />
            </View>
          ))}
        </View>
        <Button label="Add a lecture" icon="add" kind="secondary" height={44} onPress={() => setRows([...rows, row("", null)])} style={{ marginTop: 12 }} />
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
        <Button label={saving ? "Saving…" : "Looks right"} trailingIcon="arrow-forward" disabled={saving || blank} onPress={confirm} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: space.gutter, paddingTop: 16, paddingBottom: 24 },
  note: { flexDirection: "row", gap: 10, marginTop: 12, padding: 14, borderRadius: radius.lg, backgroundColor: colors.primaryTint },
  list: { marginTop: 16, gap: 8 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingLeft: 10,
    paddingRight: 4,
    paddingVertical: 4,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceContainerLowest,
    ...shadow.card,
  },
  badge: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: colors.primaryTint },
  input: { ...type.body, flex: 1, minHeight: 44, color: colors.onSurface },
  footer: { paddingHorizontal: space.gutter, paddingTop: 12, gap: 8, borderTopWidth: 1, borderTopColor: colors.surfaceContainerHigh, backgroundColor: colors.surface },
});
