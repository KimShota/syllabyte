import { questionParts } from "@syllabyte/core/questionContent";

export function QuestionText({ children }: { children: string }) {
  return <span style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{questionParts(children).map((part, i) =>
    part.kind === "text" ? part.text : <span key={i} style={{
      fontFamily: "ui-monospace, monospace",
      ...(part.kind === "code" ? { display: "block", overflowX: "auto", whiteSpace: "pre", padding: "8px 0", maxWidth: "100%" } : {}),
    }}>{part.text}</span>,
  )}</span>;
}
