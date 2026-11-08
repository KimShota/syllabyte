import { Redirect, useLocalSearchParams } from "expo-router";

/** Old placement links open the roadmap; the server now organizes slides automatically. */
export default function SlideReview() {
  const { courseId } = useLocalSearchParams<{ courseId: string }>();
  return <Redirect href={{ pathname: "/course/[courseId]", params: { courseId } }} />;
}
