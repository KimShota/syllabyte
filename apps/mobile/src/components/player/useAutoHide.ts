import { useEffect, useState } from "react";
import { AccessibilityInfo, Platform } from "react-native";

/** How long the player's controls stay up after the last touch. */
export const IDLE_MS = 3000;

/**
 * The player's controls fade out after IDLE_MS without a touch so only the video is left. They stay up
 * while `pinned` (paused, a sheet or menu open, scrubbing), on a page that isn't on screen, and always
 * while a screen reader runs (hidden controls can't be found by swiping through them).
 */
export function useAutoHide({ active, pinned }: { active: boolean; pinned: boolean }) {
  const [hidden, setHidden] = useState(false);
  const [touches, setTouches] = useState(0);
  const [screenReader, setScreenReader] = useState(false);

  useEffect(() => {
    // react-native-web can't detect a screen reader and always reports one, which would pin the controls
    if (Platform.OS === "web") return;
    let live = true;
    AccessibilityInfo.isScreenReaderEnabled().then((on) => live && setScreenReader(on));
    const sub = AccessibilityInfo.addEventListener("screenReaderChanged", setScreenReader);
    return () => {
      live = false;
      sub.remove();
    };
  }, []);

  const canHide = active && !pinned && !screenReader;
  // anything that pins the controls brings them back; the idle timer starts over once it's released
  if (!canHide && hidden) setHidden(false);

  useEffect(() => {
    if (!canHide || hidden) return;
    const id = setTimeout(() => setHidden(true), IDLE_MS);
    return () => clearTimeout(id);
  }, [canHide, hidden, touches]);

  return {
    shown: !hidden,
    /** any touch on the page: restart the idle timer */
    touched: () => setTouches((n) => n + 1),
    reveal: () => setHidden(false),
  };
}
