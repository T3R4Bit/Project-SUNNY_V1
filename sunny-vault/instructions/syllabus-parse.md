---
id: syllabus-parse-instructions
type: instruction
status: active
tags: [llm, exam-prep, calendar]
---

You are extracting structured schedule data from a pasted college syllabus for Keaton. You'll be given the class name, the semester's start and end dates (use these to resolve any date in the syllabus that doesn't include a year), and the raw syllabus text.

Respond with nothing but a single JSON object, no markdown code fence around it, no commentary before or after:

{"meeting_times": [{"days": ["Monday", "Wednesday"], "start_time": "10:00", "end_time": "10:50", "location": "Business Building Room 210"}], "due_dates": [{"title": "Project 1 due", "date": "2026-10-01"}], "exams": [{"title": "Midterm Exam", "date": "2026-10-15"}], "summary": "..."}

Field rules, all strict:
- "days": full weekday names ("Monday", not "Mon" or "M"), one entry per distinct day the class meets at these times. If lecture and lab meet at different times, that's two separate meeting_times entries.
- "start_time"/"end_time": 24-hour "HH:MM", always. "10:00 AM" becomes "10:00"; "2:30 PM" becomes "14:30".
- "location": the actual building/room string from the syllabus. Omit the field entirely (don't guess or write "TBD") if the syllabus doesn't state one.
- "date": always "YYYY-MM-DD", using the semester year you were given to resolve any date that's just a month/day in the source text.
- "due_dates": assignments, papers, projects, homework — anything with a due date but not an exam.
- "exams": midterms, finals, quizzes explicitly scheduled on a specific date. Don't invent an exam date that isn't explicitly stated.
- "summary": a compact plain-text paragraph — instructor name and contact info if given, office hours, and the grading breakdown (e.g. "30% exams, 25% projects, 20% homework, 25% participation"). This is what Sunny will show back when asked about the class later, so make it genuinely useful, not just a restatement that a grading breakdown exists.

If the syllabus doesn't clearly state something (no fixed meeting time, no due dates listed, etc.), use an empty list for that field rather than guessing. Never fabricate a date, time, or location that isn't actually in the text.
