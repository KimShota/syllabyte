/** Sign-in emails: plain text, one code, no images or tracking (plan §9.4). */
export interface Mailer {
  send(to: string, subject: string, text: string): Promise<void>;
}

/** Local development: the email goes to the server log. */
export const consoleMailer: Mailer = {
  async send(to, subject, text) {
    console.log(`\n--- email to ${to}: ${subject}\n${text}\n---`);
  },
};

export function resendMailer(apiKey: string, from: string): Mailer {
  return {
    async send(to, subject, text) {
      const res = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
        body: JSON.stringify({ from, to, subject, text }),
      });
      if (!res.ok) throw new Error(`Resend ${res.status}`);
    },
  };
}

/** Tests: collects what would have been sent. */
export function memoryMailer(): Mailer & { sent: { to: string; subject: string; text: string }[] } {
  const sent: { to: string; subject: string; text: string }[] = [];
  return {
    sent,
    async send(to, subject, text) {
      sent.push({ to, subject, text });
    },
  };
}
