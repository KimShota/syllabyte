"use client";

import { useEffect } from "react";
import { api } from "@syllabyte/core/api/client";
import { useQuery } from "@/lib/api/hooks";
import { track } from "@/lib/events";
import { InfoCard, LinkButton, TextLink } from "./ui/primitives";

/**
 * A questionnaire that is due (plan/study-instruments-plan.md I9): at the top of the playlist until it is submitted.
 * It never blocks learning; "Not now" hides it until the next visit.
 */
export function StudyCard() {
  const { data: tasks } = useQuery(() => api.getStudyTasks(), []);
  const ids = (tasks ?? []).map((t) => t.battery_id).join(",");
  useEffect(() => {
    for (const id of ids ? ids.split(",") : []) track("study_shown", { type: "battery", id });
  }, [ids]);
  if (!tasks?.length) return null;
  return (
    <>
      {tasks.map((t) => (
        <InfoCard key={t.battery_id} eyebrow="For the study" className="border-2 !border-primary/40">
          <p className="font-bold">{t.title}</p>
          <p className="mt-1">About {t.minutes} {t.minutes === 1 ? "minute" : "minutes"}. Not graded, and you can skip any question.</p>
          <div className="mt-3 flex flex-wrap items-center gap-4">
            <LinkButton href={`/study?b=${t.battery_id}`} full={false}>{t.started ? "Continue" : "Start"}</LinkButton>
            <TextLink tone="ink" onClick={() => void api.snoozeBattery(t.battery_id)}>Not now</TextLink>
          </div>
        </InfoCard>
      ))}
    </>
  );
}
