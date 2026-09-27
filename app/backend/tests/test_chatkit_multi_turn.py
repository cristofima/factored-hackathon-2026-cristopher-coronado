"""Integration tests – Multi-turn conversation flow.

Validates that follow-up messages within the same thread preserve
conversation context across turns.
"""

import json

import pytest
from httpx import AsyncClient

from conftest import get_events_by_type, parse_sse_events


class TestChatkitMultiTurnConversation:
    """Flow 2 – Multi-turn conversation within the same thread.

    Validates that a follow-up message (threads.add_user_message) on an
    existing thread preserves conversation context:
    1. First message creates the thread and asks about Contoso payments.
    2. Second message says "what about ACME" and the agent should
       understand the user still means *transactions* related to ACME.
    """

    @pytest.mark.asyncio
    async def test_follow_up_message_preserves_context(self, client: AsyncClient) -> None:
        """Send two messages in the same thread and verify the agent keeps context."""

        # ── Turn 1: create thread with initial question ──────────────
        create_body = {
            "type": "threads.create",
            "params": {
                "input": {
                    "content": [{"type": "input_text", "text": "when was last time I paid contoso?"}],
                    "attachments": [],
                    "quoted_text": "",
                    "inference_options": {},
                },
            },
        }

        turn1_response = await client.post("/chatkit", json=create_body, timeout=120)
        assert turn1_response.status_code == 200

        turn1_events = parse_sse_events(turn1_response.text)
        assert len(turn1_events) > 0, "Turn 1 should produce SSE events"

        # Extract thread_id from thread.created
        thread_created = turn1_events[0]
        assert thread_created.get("type") == "thread.created"
        thread_id = thread_created["thread"]["id"]
        assert thread_id, "thread.created must include a thread id"

        print(f"\n--- Turn 1: thread created {thread_id}, {len(turn1_events)} events ---")

        # ── Turn 2: follow-up in same thread ─────────────────────────
        follow_up_body = {
            "type": "threads.add_user_message",
            "params": {
                "input": {
                    "content": [{"type": "input_text", "text": "what about ACME"}],
                    "attachments": [],
                    "quoted_text": "",
                    "inference_options": {},
                },
                "thread_id": thread_id,
            },
        }

        turn2_response = await client.post("/chatkit", json=follow_up_body, timeout=120)
        assert turn2_response.status_code == 200

        turn2_events = parse_sse_events(turn2_response.text)
        assert len(turn2_events) > 0, "Turn 2 should produce SSE events"

        turn2_types = [e.get("type") for e in turn2_events]
        print(f"\n--- Turn 2: {len(turn2_events)} SSE events ---")
        for i, evt in enumerate(turn2_events):
            evt_type = evt.get("type", "?")
            preview = json.dumps(evt, default=str)[:200]
            print(f"  [{i}] {evt_type}: {preview}")

        # Turn 2 should NOT have thread.created (thread already exists)
        assert "thread.created" not in turn2_types, (
            "Follow-up message should not create a new thread"
        )

        # First event should echo the user message
        assert turn2_types[0] == "thread.item.done", (
            f"First turn-2 event should be 'thread.item.done' (user message), got '{turn2_types[0]}'"
        )
        user_msg = turn2_events[0]
        assert user_msg["item"]["type"] == "user_message"
        assert user_msg["item"]["thread_id"] == thread_id, "User message must be on the same thread"
        assert "acme" in user_msg["item"]["content"][0]["text"].lower()

        # Should have progress updates
        progress_events = get_events_by_type(turn2_events, "progress_update")
        assert len(progress_events) >= 1, "Expected at least one progress_update in turn 2"

        # Should have task events (tool calls for ACME lookup)
        task_events = [
            e for e in turn2_events
            if e.get("type") == "thread.item.added"
            and e.get("item", {}).get("type") == "task"
        ]
        assert len(task_events) >= 1, "Expected at least one task event in turn 2"

        # Should have an assistant message
        assistant_done_events = [
            e for e in get_events_by_type(turn2_events, "thread.item.done")
            if e.get("item", {}).get("type") == "assistant_message"
        ]
        assert len(assistant_done_events) >= 1, "Expected a final assistant_message in turn 2"

        final_text = assistant_done_events[-1]["item"]["content"][0]["text"]
        print(f"\n--- Turn 2 final response (first 500 chars) ---\n{final_text[:500]}")

        # The agent should understand "what about ACME" means transactions for ACME
        assert "acme" in final_text.lower(), (
            "Assistant response should mention 'ACME' — the agent must carry forward "
            "the transaction inquiry context from turn 1"
        )
