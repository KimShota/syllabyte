import { useState } from "react";
import { Pressable, StyleSheet, TextInput, View } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { colors, fonts, radius, type } from "@/theme/tokens";
import { Button } from "./Button";
import { IconButton } from "./Header";
import { Icon } from "./Icon";
import { Sheet, SheetHandle } from "./Sheet";
import { T } from "./T";

const ACCEPT = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
];

/** "Upload Course": a name plus the syllabus or slides. */
export function UploadSheet({ visible, onClose, onSubmit }: { visible: boolean; onClose: () => void; onSubmit: (name: string) => void }) {
  const [name, setName] = useState("");
  const [files, setFiles] = useState<string[]>([]);

  async function pick() {
    const res = await DocumentPicker.getDocumentAsync({ type: ACCEPT, multiple: true, copyToCacheDirectory: true });
    if (!res.canceled) setFiles(res.assets.map((a) => a.name));
  }

  function submit() {
    onSubmit(name.trim());
    setName("");
    setFiles([]);
  }

  return (
    <Sheet visible={visible} onClose={onClose} accessibilityLabel="Upload course">
      <View style={styles.body}>
        <SheetHandle />
        <View style={styles.titleRow}>
          <T variant="cardTitle" style={{ fontFamily: fonts.bold }}>
            Upload Course
          </T>
          <IconButton icon="close" label="Close" onPress={onClose} color={colors.onSurfaceVariant} style={styles.close} size={20} />
        </View>

        <View style={styles.field}>
          <T variant="caption" color={colors.onSurfaceVariant} style={{ fontFamily: fonts.semibold }}>
            Course Name
          </T>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="e.g. CS-201: Data Structures"
            placeholderTextColor={colors.outline}
            style={styles.input}
            accessibilityLabel="Course name"
            returnKeyType="done"
          />
        </View>

        <View style={styles.field}>
          <T variant="caption" color={colors.onSurfaceVariant} style={{ fontFamily: fonts.semibold }}>
            Syllabus or Slides (PDF/PPTX)
          </T>
          <Pressable
            onPress={pick}
            accessibilityRole="button"
            accessibilityLabel={files.length ? `${files.length} files chosen. Choose again` : "Choose files"}
            style={({ pressed }) => [styles.drop, pressed && { backgroundColor: colors.surfaceContainer }]}
          >
            <Icon name={files.length ? "check-circle" : "cloud-upload"} size={30} color={files.length ? colors.secondary : colors.primary} />
            <T variant="caption" style={{ fontFamily: fonts.semibold, marginTop: 4 }}>
              {files.length ? files.join(", ") : "Tap to choose files"}
            </T>
            <T variant="caption" color={colors.onSurfaceVariant} style={{ fontSize: 11, marginTop: 2 }}>
              PDF, DOCX, or PPTX up to 25MB
            </T>
          </Pressable>
        </View>

        <Button label="Add Course" onPress={submit} disabled={!name.trim() && files.length === 0} style={{ marginTop: 8 }} />
      </View>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  body: { paddingHorizontal: 24, paddingBottom: 16, gap: 16 },
  titleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  close: { backgroundColor: colors.surfaceContainer, borderRadius: radius.full, minWidth: 36, minHeight: 36 },
  field: { gap: 6 },
  input: {
    ...type.body,
    height: 48,
    paddingHorizontal: 16,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: colors.surfaceContainerHighest,
    color: colors.onSurface,
  },
  drop: {
    padding: 24,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceContainerLow,
    borderWidth: 2,
    borderStyle: "dashed",
    borderColor: colors.outlineVariant,
    alignItems: "center",
  },
});
