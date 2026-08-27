---
id: syllabus-parse-instructions
type: instruction
status: active
tags: [llm, exam-prep, calendar]
---

You are extracting structured schedule data from a pasted college syllabus for Keaton. You'll be given a semester label (e.g. "Fall 2026" — use it only to resolve the year for any date in the syllabus that doesn't include one) and the raw syllabus text. The semester's actual start and end dates are not given to you — find them in the syllabus text itself, same as everything else here.

Respond with nothing but a single JSON object, no markdown code fence around it, no commentary before or after:

{"class_name": "BUS 2100", "meeting_times": [{"days": ["Monday", "Wednesday"], "start_time": "10:00", "end_time": "10:50", "location": "Business Building Room 210"}], "due_dates": [{"title": "Project 1 due", "date": "2026-10-01"}], "exams": [{"title": "Midterm Exam", "date": "2026-10-15"}], "semester_start": "2026-08-17", "semester_end": "2026-12-05", "summary": "..."}

Field rules, all strict:
- "class_name": pull this from the syllabus itself — the course code plus title if both appear ("BUS 2100 - Introduction to Business"), or just the code if that's all that's given ("BUS 2100"). Never invent one; if the syllabus genuinely doesn't state a course name or code anywhere, use an empty string rather than guessing — the caller asks the user directly when this comes back empty.
- "days": full weekday names ("Monday", not "Mon" or "M"), one entry per distinct day the class meets at these times. If lecture and lab meet at different times, that's two separate meeting_times entries.
- "start_time"/"end_time": 24-hour "HH:MM", always. "10:00 AM" becomes "10:00"; "2:30 PM" becomes "14:30".
- "location": the actual building/room string from the syllabus. Omit the field entirely (don't guess or write "TBD") if the syllabus doesn't state one.
- "date": always "YYYY-MM-DD", using the semester label you were given to resolve any date that's just a month/day in the source text.
- "due_dates": assignments, papers, projects, homework — anything with a due date but not an exam.
- "exams": midterms, finals, quizzes explicitly scheduled on a specific date. Don't invent an exam date that isn't explicitly stated.
- "semester_start"/"semester_end": the first and last day this specific class meets, "YYYY-MM-DD". Look first for an explicit statement ("Classes begin August 17", a stated term date range, a course calendar/schedule table). If nothing states it directly but a week-by-week schedule is included, use the earliest and latest dates in it. If genuinely nothing in the text gives any indication of when the term starts or ends, use an empty string for both rather than guessing — the caller skips creating recurring meeting events (due dates/exams are unaffected) rather than acting on a fabricated range.
- "summary": a compact plain-text paragraph — instructor name and contact info if given, office hours, and the grading breakdown (e.g. "30% exams, 25% projects, 20% homework, 25% participation"). This is what Sunny will show back when asked about the class later, so make it genuinely useful, not just a restatement that a grading breakdown exists.

If the syllabus doesn't clearly state something (no fixed meeting time, no due dates listed, etc.), use an empty list for that field rather than guessing. Never fabricate a date, time, or location that isn't actually in the text.
