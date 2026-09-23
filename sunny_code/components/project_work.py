"""Planning, red-teaming and research over a project.

THE CRITIQUE STEP IS THE POINT
------------------------------
Most planning tools go idea -> plan -> do. The failure mode of that shape
is that the first plan is the one you execute, and the first plan is
written while you are still enthusiastic about the idea. The phase list
in project_store puts `critique` between `planning` and `refined`
precisely so the plan gets attacked once, deliberately, while changing it
is still cheap.

critique() is adversarial ON PURPOSE. It is prompted to find what breaks,
not to summarize or encourage, and every risk it raises must come with a
concrete fix -- a critique that only lists problems moves work onto the
person instead of off them, and gets ignored after the second time.

WHY STRUCTURED OUTPUT FOR CRITIQUE, PROSE FOR RESEARCH
------------------------------------------------------
A critique has to be sortable: severity decides what gets addressed
before building starts, so it comes back as typed JSON and is rendered
into markdown here. Research is genuinely prose -- a comparison's value
is in the reasoning, and forcing it into fields would flatten exactly the
part worth reading. Research also needs web search, which pairs badly
with a constrained output format.

Everything writes into the project folder, so the output is a file you
can edit in Obsidian rather than a chat message that scrolls away.
"""

import logging
from datetime import date
from typing import Dict, List, Optional

from sunny_code.components import llm_client, project_store

logger = logging.getLogger(__name__)

_MODEL = "sonnet"

SEVERITIES = ["high", "medium", "low"]

_CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "description": "One or two sentences: is this plan sound, and what is the single biggest problem?",
        },
        "risks": {
            "type": "array",
            "description": "Ways this plan fails or turns out suboptimal. Most severe first.",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short name for the risk."},
                    "severity": {"type": "string", "enum": SEVERITIES},
                    "failure_mode": {
                        "type": "string",
                        "description": "Concretely, what goes wrong and when it would be noticed.",
                    },
                    "fix": {
                        "type": "string",
                        "description": "A specific change to the plan that addresses it. Never 'be careful'.",
                    },
                },
                "required": ["title", "severity", "failure_mode", "fix"],
                "additionalProperties": False,
            },
        },
        "weak_assumptions": {
            "type": "array",
            "description": "Things the plan takes for granted that may not hold.",
            "items": {"type": "string"},
        },
        "better_alternatives": {
            "type": "array",
            "description": "Places a different approach would plainly be better.",
            "items": {
                "type": "object",
                "properties": {
                    "instead_of": {"type": "string"},
                    "proposal": {"type": "string"},
                    "why_better": {"type": "string"},
                },
                "required": ["instead_of", "proposal", "why_better"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "risks", "weak_assumptions", "better_alternatives"],
    "additionalProperties": False,
}

_CRITIQUE_SYSTEM = """You are red-teaming a plan. Your job is to find what will go
wrong with it, not to improve morale.

Rules:
- Attack the plan, never the person. The target is the reasoning.
- Every risk needs a CONCRETE failure mode: what breaks, under what conditions,
  and when it would first be noticed. "This might not scale" is not a finding.
- Every risk needs a SPECIFIC fix. "Be careful" and "monitor closely" are not
  fixes. A fix changes the plan.
- Rank honestly. If the plan is mostly sound, say so in the verdict and return
  few risks. Inventing high-severity problems to seem thorough is the failure
  mode of this exercise, and it trains the reader to ignore you.
- Prefer the risk that is boring and likely over the one that is dramatic and
  rare.
- Where a different approach is plainly better, say so plainly, and say what it
  costs as well as what it buys.
- Judge the plan on its own goals. Do not substitute goals it never had."""

_PLAN_SYSTEM = """You draft a first plan for a project. It will be attacked in a
separate critique step immediately afterwards, so aim for clear and concrete
rather than defensively hedged -- vagueness hides from criticism, which defeats
the point.

Produce markdown with:
- A one-paragraph statement of what "done" means. If that cannot be stated, say
  so; a project without a definition of done is the finding.
- Milestones in order. Each with a name, what it produces, and a rough size
  (hours / days / weeks). Use real dates only where the project has real
  deadlines; invented dates are worse than none.
- What has to be true for this to work (dependencies, access, other people).
- What is deliberately NOT in scope.

Be specific enough to be wrong. No filler sections."""

_RESEARCH_SYSTEM = """You research a question for a project and come back with a
comparison, not a summary.

Search the web where current facts matter -- prices, versions, what a tool
actually supports today. Say when you are working from general knowledge rather
than something you looked up.

Produce markdown:
- The question, restated precisely as you interpreted it.
- Each real option: what it is, what it is good at, where it falls down. Include
  the option the reader did not ask about if it is genuinely a contender.
- A comparison of the tradeoffs that actually differ. Skip dimensions where the
  options are the same; they pad the page and hide the real decision.
- A recommendation, with the reason, and the specific condition under which you
  would pick differently.

Do not present every option as equally good. Picking is the job."""


def _context_for(slug: str) -> Optional[str]:
    project = project_store.get(slug)
    if project is None:
        return None
    parts = [project_store.context(slug)]
    custom = project_store.instructions(slug)
    if custom:
        parts.append(f"PROJECT INSTRUCTIONS (follow these):\n{custom}\n")
    return "\n".join(parts)


async def draft_plan(slug: str, notes: str = "") -> Optional[str]:
    """Write plan.md from the project's description and any notes.

    Advances the phase to `planning`. Returns the markdown, or None.
    """
    context = _context_for(slug)
    if context is None:
        return None

    prompt = f"{context}\n"
    if notes.strip():
        prompt += f"ADDITIONAL NOTES FROM KEATON:\n{notes.strip()}\n\n"
    prompt += "Draft the first plan for this project."

    plan = await llm_client.ask_claude(
        prompt=prompt, system=_PLAN_SYSTEM, model=_MODEL,
        max_tokens=4096, purpose="project-plan",
    )
    if not plan:
        return None

    body = (f"---\ntype: plan\nproject: {slug}\ndrafted: {date.today().isoformat()}\n---\n\n"
            f"# Plan\n\n{plan.strip()}\n")
    project_store.write_file(slug, project_store.PLAN_FILE, body)
    project_store.update(slug, phase=project_store.PLANNING)
    return plan


def _render_critique(result: Dict, slug: str) -> str:
    """Critique JSON as a markdown file worth reading in Obsidian."""
    lines = [
        f"---\ntype: critique\nproject: {slug}\nrun: {date.today().isoformat()}\n---",
        "",
        "# Critique",
        "",
        f"**Verdict.** {result.get('verdict', '').strip()}",
        "",
    ]

    risks = result.get("risks") or []
    if risks:
        order = {s: i for i, s in enumerate(SEVERITIES)}
        risks = sorted(risks, key=lambda r: order.get(r.get("severity"), 9))
        lines += ["## Risks", ""]
        for risk in risks:
            severity = str(risk.get("severity", "")).upper()
            lines += [
                f"### {risk.get('title', 'Untitled')}  ·  {severity}",
                "",
                f"**How it fails.** {risk.get('failure_mode', '').strip()}",
                "",
                f"**Fix.** {risk.get('fix', '').strip()}",
                "",
            ]

    assumptions = [a for a in (result.get("weak_assumptions") or []) if a.strip()]
    if assumptions:
        lines += ["## Assumptions worth checking", ""]
        lines += [f"- {a.strip()}" for a in assumptions]
        lines += [""]

    alternatives = result.get("better_alternatives") or []
    if alternatives:
        lines += ["## Where something else would be better", ""]
        for alt in alternatives:
            lines += [
                f"**Instead of** {alt.get('instead_of', '').strip()}",
                "",
                f"{alt.get('proposal', '').strip()}",
                "",
                f"*Why.* {alt.get('why_better', '').strip()}",
                "",
            ]

    if not risks and not assumptions and not alternatives:
        lines += ["_Nothing substantial found. Treat that with suspicion "
                  "if the plan is large._", ""]

    return "\n".join(lines)


async def critique(slug: str) -> Optional[Dict]:
    """Attack the project's plan. Writes critique.md, advances the phase.

    Returns the structured result, or None if there was no plan to attack
    -- critiquing a project with no plan produces generic advice, which
    is the thing this step exists to avoid.
    """
    context = _context_for(slug)
    if context is None:
        return None

    plan = project_store.read_file(slug, project_store.PLAN_FILE)
    if not plan or not plan.strip():
        logger.info(f"critique({slug}): no plan to attack yet")
        return None

    result = await llm_client.ask_claude_json(
        prompt=f"{context}\nAttack this project's plan.",
        schema=_CRITIQUE_SCHEMA,
        system=_CRITIQUE_SYSTEM,
        model=_MODEL,
        # A real critique is several risks, each with a concrete failure
        # mode and a concrete fix. 4096 truncated it mid-JSON on the very
        # first live run against a project of ordinary size, and truncated
        # JSON is a total loss rather than a short answer -- there is no
        # partial credit, so this is sized for the worst case.
        max_tokens=16000,
        purpose="project-critique",
    )
    if result is None:
        return None

    project_store.write_file(slug, project_store.CRITIQUE_FILE,
                             _render_critique(result, slug))
    project_store.update(slug, phase=project_store.CRITIQUE)
    return result


async def research(slug: str, question: str) -> Optional[str]:
    """Research a question in the project's context and file the result.

    Saved under research/ with a dated slug rather than one rolling file,
    so an earlier comparison stays readable after the decision changes --
    the reasoning behind a choice is most useful exactly when you are
    reconsidering it.
    """
    context = _context_for(slug)
    if context is None:
        return None
    question = (question or "").strip()
    if not question:
        return None

    answer = await llm_client.ask_claude(
        prompt=f"{context}\nResearch question: {question}",
        system=_RESEARCH_SYSTEM,
        model=_MODEL,
        max_tokens=6144,
        purpose="project-research",
        enable_web_search=True,
    )
    if not answer:
        return None

    from sunny_code.components import vault_io
    stem = vault_io.slugify(question)[:50] or "research"
    filename = f"research/{date.today().isoformat()}-{stem}.md"
    body = (f"---\ntype: research\nproject: {slug}\n"
            f"question: {question!r}\nrun: {date.today().isoformat()}\n---\n\n"
            f"# {question}\n\n{answer.strip()}\n")
    project_store.write_file(slug, filename, body)
    return answer


def critique_summary(slug: str) -> Optional[str]:
    """The headline from the last critique, for a brief or a list."""
    text = project_store.read_file(slug, project_store.CRITIQUE_FILE)
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("**Verdict.**"):
            return line.replace("**Verdict.**", "").strip()
    return None
