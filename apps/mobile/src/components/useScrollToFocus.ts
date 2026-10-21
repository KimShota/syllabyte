import { useCallback, useRef } from "react";
import type { HostInstance, LayoutChangeEvent, ScrollViewInstance } from "react-native";

/**
 * Opens a long roadmap where the student is, not at its top: once the row for `focusKey` has been laid out, the scroll
 * view jumps so that row sits in the middle of the screen. It moves at most once per focus, and never after the
 * student has scrolled themselves. `focusKey` null leaves the screen at its top.
 *
 * Wiring: the ScrollView takes `scrollRef`, `onScrollLayout` and `onScrollBeginDrag`; a View wrapping everything
 * inside it takes `contentRef`; the focused row takes `focusRef` and `onFocusLayout` (Serpentine does this for its
 * `focusKey` row).
 */
export function useScrollToFocus(focusKey: string | null) {
  const scrollRef = useRef<ScrollViewInstance>(null);
  const contentRef = useRef<HostInstance>(null);
  const focusRef = useRef<HostInstance>(null);
  const viewport = useRef(0);
  const touched = useRef(false);
  const scrolledTo = useRef<string | null>(null);

  const onFocusLayout = useCallback(() => {
    if (!focusKey || touched.current || scrolledTo.current === focusKey) return;
    const row = focusRef.current;
    const content = contentRef.current;
    if (!row || !content || !viewport.current) return;
    row.measureLayout(content, (_x, y, _w, h) => {
      scrolledTo.current = focusKey;
      scrollRef.current?.scrollTo({ y: Math.max(0, y + h / 2 - viewport.current / 2), animated: false });
    });
  }, [focusKey]);

  const onScrollLayout = useCallback(
    (e: LayoutChangeEvent) => {
      viewport.current = e.nativeEvent.layout.height;
      onFocusLayout();
    },
    [onFocusLayout],
  );

  const onScrollBeginDrag = useCallback(() => {
    touched.current = true;
  }, []);

  return { scrollRef, contentRef, focusRef, onScrollLayout, onScrollBeginDrag, onFocusLayout };
}
