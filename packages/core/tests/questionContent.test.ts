import { describe, expect, it } from "vitest";
import { questionLabel, questionParts } from "../src/questionContent";

describe("question content", () => {
  it("leaves mathematical symbols, currency and HTML literal", () => {
    const text = 'For λ ∈ ℝ, is x² ≤ 4? O(n log n); $5. <script>alert(1)</script>';
    expect(questionParts(text)).toEqual([{ kind: "text", text }]);
  });

  it("preserves code indentation, case, operators and newlines", () => {
    const text = "In Python 3:\n```python\nx = 2\nif x < 3:\n    X = x ** 2\n```\nWhat is `X`?";
    expect(questionParts(text)).toEqual([
      { kind: "text", text: "In Python 3:\n" },
      { kind: "code", language: "python", text: "x = 2\nif x < 3:\n    X = x ** 2" },
      { kind: "text", text: "\nWhat is " },
      { kind: "inlineCode", text: "X" },
      { kind: "text", text: "?" },
    ]);
    expect(questionLabel(text)).toBe("In Python 3:\nx = 2\nif x < 3:\n    X = x ** 2\nWhat is X?");
  });

  it("keeps backticks inside fenced code literal and supports data matrices", () => {
    const text = '```js\nconst x = `hello`;\n```\n```text\n1 0\n0 1\n```';
    expect(questionParts(text).filter((p) => p.kind === "code").map((p) => p.text))
      .toEqual(['const x = `hello`;', '1 0\n0 1']);
  });

  it("accepts Windows newlines and preserves unfinished content", () => {
    expect(questionParts('```c++\r\nint x = 1;\r\n```')).toEqual([{ kind: "code", language: "c++", text: "int x = 1;" }]);
    expect(questionParts('Use `x and\n```python\nx = 1')).toEqual([{ kind: "text", text: 'Use `x and\n```python\nx = 1' }]);
    expect(questionParts("")).toEqual([]);
  });
});
