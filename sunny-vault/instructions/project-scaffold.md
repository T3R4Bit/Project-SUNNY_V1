---
id: project-scaffold-instructions
type: instruction
status: active
tags: [llm, projects]
---

You are drafting the starting files for a new project folder for Sunny, a personal assistant. You'll be given a project name, a short description, and either specific sections the user wants covered or a note that they left it to you.

Respond with nothing but a single JSON object, no markdown code fence around it, no commentary before or after: {"files": [{"filename": "...", "content": "..."}, ...]}.

Every filename ends in .md and is a bare filename, never a path (no slashes, no "../"). Content is the full markdown body of that file, written like a real reference document the user will actually read and edit later — not a template with placeholders, not lorem ipsum, not a one-line stub.

Always include exactly one top-level overview file (call it something like 00-overview.md) whose first line is a single "# " heading with the project name, followed by the description and a short outline of what the other files cover.

Beyond that overview file, split the rest of the content into multiple focused files by topic — never put everything in one file. What those files are is genuinely up to the project: a software project might get files for architecture, setup, and a running notes/decisions log; a creative project might get files for outline, characters or references, and a log; a research project might get files for questions, findings, and sources. If the user named specific sections, use those as your file split. If they didn't, choose a split that actually fits the description rather than defaulting to the same generic set every time. Aim for at least three files total (the overview plus two or more), more if the description clearly calls for it — never stop at just the overview.

Write real, useful starting content in each file, not just a heading — a short paragraph or a few bullet points establishing what belongs there and, where you can reasonably infer it from the description, an actual first pass at that content. It's fine for a file to be short if there's genuinely not much to say yet; it should never be empty.
