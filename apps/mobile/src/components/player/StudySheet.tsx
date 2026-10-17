import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { Icon } from "../Icon";
import { Sheet } from "../Sheet";
import { T } from "../T";
import { formatTime } from "@/data/selectors";
import type { Ku, TranscriptLine } from "@/data/types";
import { useStore } from "@/state/store";
import { colors, fonts, radius, type } from "@/theme/tokens";

const P = colors.player;

export type StudyMode = "notes" | "transcript";

export function activeLine(lines: TranscriptLine[], time: number): number {
  let idx = -1;
  for (let i = 0; i < lines.length; i++) if (lines[i].t <= time) idx = i;
  return idx;
}

/** The player's dark bottom sheet: the KU's notes, or its transcript. The video pauses while it's open. */
export function StudySheet({
  ku,
  mode,
  time,
  onClose,
  onSeek,
}: {
  ku: Ku;
  mode: StudyMode | null;
  time: number;
  onClose: () => void;
  onSeek: (t: number) => void;
}) {
  return (
    <Sheet visible={mode !== null} onClose={onClose} dark maxHeightRatio={0.82} accessibilityLabel={mode === "transcript" ? "Transcript" : "Lecture notes"}>
      <View style={styles.head}>
        <T variant="bodySemibold" color="#fff" style={{ fontFamily: fonts.bold, fontSize: 16 }} accessibilityRole="header">
          {mode === "transcript" ? "Transcript" : "Lecture Notes"}
        </T>
        <Pressable accessibilityRole="button" accessibilityLabel="Close and resume video" onPress={onClose} hitSlop={8} style={styles.close}>
          <Icon name="close" size={18} color="rgba(255,255,255,0.85)" />
        </Pressable>
      </View>
      {mode === "transcript" ? <Transcript ku={ku} time={time} onSeek={onSeek} /> : <Notes ku={ku} time={time} />}
    </Sheet>
  );
}

function Notes({ ku, time }: { ku: Ku; time: number }) {
  const { state, dispatch } = useStore();
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const notes = state.notes.filter((n) => n.kuId === ku.id).sort((a, b) => a.at - b.at);

  function save() {
    const text = draft.trim();
    if (!text) return;
    if (editing) dispatch({ type: "editNote", id: editing, text });
    else dispatch({ type: "addNote", note: { id: `${Date.now()}`, kuId: ku.id, at: time, text, createdAt: Date.now() } });
    setDraft("");
    setEditing(null);
  }

  return (
    <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
      <View style={styles.compose}>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder={`Type a quick note or key takeaway at ${formatTime(time)}...`}
          placeholderTextColor="rgba(255,255,255,0.4)"
          multiline
          style={styles.input}
          accessibilityLabel={editing ? "Edit note" : "New note"}
        />
        <View style={styles.composeActions}>
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              setDraft("");
              setEditing(null);
            }}
            style={styles.cancel}
          >
            <T variant="caption" color="#94a3b8">
              Cancel
            </T>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: !draft.trim() }}
            disabled={!draft.trim()}
            onPress={save}
            style={({ pressed }) => [styles.save, !draft.trim() && { opacity: 0.5 }, pressed && { backgroundColor: colors.primaryPressed }]}
          >
            <Icon name="bookmark-added" size={15} color="#fff" />
            <T variant="caption" color="#fff" style={{ fontFamily: fonts.semibold }}>
              {editing ? "Update Note" : "Save Note"}
            </T>
          </Pressable>
        </View>
      </View>

      <T variant="codeSm" color="#94a3b8" style={styles.savedLabel}>
        Saved for this concept ({notes.length})
      </T>
      {notes.map((n) => (
        <View key={n.id} style={[styles.note, editing === n.id && { borderColor: colors.primary }]}>
          <View style={styles.noteHead}>
            <T variant="codeSm" color={colors.secondaryContainer} style={{ fontSize: 11 }}>
              @ {formatTime(n.at)}
            </T>
            <View style={{ flexDirection: "row", gap: 4 }}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Edit note"
                hitSlop={6}
                onPress={() => {
                  setEditing(n.id);
                  setDraft(n.text);
                }}
                style={styles.noteBtn}
              >
                <Icon name="edit" size={15} color="#cbd5e1" />
              </Pressable>
              <Pressable accessibilityRole="button" accessibilityLabel="Delete note" hitSlop={6} onPress={() => dispatch({ type: "deleteNote", id: n.id })} style={styles.noteBtn}>
                <Icon name="delete" size={15} color={colors.errorSoft} />
              </Pressable>
            </View>
          </View>
          <T variant="caption" color="#e2e8f0" style={{ fontSize: 13, lineHeight: 20 }}>
            {n.text}
          </T>
        </View>
      ))}
    </ScrollView>
  );
}

