"use client";

import { useState } from "react";

interface Course {
  name: string;
  code: string;
}

export default function Home() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseName, setCourseName] = useState("");
  const [courseCode, setCourseCode] = useState("");
  function addCourse() {
  if (courseName.trim() === "" || courseCode.trim() === "") return;

  const newCourse: Course = {
    name: courseName,
    code: courseCode,
  };

  setCourses([...courses, newCourse]);

  setCourseName("");
  setCourseCode("");
}

  return (
    <main className="min-h-screen bg-gray-950 text-white p-10">
      <h1 className="text-4xl font-bold">
        StudentFlow
      </h1>

      <p className="mt-2 text-gray-400">
        Your university life, organized.
      </p>

      <div className="mt-10">
        <div className="mt-6 flex gap-3">
          <input
            type="text"
            placeholder="Course name"
            value={courseName}
            onChange={(e) => setCourseName(e.target.value)}
            className="rounded-lg border border-gray-700 bg-gray-900 px-4 py-2 text-white outline-none"
          />
          <input
            type="text"
            placeholder="Course code"
            value={courseCode}
            onChange={(e) => setCourseCode(e.target.value)}
            className="rounded-lg border border-gray-700 bg-gray-900 px-4 py-2 text-white outline-none"
          />

          <button
            onClick={addCourse}
            className="rounded-lg bg-white px-4 py-2 font-medium text-black hover:bg-gray-200"
          >
            Add
          </button>
        </div>
        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
            <p className="text-sm text-gray-400">Courses</p>
            <p className="mt-2 text-3xl font-bold">{courses.length}</p>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
            <p className="text-sm text-gray-400">Assignments</p>
            <p className="mt-2 text-3xl font-bold">0</p>
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
            <p className="text-sm text-gray-400">Exams</p>
            <p className="mt-2 text-3xl font-bold">0</p>
          </div>
        </div>
        <div className="mt-10">
          <h2 className="text-2xl font-semibold">My Courses</h2>

          <div className="mt-4 space-y-3">
            {courses.map((course, index) => (
              <div
                key={index}
                className="rounded-lg border border-gray-800 bg-gray-900 p-4"
              >
                <p className="font-semibold">{course.name}</p>
                <p className="mt-1 text-sm text-gray-400">{course.code}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}