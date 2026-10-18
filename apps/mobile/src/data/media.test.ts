import { describe, expect, it } from "vitest";
import { mediaBase, mediaUrl } from "./media";

describe("mediaBase", () => {
  it("uses the override, without a trailing slash", () => {
    expect(mediaBase("https://cdn.example.com/", "192.168.1.5:8081")).toBe("https://cdn.example.com");
  });
  it("falls back to the Metro host on the media port", () => {
    expect(mediaBase(undefined, "192.168.1.5:8081")).toBe("http://192.168.1.5:8787");
  });
  it("is null when the host is unknown", () => {
    expect(mediaBase(undefined, undefined)).toBeNull();
  });
});

describe("mediaUrl", () => {
  it("appends the fixture path to the base", () => {
    expect(mediaUrl("/fixtures/ku-a/video.mp4", "http://h:8787")).toBe("http://h:8787/fixtures/ku-a/video.mp4");
  });
  it("is undefined without a base, so the player falls back to the stand-in frame", () => {
    expect(mediaUrl("/fixtures/ku-a/video.mp4", null)).toBeUndefined();
  });
});
