"""Debrief: dump what happened, answer a question or two, have it filed.

THE SHAPE, AND WHY
------------------
You type what happened in whatever form it comes out. Sunny reads it,
asks **at most two** questions, and then files the result into long-term
memory and the task list.

Two questions is a hard cap, not a default. The value of this is that it
costs less effort than writing things up properly -- a flow that asks six
questions is just a form, and a form is the thing you do not fill in. The
prompt is told to ask nothing when the dump is already clear, and the
flow handles zero questions by going straight to filing.

WHY IT ASKS AT ALL
------------------
A raw dump is full of things only you know: whether "the lab ran long"
means a one-off or a recurring problem, whether "didn't get to the essay"
is the one due Friday. Those are exactly the details that decide whether
something becomes a task with a date or a fact about how you work. One
question resolves more than a paragraph of guessing.

TWO DESTINATIONS, DELIBERATELY SEPARATE
---------------------------------------
- **Facts** go to memory_store: durable things about you, your
  preferences, your constraints, how you work.
- **Tasks** go to the task list: things with an action attached.

They are proposed separately and filed separately because they decay
differently. A task gets completed and archived; a fact stays true until
it does not. Mixing them would mean either tasks polluting memory or
facts quietly disappearing when a task is closed.

NOTHING IS FILED WITHOUT BEING SHOWN
------------------------------------
Every proposed fact and task is listed back before it is written. An
assistant that silently decides what to remember about you is one you
stop trusting the first time it gets something wrong, and the whole point
of memory is that it is load-bearing.
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from sunny_code.components import llm_client

logger = logging.getLogger(__name__)

_MODEL = "sonnet"

# Hard cap. See the module docstring -- this is the feature, not a limit
# on it.
MAX_QUESTIONS = 2

FACT_KINDS = ["fact", "preference", "flaw", "constraint"]

_ANALYSE_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "description": (
                "At most two clarifying questions, and only where the answer would "
                "change what gets filed. Empty when the dump is already clear."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Asked directly, one sentence."},
                    "why": {
                        "type": "string",
                        "description": "What this changes about what gets filed. Not shown, but it forces the question to earn its place.",
                    },
                },
                "required": ["question", "why"],
                "additionalProperties": False,
            },
        },
        "summary": {
            "type": "string",
            "description": "One or two sentences reflecting the dump back, so it is clear what was understood.",
        },
    },
    "required": ["questions", "summary"],
    "additionalProperties": False,
}

_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "description": "Durable things about Keaton worth remembering. Empty if none.",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "One sentence, stated as a fact about Keaton, not about today.",
                    },
                    "kind": {"type": "string", "enum": FACT_KINDS},
                },
                "required": ["text", "kind"],
                "additionalProperties": False,
            },
        },
        "tasks": {
            "type": "array",
            "description": "Things with an action attached. Empty if none.",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short imperative title, no date words."},
                    "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD, or null."},
                    "category": {"type": "string"},
                },
                "required": ["title", "due_date", "category"],
                "additionalProperties": False,
            },
        },
        "note": {
            "type": "string",
            "description": "One line on what was filed and why. Empty string if nothing was.",
        },
    },
    "required": ["facts", "tasks", "note"],
    "additionalProperties": False,
}

_ANALYSE_SYSTEM = """Keaton has dumped what happened. Work out whether anything
needs clarifying before it can be filed.

Ask AT MOST TWO questions, and only where the answer changes what gets filed --
whether something becomes a dated task or a standing fact, which of two things
he meant, whether a problem is recurring or a one-off.

