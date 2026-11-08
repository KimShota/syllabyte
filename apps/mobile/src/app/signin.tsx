import { useEffect, useRef, useState } from "react";
import { Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import * as Linking from "expo-linking";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ApiError } from "@syllabyte/core/api/remote";
import { Button } from "@/components/Button";
import { IconButton } from "@/components/Header";
import { T } from "@/components/T";
import { requestSignInLink, useSession, verifySignInLink } from "@/state/session";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

const looksLikeEmail = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim());
const signInError = (error: unknown) => error instanceof ApiError && error.status === 0
  ? "Can't reach the server. Check your connection and try again."
  : error instanceof ApiError ? error.message : "Something went wrong. Try again.";

/** Sign up with a new email or sign in to an existing account, then follow the email verification link. */
export default function SignIn() {
  const insets = useSafeAreaInsets();
  const { status } = useSession();
  const params = useLocalSearchParams<{ ticket?: string | string[]; mode?: string }>();
  const signingUp = params.mode === "signup";
  const ticket = typeof params.ticket === "string" ? params.ticket : null;
  const handledTicket = useRef<string | null>(null);
  const [step, setStep] = useState<"email" | "sent">("email");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Wait for saved-session loading so it cannot overwrite the new session. Redeem a ticket only once per mount.
    if (status !== "signedOut" || !ticket || handledTicket.current === ticket) return;
    handledTicket.current = ticket;
    setVerifying(true);
    setError(null);
    void verifySignInLink(ticket).then(() => router.replace("/"), (cause) => {
      handledTicket.current = null; // a network failure must allow the same emailed link to be opened again
      setError(signInError(cause));
      router.setParams({ ticket: undefined });
    }).finally(() => setVerifying(false));
  }, [status, ticket]);

  async function sendLink() {
    if (!looksLikeEmail(email) || busy || verifying) return;
    setBusy(true);
    setError(null);
    try {
      await requestSignInLink(email, Linking.createURL("/signin"), signingUp ? "signup" : "signin");
      setStep("sent");
    } catch (cause) {
      setError(signInError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom + 8 }]}>
      <View style={styles.topBar}>
        <IconButton icon="arrow-back" label="Back to welcome" onPress={() => router.dismissTo("/landing")} />
      </View>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Image source={require("../../assets/icon.png")} style={styles.logo} accessibilityIgnoresInvertColors />
          <T variant="titleMobile" style={{ fontFamily: fonts.extraBold, textAlign: "center" }} accessibilityRole="header">
            {verifying ? "Signing you in…" : step === "email" ? signingUp ? "Create your account" : "Sign in to SyllaByte" : signingUp ? "Verify your email" : "Check your email"}
          </T>
          <T variant="body" color="#606474" style={{ textAlign: "center", marginTop: 8, maxWidth: 320, fontFamily: fonts.medium }}>
            {verifying ? "Verifying your sign-in link."
              : step === "email" ? signingUp ? "Enter your email. We'll send a link to create your account." : "Enter your account email. We'll send a sign-in link."
              : signingUp ? `Check ${email.trim()} for a verification link. Open it to finish creating your account. The link lasts 10 minutes.`
              : `If ${email.trim()} has an account, we've sent a sign-in link. The link works once and lasts 10 minutes.`}
          </T>
        </View>

        <View style={styles.card}>
          {step === "email" && !verifying ? (
            <>
              <T variant="caption" color={colors.onSurfaceVariant} style={styles.label}>Email</T>
              <TextInput
                accessibilityLabel="Email"
                value={email}
                onChangeText={setEmail}
                autoCapitalize="none"
                autoComplete="email"
                autoCorrect={false}
                keyboardType="email-address"
                textContentType="emailAddress"
                placeholder="you@example.com"
                placeholderTextColor={colors.outline}
                returnKeyType="send"
                onSubmitEditing={() => void sendLink()}
                style={styles.input}
              />
              <Button label={busy ? "Sending…" : signingUp ? "Verify my email" : "Email me a sign-in link"} disabled={!looksLikeEmail(email) || busy} onPress={() => void sendLink()} trailingIcon="arrow-forward" />
            </>
          ) : verifying ? (
            <T variant="body" style={{ textAlign: "center" }} accessibilityLiveRegion="polite">Signing in…</T>
          ) : (
            <>
              <Button label={busy ? "Sending…" : "Send a new link"} disabled={busy} onPress={() => void sendLink()} />
              <Pressable accessibilityRole="button" onPress={() => { setStep("email"); setError(null); }} disabled={busy} hitSlop={8} style={styles.links}>
                <T variant="caption" color={colors.primary} style={{ fontFamily: fonts.semibold }}>Use a different email</T>
              </Pressable>
            </>
          )}
          {error ? <T variant="caption" color={colors.error} accessibilityRole="alert">{error}</T> : null}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#f2f3f7" },
  topBar: { paddingHorizontal: 12, alignItems: "flex-start" },
  content: { paddingHorizontal: 16, paddingTop: 48, paddingBottom: 24 },
  header: { alignItems: "center", marginBottom: 28 },
  logo: { width: 64, height: 64, borderRadius: radius.xl, marginBottom: 20 },
  card: {
    backgroundColor: colors.surfaceContainerLowest,
    borderRadius: 24,
    padding: 20,
    gap: 12,
    borderWidth: 1,
    borderColor: "rgba(243,232,255,0.6)",
    ...shadow.card,
  },
  label: { textTransform: "uppercase", letterSpacing: 1.2 },
  input: {
    minHeight: 52,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderColor: colors.outlineVariant,
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    fontFamily: fonts.medium,
    fontSize: 17,
    color: colors.onSurface,
  },
  links: { flexDirection: "row", justifyContent: "space-between", marginTop: 4 },
});
