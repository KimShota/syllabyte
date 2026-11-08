import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Animated, Image, ScrollView, StyleSheet, View } from "react-native";
import { router } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { AnalyzerMaterial } from "@syllabyte/core/api/types";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { useLoop } from "@/components/Motion";
import { T } from "@/components/T";
import { REMOTE } from "@/data/backend";
import { analyzerFrames, MATERIAL_STATUS } from "@/data/analyzer";
import { backendMediaUrl } from "@/data/media";
import { setPrefs } from "@/state/app";
import { useMyCourse } from "@/state/course";
import { courseCalls } from "@/state/session";
import { finishSetup } from "@/state/uploads";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

/** Original uploaded pages with document-level processing status; browsing never blocks background work. */
export default function Analyzing() {
  const insets = useSafeAreaInsets();
  const [materials, setMaterials] = useState<AnalyzerMaterial[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [index, setIndex] = useState(0);
  const [previewHeight, setPreviewHeight] = useState(0);
  const [failedImage, setFailedImage] = useState<string | null>(null);
  const finishing = useRef(false);
  const left = useRef(false);
  const imageUrls = useRef(new Map<string, { uri: string; at: number }>());
  const sweep = useLoop(1800);
  const myCourse = useMyCourse();
  const frames = analyzerFrames(materials);
  const frame = frames[index % Math.max(1, frames.length)];

  function goHome() {
    left.current = true;
    setPrefs({ setupDone: true });
    router.dismissTo("/");
  }

  useEffect(() => {
    if (!courseCalls) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await courseCalls!.materials();
        if (active) {
          // Keep Image sources stable between status polls, refreshing signed links before they expire.
          const now = Date.now();
          for (const file of next) for (const page of file.pages) {
            if (!page.image_url) continue;
            const key = `${file.id}:${page.n}`;
            const cached = imageUrls.current.get(key);
            if (cached && now - cached.at < 120_000) page.image_url = cached.uri;
            else imageUrls.current.set(key, { uri: page.image_url, at: now });
          }
          setMaterials(next);
          setLoadFailed(false);
        }
      } catch {
        if (active) setLoadFailed(true);
      }
      if (active) timer = setTimeout(() => void refresh(), 4000);
    }
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, []);

  useEffect(() => {
    if (left.current || !REMOTE || !myCourse || myCourse.status === "reading") return;
    if (myCourse.status === "ready" && (myCourse.adding?.status === "reading" ||
      (myCourse.course.slides_pending ?? 0) > 0 || myCourse.course.lectures.some((l) => l.state === "analyzing"))) return;
    if (myCourse.status !== "ready" || myCourse.adding?.status === "failed") {
      router.replace("/welcome");
      return;
    }
    if (finishing.current) return;
    finishing.current = true;
    void finishSetup(myCourse.course.id).then(
      (next) => { if (!left.current) router.replace(next); },
      () => { if (!left.current) router.replace("/"); },
    );
  }, [myCourse]);

  useEffect(() => {
    if (!frames.length) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % frames.length), 3000);
    return () => clearInterval(timer);
  }, [frames.length]);

  useEffect(() => {
    if (REMOTE) return;
    const timer = setTimeout(() => { if (!left.current) router.replace("/quiz"); }, 6000);
    return () => clearTimeout(timer);
  }, []);

  const pageLabel = frame?.page ? `${frame.file.unit === "slide" ? "Slide" : frame.file.unit === "section" ? "Section" : "Page"} ${frame.page.n} of ${frame.file.pages.length}` : "Preparing page previews…";
  const image = frame?.page?.image_url ? backendMediaUrl(frame.page.image_url) : undefined;
  const laserY = sweep.interpolate({ inputRange: [0, 1], outputRange: [0, Math.max(0, previewHeight - 3)] });

  return (
    <View style={[styles.screen, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 16 }]}>
      <View style={styles.tag}>
        <Icon name="psychology" size={18} color={colors.outline} />
        <T variant="codeSm" color={colors.outline} style={{ fontFamily: fonts.monoMedium }}>ANALYZER</T>
      </View>
      <T variant="titleMobile" style={styles.title} accessibilityRole="header">Analyzing your materials...</T>

      <View style={styles.deck}>
        <View style={styles.deckBack} />
        <View style={styles.card}>
          <View style={styles.fileHeader}>
            <Icon name={frame?.file.kind === "syllabus" ? "description" : "layers"} size={19} color={colors.primary} />
            <View style={{ flex: 1, gap: 4 }}>
              <T variant="bodySemibold" style={{ fontSize: 14, lineHeight: 20 }} numberOfLines={2}>
                {frame?.file.file_name ?? "Your uploaded materials"}
              </T>
              <T variant="codeSm" color={colors.primary} style={{ fontSize: 11 }}>{frame?.file.kind === "syllabus" ? "Syllabus · " : ""}{frame ? pageLabel : "Loading documents…"}</T>
            </View>
          </View>
          {frame ? <T variant="caption" color={frame.file.state === "failed" ? colors.error : colors.onSurfaceVariant} style={styles.status}>
            {MATERIAL_STATUS[frame.file.state]}
          </T> : null}

          <View style={styles.preview} onLayout={(e) => setPreviewHeight(e.nativeEvent.layout.height)}>
            {image && failedImage !== image ? (
              <Image key={frame.key} source={{ uri: image }} resizeMode="contain" style={styles.image}
                accessibilityLabel={`${frame.file.file_name}, ${pageLabel}`} onError={() => setFailedImage(image)} />
            ) : frame?.page?.text ? (
              <ScrollView key={frame.key} contentContainerStyle={styles.textPreview}>
                <T variant="caption" color={colors.outline}>Extracted document text</T>
                <T variant="body" style={{ fontSize: 13, lineHeight: 20 }}>{frame.page.text}</T>
              </ScrollView>
            ) : (
              <View style={styles.placeholder}>
                {!loadFailed && frame?.file.preview_state !== "failed" ? <ActivityIndicator color={colors.primary} /> : <Icon name="description" size={32} color={colors.outline} />}
                <T variant="caption" color={colors.onSurfaceVariant} style={{ textAlign: "center" }}>
                  {loadFailed ? "Couldn’t load your materials. Retrying…" : image && failedImage === image ? "This page preview could not be loaded." : frame?.file.preview_state === "failed" ? "A page preview isn’t available for this file. Processing status is shown above." : REMOTE ? "Preparing previews of your uploaded pages…" : "Upload materials with a connected server to see your pages here."}
                </T>
              </View>
            )}
            {frame?.page ? <Animated.View pointerEvents="none" style={[styles.laser, { transform: [{ translateY: laserY }] }]}>
              <LinearGradient colors={["transparent", colors.primary, colors.secondary]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={{ flex: 1 }} />
            </Animated.View> : null}
          </View>
          {frame?.page ? <T variant="caption" color={colors.outline} style={styles.previewNote}>Previewing your uploaded pages</T> : null}
        </View>
      </View>

      <View style={styles.footer}>
        <T variant="caption" color={colors.onSurfaceVariant} style={{ textAlign: "center" }}>Your materials will keep processing in the background.</T>
        <Button label="Go to home" icon="home" onPress={goHome} accessibilityHint="Explore the app while your materials keep processing" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: 24 },
  tag: { minHeight: 36, flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 },
  title: { textAlign: "center", marginBottom: 16 },
  deck: { flex: 1, marginBottom: 8 },
  deckBack: { position: "absolute", top: 8, left: 8, right: 8, bottom: -8, borderRadius: radius.xl, backgroundColor: "rgba(232,231,243,0.6)" },
  card: { flex: 1, borderRadius: radius.xl, backgroundColor: colors.surfaceContainerLowest, borderWidth: 1, borderColor: "rgba(201,196,215,0.3)", padding: 16, overflow: "hidden", ...shadow.raised },
  fileHeader: { flexDirection: "row", alignItems: "center", gap: 10 },
  status: { marginTop: 8, marginBottom: 12, fontSize: 12 },
  preview: { flex: 1, overflow: "hidden", borderRadius: radius.md, backgroundColor: colors.surfaceContainerLow },
  image: { width: "100%", height: "100%", backgroundColor: "white" },
  textPreview: { padding: 16, gap: 12 },
  placeholder: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 16 },
  laser: { position: "absolute", left: 0, right: 0, top: 0, height: 3, ...shadow.glow },
  previewNote: { textAlign: "center", marginTop: 10, fontSize: 11 },
  footer: { paddingTop: 16, gap: 12 },
});