Asking nothing is the best outcome and is common. If the dump is clear, return
an empty questions list. Questions that merely show interest ("how did that
make you feel?") are noise here; this is filing, not therapy.

Do not ask about anything you could reasonably infer. Do not ask two questions
that resolve the same ambiguity.

The summary reflects the dump back in one or two sentences so he can see what
you understood. Do not editorialize or encourage."""

_FILE_SYSTEM = """File a debrief into long-term memory and the task list.

FACTS are durable things about Keaton: how he works, what he prefers, what he
struggles with, standing constraints. Write them as facts about HIM, not about
today -- "loses focus in long afternoon labs", not "the lab ran long today".
A fact that is only true of one day is not a fact, it is a diary entry, and
does not belong in memory.

TASKS are things with an action attached. Give a real due date only where one
was actually stated or is genuinely implied; inventing dates is worse than
leaving them null.

Be conservative. Filing nothing is a valid and common outcome -- most days
contain no durable fact. One good fact beats four restatements of the same
observation. Never file a fact that merely restates a task.

Use only the categories given. The note is one line on what you filed, written
plainly."""


def _context(dump: str, answers: Optional[List[Dict]] = None) -> str:
    parts = [f"Today is {date.today().isoformat()}.", "", "WHAT KEATON WROTE:", dump.strip()]
    if answers:
        parts += ["", "HIS ANSWERS:"]
        for item in answers:
            parts.append(f"  Q: {item['question']}")
            parts.append(f"  A: {item['answer']}")
    return "\n".join(parts)


async def analyse(dump: str) -> Optional[Dict[str, Any]]:
    """Read the dump and return {questions, summary}, or None on failure.

    Questions are truncated to MAX_QUESTIONS here as well as in the
    prompt -- a cap enforced only by instruction is a cap the model can
    talk itself out of on a long dump.
    """
    dump = (dump or "").strip()
    if not dump:
        return None

    result = await llm_client.ask_claude_json(
        prompt=_context(dump),
        schema=_ANALYSE_SCHEMA,
        system=_ANALYSE_SYSTEM,
        model=_MODEL,
        max_tokens=2048,
        purpose="debrief-analyse",
    )
    if result is None:
        return None
    result["questions"] = (result.get("questions") or [])[:MAX_QUESTIONS]
    return result


async def propose(dump: str, answers: Optional[List[Dict]] = None,
                  categories: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Work out what to file. Returns {facts, tasks, note} WITHOUT writing
    anything -- see the module docstring on showing before filing."""
    dump = (dump or "").strip()
    if not dump:
        return None

    from sunny_code.components import category_store

    categories = categories or category_store.get_categories()
    schema = {
        **_FILE_SCHEMA,
        "properties": {
            **_FILE_SCHEMA["properties"],
            "tasks": {
                **_FILE_SCHEMA["properties"]["tasks"],
                "items": {
                    **_FILE_SCHEMA["properties"]["tasks"]["items"],
                    "properties": {
                        **_FILE_SCHEMA["properties"]["tasks"]["items"]["properties"],
                        # Same reasoning as extract.py: an enum makes an
                        # off-list category impossible to generate rather
                        # than something to catch afterwards.
                        "category": {"type": "string", "enum": categories},
                    },
                },
            },
        },
    }

    return await llm_client.ask_claude_json(
        prompt=_context(dump, answers),
        schema=schema,
        system=_FILE_SYSTEM,
        model=_MODEL,
        max_tokens=4096,
        purpose="debrief-file",
    )


def commit(proposal: Dict[str, Any], tasks_db=None, source: str = "debrief") -> Dict[str, Any]:
    """Write a proposal to memory and the task list.

    Returns what was actually written, not what was proposed. The two can
    differ -- memory_store.remember() rejects junk, and a task can fail
    validation -- and reporting the proposal as though it were the result
    would be the one lie this flow cannot afford.
    """
    from sunny_code.components import memory_store

    written_facts, written_tasks = [], []

    for fact in proposal.get("facts") or []:
        text = (fact.get("text") or "").strip()
        if not text:
            continue
        fact_id = memory_store.remember(text, kind=fact.get("kind", "fact"), source=source)
        if fact_id:
            written_facts.append({"id": fact_id, "text": text, "kind": fact.get("kind", "fact")})

    if tasks_db is not None:
        for task in proposal.get("tasks") or []:
            title = (task.get("title") or "").strip()
            if not title:
                continue
            try:
                task_id = tasks_db.create_task(
                    title=title,
                    tag=task.get("category") or "General",
                    due_date=task.get("due_date"),
                    source=source,
                )
                written_tasks.append({"id": task_id, "title": title,
                                      "due_date": task.get("due_date")})
            except ValueError as e:
                logger.warning(f"debrief: task {title!r} rejected: {e}")

    return {"facts": written_facts, "tasks": written_tasks}


def format_proposal(proposal: Dict[str, Any]) -> str:
    """The proposal as text, for showing before filing."""
    lines = []
    facts = proposal.get("facts") or []
    tasks = proposal.get("tasks") or []

    if facts:
        lines.append("**Remembering**")
        for fact in facts:
            lines.append(f"  · {fact['text']}  _{fact['kind']}_")
    if tasks:
        if lines:
            lines.append("")
        lines.append("**Tasks**")
        for task in tasks:
            due = f"  — due {task['due_date']}" if task.get("due_date") else ""
            lines.append(f"  · {task['title']}{due}")

    if not lines:
        # Explicitly worth saying. Silence here reads as a failure, when
        # it is usually the correct outcome.
        return "Nothing worth filing from that — no durable facts, no actions."
    return "\n".join(lines)
