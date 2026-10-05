/**
 * Production serves the pipeline's MP4. A test build (NEXT_PUBLIC_TEST_WEBM=1) lists a small
 * WebM first, because Playwright's Chromium has no H.264 decoder. Real browsers are unaffected.
 */
export function VideoSources({ url }: { url: string }) {
  return (
    <>
      {process.env.NEXT_PUBLIC_TEST_WEBM === "1" && <source src={url.replace(/\.mp4$/, ".webm")} type="video/webm" />}
      <source src={url} type="video/mp4" />
    </>
  );
}
