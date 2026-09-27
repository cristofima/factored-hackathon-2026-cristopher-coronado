"""Integration tests – New Thread flow.

Validates the full SSE event sequence for creating a new thread
and processing the first user message through the multi-agent banking assistant.
"""

import json

import pytest
from httpx import AsyncClient

from conftest import get_events_by_type, parse_sse_events


class TestChatkitNewThreadFlow:
    """Flow 1 – New Thread first user message.

    Validates the full SSE event sequence:
    1. thread.created
    2. thread.item.done  (echoes the user message)
    3. progress_update(s)
    4. thread.item.added  (tasks: handoff, tool calls, assistant message)
    5. thread.item.updated (text streaming deltas)
    6. thread.item.done  (final assistant message)
    """


    @pytest.mark.asyncio
    async def test_new_thread_event_flow(self, client: AsyncClient) -> None:
        """Validate the full SSE event sequence for a new thread asking about Contoso payments."""
        request_body = {
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

        response = await client.post("/chatkit", json=request_body, timeout=120)
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        assert len(events) > 0, "Should receive at least one SSE event"

        event_types = [e.get("type") for e in events]
        print(f"\n--- Received {len(events)} SSE events ---")
        for i, evt in enumerate(events):
            evt_type = evt.get("type", "?")
            preview = json.dumps(evt, default=str)[:200]
            print(f"  [{i}] {evt_type}: {preview}")

        # 1) First event must be thread.created
        assert event_types[0] == "thread.created", (
            f"First event should be 'thread.created', got '{event_types[0]}'"
        )
        thread_created = events[0]
        thread_id = thread_created["thread"]["id"]
        assert thread_id, "thread.created must include a thread id"

        # 2) Second event must be thread.item.done echoing the user message
        assert event_types[1] == "thread.item.done", (
            f"Second event should be 'thread.item.done' (user message), got '{event_types[1]}'"
        )
        user_message_event = events[1]
        assert user_message_event["item"]["type"] == "user_message"
        user_text = user_message_event["item"]["content"][0]["text"]
        assert "contoso" in user_text.lower(), "User message should contain the query"

        # 3) At least one progress_update must appear
        progress_events = get_events_by_type(events, "progress_update")
        assert len(progress_events) >= 1, "Expected at least one progress_update event"

        # 4) task events (thread.item.added with type=task) should appear
        task_added_events = [
            e for e in events
            if e.get("type") == "thread.item.added"
            and e.get("item", {}).get("type") == "task"
        ]
        assert len(task_added_events) >= 1, "Expected at least one task event from tool calls"

        # Verify we see agent handoff and tool-call tasks
        task_titles = [
            e["item"].get("task", {}).get("title", "")
            for e in task_added_events
            if "task" in e.get("item", {})
        ]
        print(f"\n--- Task titles ---")
        for t in task_titles:
            print(f"  • {t}")

        # Should see a handoff to TransactionHistoryAgent (or similar)
        # Title may be absent depending on model/prompt variability
        if any(t for t in task_titles):
            has_handoff = any("Connected to" in t for t in task_titles)
            assert has_handoff, (
                f"Expected a 'Connected to ...' handoff task, got: {task_titles}"
            )

            # Should see account lookup tool call
            has_account_lookup = any(
                "account" in t.lower() or "retrieved" in t.lower()
                for t in task_titles
            )
            assert has_account_lookup, (
                f"Expected an account lookup task, got: {task_titles}"
            )

        # 5) Assistant message events
        assistant_added_events = [
            e for e in events
            if e.get("type") == "thread.item.added"
            and e.get("item", {}).get("type") == "assistant_message"
        ]
        assert len(assistant_added_events) >= 1, "Expected at least one assistant_message added event"

        # Text streaming deltas
        text_delta_events = get_events_by_type(events, "thread.item.updated")
        assert len(text_delta_events) >= 1, "Expected text streaming delta events"
        # Check delta structure
        first_delta = text_delta_events[0]
        assert "update" in first_delta
        assert first_delta["update"]["type"] == "assistant_message.content_part.text_delta"
        assert "delta" in first_delta["update"]

        # 6) Final thread.item.done for the assistant message
        done_events = get_events_by_type(events, "thread.item.done")
        assistant_done_events = [
            e for e in done_events
            if e.get("item", {}).get("type") == "assistant_message"
        ]
        assert len(assistant_done_events) >= 1, "Expected a final thread.item.done for assistant_message"

        final_message = assistant_done_events[-1]
        final_text = final_message["item"]["content"][0]["text"]
        print(f"\n--- Final assistant response (first 500 chars) ---\n{final_text[:500]}")

        # The assistant should mention Contoso in its response
        assert "contoso" in final_text.lower(), (
            "Assistant response should mention 'Contoso' since we asked about Contoso payments"
        )
