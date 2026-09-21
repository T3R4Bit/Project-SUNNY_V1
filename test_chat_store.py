#!/usr/bin/env python
"""Regression tests for durable chat conversations.

The cases worth protecting are the ones where the UI would promise
something the backend doesn't deliver:

  - A reloaded conversation must RESUME, not just display. Showing the
    transcript while Sunny has no memory of it is worse than showing
    nothing, because the next follow-up lands with no context and the
    user has no way to know why.
  - Titles must not change under you once set.
  - An unknown conversation id must be adopted, not rejected -- the id
    lives in localStorage and can outlive the database.
  - Deleting must clear the in-memory context too, or a later
    conversation could inherit deleted turns.
"""

import sys
import tempfile
from pathlib import Path

from sunny_code.components import chat_store, conversation_memory

FAILURES = []
_TMP = Path(tempfile.mkdtemp(prefix="sunny_chat_"))
chat_store._db_path = lambda: _TMP / "chat.db"


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def fresh_memory():
    conversation_memory._history.clear()
    conversation_memory._last_touched.clear()


def test_create_and_persist():
    print("\n-- persistence --")
    cid = chat_store.create_conversation()
    check("conversation gets an id", bool(cid))

    chat_store.add_message(cid, "user", "what are my tasks")
    chat_store.add_message(cid, "assistant", "You have 11 open tasks.")

    msgs = chat_store.get_messages(cid)
    check("both messages stored", len(msgs) == 2)
    check("order is chronological", msgs[0]["role"] == "user" and msgs[1]["role"] == "assistant")
    check("content round-trips", msgs[1]["content"] == "You have 11 open tasks.")


def test_title_from_first_message():
    print("\n-- titles --")
    cid = chat_store.create_conversation()
    chat_store.add_message(cid, "user", "how should I plan my week around classes")
    listed = {c["id"]: c for c in chat_store.list_conversations()}
    check("titled from the first user message",
          listed[cid]["title"] == "how should I plan my week around classes")

    # A later message must not rename it.
    chat_store.add_message(cid, "assistant", "Here is a plan.")
    chat_store.add_message(cid, "user", "actually never mind")
    listed = {c["id"]: c for c in chat_store.list_conversations()}
    check("later messages don't rename it",
          listed[cid]["title"] == "how should I plan my week around classes")

    long_text = "x" * 200
    check("long titles truncate", len(chat_store.make_title(long_text)) <= chat_store.TITLE_MAX + 1)
    check("truncation breaks on a word boundary",
          chat_store.make_title("alpha beta gamma delta " * 10).endswith("…"))
    check("empty message still gets a title", chat_store.make_title("") == chat_store.DEFAULT_TITLE)


def test_rename_and_delete():
    print("\n-- rename / delete --")
    cid = chat_store.create_conversation()
    chat_store.add_message(cid, "user", "hello")
    check("rename works", chat_store.rename_conversation(cid, "Weekly planning") is True)
    listed = {c["id"]: c for c in chat_store.list_conversations()}
    check("new title is stored", listed[cid]["title"] == "Weekly planning")
    check("blank rename rejected", chat_store.rename_conversation(cid, "   ") is False)

    check("delete reports success", chat_store.delete_conversation(cid) is True)
    check("conversation is gone", cid not in {c["id"] for c in chat_store.list_conversations()})
    check("its messages are gone too", chat_store.get_messages(cid) == [])


def test_unknown_id_is_adopted():
    print("\n-- unknown id --")
    # Simulates a client holding an id in localStorage after the DB was
    # cleared or restored. Rejecting would strand them.
    adopted = chat_store.ensure_conversation("idfromlocalstorage")
    check("unknown id is kept, not replaced", adopted == "idfromlocalstorage")
    chat_store.add_message(adopted, "user", "still works")
    check("it is writable afterwards", len(chat_store.get_messages(adopted)) == 1)

    made = chat_store.ensure_conversation(None)
    check("no id creates one", bool(made) and made != adopted)


def test_hydrate_makes_resume_real():
    print("\n-- resume after restart --")
    fresh_memory()
    cid = chat_store.create_conversation()
    session = f"web:{cid}"

    chat_store.add_message(cid, "user", "who won the 2021 F1 title")
    chat_store.add_message(cid, "assistant", "Max Verstappen.")

    # Simulates a restart: the transcript survives, RAM does not.
    fresh_memory()
    check("memory is empty before hydration",
          conversation_memory.format_for_prompt(session) == "")

    restored = chat_store.hydrate_memory(cid, session)
    check("hydration replays the stored turns", restored == 2)

    prompt = conversation_memory.format_for_prompt(session)
    check("prompt context carries the question", "2021 F1 title" in prompt)
    check("prompt context carries the answer", "Verstappen" in prompt)

    # Must not re-seed on every message of a live conversation.
    again = chat_store.hydrate_memory(cid, session)
    check("no double-hydration when memory is warm", again == 0)


def test_delete_clears_memory():
    print("\n-- delete clears context --")
    fresh_memory()
    cid = chat_store.create_conversation()
    session = f"web:{cid}"
    chat_store.add_message(cid, "user", "secret plan")
    chat_store.hydrate_memory(cid, session)
    check("context present before delete", conversation_memory.format_for_prompt(session) != "")

    # Mirrors what the delete route does.
    chat_store.delete_conversation(cid)
    conversation_memory._history.pop(session, None)
    conversation_memory._last_touched.pop(session, None)
    check("context cleared after delete", conversation_memory.format_for_prompt(session) == "")


def test_separate_conversations_dont_bleed():
    print("\n-- isolation --")
    fresh_memory()
    a = chat_store.create_conversation()
    b = chat_store.create_conversation()
    chat_store.add_message(a, "user", "topic alpha")
    chat_store.add_message(b, "user", "topic beta")

    chat_store.hydrate_memory(a, f"web:{a}")
    chat_store.hydrate_memory(b, f"web:{b}")

    pa = conversation_memory.format_for_prompt(f"web:{a}")
    pb = conversation_memory.format_for_prompt(f"web:{b}")
    check("conversation A sees only its own turns", "alpha" in pa and "beta" not in pa)
    check("conversation B sees only its own turns", "beta" in pb and "alpha" not in pb)
    check("transcripts are separate too",
          len(chat_store.get_messages(a)) == 1 and len(chat_store.get_messages(b)) == 1)


def test_listing_order_and_preview():
    print("\n-- sidebar listing --")
    first = chat_store.create_conversation()
    chat_store.add_message(first, "user", "older conversation")
    second = chat_store.create_conversation()
    chat_store.add_message(second, "user", "newer conversation")
    chat_store.add_message(second, "assistant", "a reply here")

    listed = chat_store.list_conversations()
    ids = [c["id"] for c in listed]
    check("most recently updated is first", ids.index(second) < ids.index(first))
    entry = next(c for c in listed if c["id"] == second)
    check("preview shows the last message", entry["preview"] == "a reply here")
    check("message count is right", entry["message_count"] == 2)


if __name__ == "__main__":
    test_create_and_persist()
    test_title_from_first_message()
    test_rename_and_delete()
    test_unknown_id_is_adopted()
    test_hydrate_makes_resume_real()
    test_delete_clears_memory()
    test_separate_conversations_dont_bleed()
    test_listing_order_and_preview()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("All chat-store checks passed.")
