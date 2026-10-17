import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import * as DocumentPicker from "expo-document-picker";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/Button";
import { Icon, type IconName } from "@/components/Icon";
import { T } from "@/components/T";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

const MIME = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  key: "application/x-iwork-keynote-sffkey",
};

/** First run: upload the syllabus and the lecture slides. */
export default function Welcome() {
  const insets = useSafeAreaInsets();
  const [syllabus, setSyllabus] = useState<string | null>(null);
  const [slides, setSlides] = useState<string | null>(null);

  return (
    <View style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom + 8 }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View style={styles.logo}>
            <Icon name="menu-book" size={28} color={colors.onPrimary} />
          </View>
          <T variant="titleMobile" style={{ fontFamily: fonts.extraBold, textAlign: "center" }} accessibilityRole="header">
            Welcome to SyllaByte
          </T>
          <T variant="body" color="#606474" style={{ textAlign: "center", marginTop: 8, maxWidth: 300, fontFamily: fonts.medium }}>
            Upload your course materials to auto-generate interactive study roadmaps.
          </T>
        </View>

        <View style={styles.card}>
          <Dropzone
            title="Syllabus"
            icon="description"
            tint={colors.primaryTint}
            iconColor={colors.primary}
            formats={["PDF", "DOCX"]}
            file={syllabus}
            onPick={async () => {
              const res = await DocumentPicker.getDocumentAsync({ type: [MIME.pdf, MIME.docx] });
              if (!res.canceled) setSyllabus(res.assets[0].name);
            }}
          />
          <Dropzone
            title="Lecture Slides"
            icon="slideshow"
            tint="#e6f7f4"
            iconColor="#0d9488"
            formats={["PDF", "PPTX", "KEY"]}
            file={slides}
            onPick={async () => {
              const res = await DocumentPicker.getDocumentAsync({ type: [MIME.pdf, MIME.pptx, MIME.key], multiple: true });
              if (!res.canceled) setSlides(res.assets.map((a) => a.name).join(", "));
            }}
          />
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <Button
          label="Get Started"
          trailingIcon="arrow-forward"
          onPress={() => router.push({ pathname: "/analyzing", params: { from: "welcome" } })}
        />
        {!syllabus && !slides ? (
          <T variant="caption" color={colors.onSurfaceVariant} style={{ textAlign: "center" }}>
            No files yet? Continue with the demo course, CS-UH 2219E.
          </T>
        ) : null}
      </View>
    </View>
  );
}

function Dropzone({
  title,
  icon,
  tint,
  iconColor,
  formats,
  file,
  onPick,
}: {
  title: string;
  icon: IconName;
  tint: string;
  iconColor: string;
  formats: string[];
  file: string | null;
  onPick: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={file ? `${title}: ${file}. Choose a different file` : `Upload ${title.toLowerCase()} file`}
      onPress={onPick}
      style={({ pressed }) => [styles.drop, file && styles.dropDone, pressed && { borderColor: colors.primary, backgroundColor: colors.primaryTint }]}
    >
      <View style={[styles.dropIcon, { backgroundColor: file ? colors.secondaryContainer : tint }]}>
        <Icon name={file ? "check" : icon} size={24} color={file ? colors.secondary : iconColor} />
      </View>
      <T variant="bodySemibold" style={{ fontFamily: fonts.bold, fontSize: 16 }}>
        {title}
      </T>
      <T variant="caption" color="#606474" style={{ fontSize: 12, marginTop: 2 }} numberOfLines={1}>
        {file ?? "Select file"}
      </T>
      <View style={styles.formats}>
        {formats.map((f) => (
          <View key={f} style={styles.format}>
            <T variant="codeSm" color="#64748b" style={{ fontSize: 11, fontFamily: fonts.bold }}>
              {f}
            </T>
          </View>
        ))}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#f2f3f7" },
  content: { paddingHorizontal: 16, paddingTop: 24, paddingBottom: 24 },
  header: { alignItems: "center", marginBottom: 28 },
  logo: {
    width: 56,
    height: 56,
    borderRadius: radius.xl,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 20,
    ...shadow.glow,
  },
  card: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: 24,
    padding: 16,
    gap: 16,
    borderWidth: 1,
    borderColor: "rgba(243,232,255,0.6)",
    ...shadow.card,
  },
  drop: {
    borderRadius: radius.xl,
    borderWidth: 1.5,
    borderStyle: "dashed",
    borderColor: colors.outlineVariant,
    padding: 20,
    alignItems: "center",
  },
  dropDone: { borderStyle: "solid", borderColor: "rgba(0,107,93,0.35)" },
  dropIcon: { width: 48, height: 48, borderRadius: radius.lg, alignItems: "center", justifyContent: "center", marginBottom: 12 },
  formats: { flexDirection: "row", gap: 8, marginTop: 14 },
  format: { paddingHorizontal: 10, paddingVertical: 2, borderRadius: 6, borderWidth: 1, borderColor: "#e2e8f0", backgroundColor: "#f8fafc" },
  footer: { paddingHorizontal: 16, gap: 10 },
});
