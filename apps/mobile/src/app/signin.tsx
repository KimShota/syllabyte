import { useState } from "react";
import { Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ApiError } from "@syllabyte/core/api/remote";
import { Button } from "@/components/Button";
import { T } from "@/components/T";
import { requestSignInCode, verifySignInCode } from "@/state/session";
import { colors, fonts, radius, shadow } from "@/theme/tokens";

const looksLikeEmail = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim());

/**
 * Sign in with the email the course gave SyllaByte and the 6-character code emailed to it. The root layout moves a
 * signed-in student on to Home. There is no "create account": only enrolled emails get a code, and this screen says
 * the same thing either way.
 */
export default function SignIn() {
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function sendCode() {
    setBusy(true);
    setError(null);
    try {
      await requestSignInCode(email);
      setStep("code");
      setCode("");
    } catch (e) {
      setError(e instanceof ApiError && e.status === 0 ? "Can't reach the server. Check your connection and try again." : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function submitCode() {
    setBusy(true);
    setError(null);
    try {
      await verifySignInCode(email, code);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 0
          ? "Can't reach the server. Check your connection and try again."
          : "That code didn't work. Check it, or ask for a new one.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={[styles.screen, { paddingTop: insets.top, paddingBottom: insets.bottom + 8 }]}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Image source={require("../../assets/icon.png")} style={styles.logo} accessibilityIgnoresInvertColors />
          <T variant="titleMobile" style={{ fontFamily: fonts.extraBold, textAlign: "center" }} accessibilityRole="header">
            {step === "email" ? "Sign in to SyllaByte" : "Check your email"}
          </T>
          <T variant="body" color="#606474" style={{ textAlign: "center", marginTop: 8, maxWidth: 320, fontFamily: fonts.medium }}>
            {step === "email"
              ? "Use the email address your course has for you. We'll send you a code."
              : `If ${email.trim()} is enrolled in a SyllaByte course, we've sent it a 6-character code. It works once and lasts 10 minutes.`}
          </T>
        </View>

        <View style={styles.card}>
          {step === "email" ? (
            <>
              <T variant="caption" color={colors.onSurfaceVariant} style={styles.label}>
                Email
              </T>
              <TextInput
                accessibilityLabel="Email"
                value={email}
                onChangeText={setEmail}
                autoCapitalize="none"
                autoComplete="email"
                autoCorrect={false}
                keyboardType="email-address"
                textContentType="emailAddress"
                placeholder="you@nyu.edu"
                placeholderTextColor={colors.outline}
                returnKeyType="send"
                onSubmitEditing={() => looksLikeEmail(email) && !busy && void sendCode()}
                style={styles.input}
              />
              {error ? <T variant="caption" color={colors.error} accessibilityRole="alert">{error}</T> : null}
              <Button label={busy ? "Sending..." : "Send me a code"} disabled={!looksLikeEmail(email) || busy} onPress={() => void sendCode()} trailingIcon="arrow-forward" />
            </>
          ) : (
            <>
              <T variant="caption" color={colors.onSurfaceVariant} style={styles.label}>
                Code
              </T>
              <TextInput
                accessibilityLabel="Sign-in code"
                value={code}
                onChangeText={(t) => setCode(t.toUpperCase().replace(/[^A-Z0-9]/g, ""))}
                autoCapitalize="characters"
                autoComplete="one-time-code"
                autoCorrect={false}
                maxLength={6}
                textContentType="oneTimeCode"
                placeholder="ABC123"
                placeholderTextColor={colors.outline}
                returnKeyType="done"
                onSubmitEditing={() => code.length === 6 && !busy && void submitCode()}
                style={[styles.input, styles.codeInput]}
              />
              {error ? <T variant="caption" color={colors.error} accessibilityRole="alert">{error}</T> : null}
              <Button label={busy ? "Signing in..." : "Sign in"} disabled={code.length !== 6 || busy} onPress={() => void submitCode()} />
              <View style={styles.links}>
                <Pressable accessibilityRole="button" onPress={() => void sendCode()} disabled={busy} hitSlop={8}>
                  <T variant="caption" color={colors.primary} style={{ fontFamily: fonts.semibold }}>
                    Send a new code
                  </T>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => {
                    setStep("email");
                    setError(null);
                  }}
                  hitSlop={8}
                >
                  <T variant="caption" color={colors.primary} style={{ fontFamily: fonts.semibold }}>
                    Use a different email
                  </T>
                </Pressable>
              </View>
            </>
          )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#f2f3f7" },
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
  codeInput: { fontFamily: fonts.monoSemibold, fontSize: 24, letterSpacing: 8, textAlign: "center" },
  links: { flexDirection: "row", justifyContent: "space-between", marginTop: 4 },
});
