// Uploaded courses, from the server's command line (plan/slide-uploads-plan.md): what students added, and the
// researcher's fixes. Students never reorganize a course themselves.
//   npm run courses -- list
//   npm run courses -- show <course>                       (lectures, decks, updated versions, failed jobs)
//   npm run courses -- rename <course> <n> "<title>"
//   npm run courses -- add-lecture <course> "<title>"
//   npm run courses -- move-deck <deck> <n>                (its KUs now count for lecture n)
//   npm run courses -- move-student <code|email> <course>  (before they have answered anything)
//   npm run courses -- merge <from-course> <into-course>   (its students and its syllabus join the other course)
//   npm run courses -- retry <job>                         (a failed upload job)
import { appendLecture, courseDetail, courseSummaries, mergeCourses, moveDeck, moveStudent, renameLecture, retryJob } from "../src/courseAdmin";
import { Courses } from "../src/courses";
import { openDb } from "../src/db";
import { Uploads } from "../src/uploads";

const db = openDb(process.env.SYLLABYTE_DB ?? "data/syllabyte.db");
const courses = new Courses(db);
const uploads = new Uploads(db, courses, process.env.SYLLABYTE_FILES ?? "data/files");
const [cmd, a, b, c] = process.argv.slice(2);

function usage(): never {
  console.error(
    "usage: npm run courses -- list | show <course> | rename <course> <n> <title> | add-lecture <course> <title> | move-deck <deck> <n> | move-student <code|email> <course> | merge <from> <into> | retry <job>",
  );
  process.exit(1);
}

try {
  if (cmd === "list") {
    const rows = courseSummaries(db);
    for (const r of rows)
      console.log(`${r.id}  ${[r.code, r.name].filter(Boolean).join(" · ")}  ${r.students} students, ${r.lectures} lectures, ${r.ready_decks} decks ready, ${r.failed_decks} failed`);
    console.log(`${rows.length} courses`);
  } else if (cmd === "show" && a) {
    console.log(JSON.stringify(courseDetail(db, courses, a), null, 2));
  } else if (cmd === "rename" && a && b && c) {
    renameLecture(courses, a, Number(b), c);
    console.log("renamed");
  } else if (cmd === "add-lecture" && a && b) {
    console.log(`added lecture ${appendLecture(courses, a, b)}`);
  } else if (cmd === "move-deck" && a && b) {
    moveDeck(db, courses, a, Number(b));
    console.log("moved");
  } else if (cmd === "move-student" && a && b) {
    moveStudent(db, courses, a, b);
    console.log("moved");
  } else if (cmd === "merge" && a && b) {
    mergeCourses(db, courses, a, b);
    console.log("merged");
  } else if (cmd === "retry" && a) {
    retryJob(uploads, a);
    console.log("queued again");
  } else usage();
} catch (e) {
  console.error((e as Error).message);
  process.exit(1);
}