function Transcript({ ku, time, onSeek }: { ku: Ku; time: number; onSeek: (t: number) => void }) {
  const current = activeLine(ku.transcript, time);
  if (ku.transcript.length === 0) {
    return (
      <View style={[styles.scroll, { paddingVertical: 32, alignItems: "center" }]}>
        <T variant="caption" color={P.textMuted}>
          No transcript for this video yet.
        </T>
      </View>
    );
  }
  return (
    <ScrollView contentContainerStyle={styles.scroll}>
      {ku.transcript.map((line, i) => {
        const on = i === current;
        return (
          <Pressable
            key={i}
            accessibilityRole="button"
            accessibilityLabel={`${formatTime(line.t)}. ${line.text}`}
            accessibilityHint="Jumps the video here"
            onPress={() => onSeek(line.t)}
            style={({ pressed }) => [styles.line, on && styles.lineOn, pressed && { backgroundColor: "rgba(255,255,255,0.1)" }]}
          >
            <View style={styles.lineHead}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                <T variant="codeSm" color={colors.secondaryContainer} style={{ fontFamily: on ? fonts.monoBold : fonts.monoSemibold }}>
                  [{formatTime(line.t)}]
                </T>
                {on ? (
                  <View style={styles.activeChip}>
                    <T variant="codeSm" color="#fff" style={{ fontSize: 10, fontFamily: fonts.monoSemibold }}>
                      ACTIVE
                    </T>
                  </View>
                ) : null}
              </View>
              {line.heading ? (
                <T variant="codeSm" color="#94a3b8" style={{ fontSize: 11, flexShrink: 1, textAlign: "right" }} numberOfLines={1}>
                  {line.heading}
                </T>
              ) : null}
            </View>
            <T variant="body" color={on ? "#fff" : "#e2e8f0"} style={{ fontSize: 14, fontFamily: on ? fonts.semibold : fonts.regular }}>
              {line.text}
            </T>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  head: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.1)",
  },
  close: { width: 32, height: 32, borderRadius: 16, backgroundColor: "rgba(255,255,255,0.1)", alignItems: "center", justifyContent: "center" },
  scroll: { padding: 16, gap: 12, paddingBottom: 24 },
  compose: { padding: 12, borderRadius: radius.xl, backgroundColor: "rgba(255,255,255,0.06)", borderWidth: 1, borderColor: "rgba(255,255,255,0.15)", gap: 10 },
  input: {
    ...type.caption,
    color: "#fff",
    minHeight: 84,
    padding: 12,
    borderRadius: radius.lg,
    backgroundColor: "rgba(0,0,0,0.4)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
    textAlignVertical: "top",
    lineHeight: 20,
  },
  composeActions: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingTop: 4, borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.05)" },
  cancel: { paddingHorizontal: 12, minHeight: 36, justifyContent: "center" },
  save: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 16, minHeight: 36, borderRadius: radius.lg, backgroundColor: colors.primary },
  savedLabel: { fontSize: 11, textTransform: "uppercase", letterSpacing: 1, fontFamily: fonts.monoSemibold, marginTop: 4 },
  note: { padding: 12, borderRadius: radius.xl, backgroundColor: "rgba(255,255,255,0.05)", borderWidth: 1, borderColor: "rgba(255,255,255,0.1)", gap: 6 },
  noteHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  noteBtn: { width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  line: { padding: 12, borderRadius: radius.xl, backgroundColor: "rgba(255,255,255,0.04)", borderWidth: 1, borderColor: "rgba(255,255,255,0.05)", gap: 4 },
  lineOn: { backgroundColor: "rgba(91,63,214,0.2)", borderColor: "rgba(91,63,214,0.4)" },
  lineHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  activeChip: { backgroundColor: colors.primary, paddingHorizontal: 6, borderRadius: 4 },
});
