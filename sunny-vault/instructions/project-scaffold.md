---
id: project-scaffold-instructions
type: instruction
status: active
tags: [llm, projects]
---

You are drafting the single starting file for a new project folder for Sunny, a personal assistant. You'll be given a project name, a short description, and either specific sections the user wants covered or a note that they left it to you.

Respond with nothing but a single JSON object, no markdown code fence around it, no commentary before or after: {"files": [{"filename": "...", "content": "..."}]} — exactly one entry in the list.

The filename ends in .md and is a bare filename, never a path (no slashes, no "../"); call it something like 00-overview.md.

Content is the full markdown body of that one file, written like a real reference document the user will actually read and edit later — not a template with placeholders, not lorem ipsum. It has exactly two sections:

1. A "# " heading with the project name, followed by the description and a short explanation of what the project is and why it matters — written in real prose, not a stub.
2. A "## Proposed Architecture" heading laying out a genuine first pass at how the project would be structured — components, how they fit together, key decisions or tradeoffs worth flagging. Tailor this to what the project actually is: a software project gets modules/data flow/stack choices, a research project gets phases/methodology, a creative project gets structure/format — whatever "architecture" means for this kind of project. If the user named specific sections they want covered, fold those into this section rather than adding more files.

Do not create any other files or sections beyond these two.
