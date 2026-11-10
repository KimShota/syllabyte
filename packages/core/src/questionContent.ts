/** Question strings stay backward compatible. Only code delimiters are interpreted; HTML is always text. */
export type QuestionPart = { kind: "text" | "inlineCode" | "code"; text: string; language?: string };

export function questionParts(source: string): QuestionPart[] {
  const parts: QuestionPart[] = [];
  // Fences must occupy their own lines. Inline code cannot cross a newline.
  const tokens = /^```([\w+-]*)[ \t]*\r?\n([\s\S]*?)^```[ \t]*(?=\r?$)|`([^`\r\n]+)`/gm;
  let cursor = 0;
  for (const match of source.matchAll(tokens)) {
    if (match.index! > cursor) parts.push({ kind: "text", text: source.slice(cursor, match.index) });
    if (match[2] !== undefined) {
      parts.push({ kind: "code", text: match[2].replace(/\r?\n$/, ""), language: match[1] || undefined });
    } else {
      parts.push({ kind: "inlineCode", text: match[3] });
    }
    cursor = match.index! + match[0].length;
  }
  if (cursor < source.length) parts.push({ kind: "text", text: source.slice(cursor) });
  return parts;
}

/** Keep symbols and code intact in screen reader labels, without speaking formatting delimiters. */
export function questionLabel(source: string): string {
  return questionParts(source).map((part) => part.text).join("");
}
