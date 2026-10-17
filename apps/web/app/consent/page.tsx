import { CONSENT_TEXT } from "@syllabyte/core/content/consent";
import { ConsentView } from "./ConsentView";

export default function Consent() {
  // The text lives in packages/core/src/content/consent.md so the approved wording can be dropped in; prebuild
  // mirrors it into this module.
  return <ConsentView markdown={CONSENT_TEXT} />;
}
