"""Integration tests – Thread List flow.

Validates that the threads.list operation returns previously created
threads from the store (CosmosDB or SQLite fallback), and that thread
listing is isolated per user_id.
"""

import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from conftest import parse_sse_events


class TestChatkitThreadList:
    """Flow – List threads.

    Creates a thread, then calls threads.list and verifies the newly
    created thread appears in the response.
    """

    @pytest.mark.asyncio
    async def test_thread_list_returns_created_thread(self, client: AsyncClient) -> None:
        """Create a thread, then list threads and verify it appears."""

        # ── Step 1: Create a thread so there is at least one ─────────
        create_body = {
            "type": "threads.create",
            "params": {
                "input": {
                    "content": [{"type": "input_text", "text": "hello, what is my account balance?"}],
                    "attachments": [],
                    "quoted_text": "",
                    "inference_options": {},
                },
            },
        }

        create_response = await client.post("/chatkit", json=create_body, timeout=120)
        assert create_response.status_code == 200

        events = parse_sse_events(create_response.text)
        assert len(events) > 0, "Should receive at least one SSE event"

        # Extract the thread id from thread.created
        thread_created = events[0]
        assert thread_created["type"] == "thread.created"
        created_thread_id = thread_created["thread"]["id"]
        assert created_thread_id, "thread.created must include a thread id"

        print(f"\n--- Created thread: {created_thread_id} ---")

        # ── Step 2: List threads ─────────────────────────────────────
        list_body = {
            "type": "threads.list",
            "params": {"limit": 9999, "order": "desc"},
        }

        list_response = await client.post("/chatkit", json=list_body, timeout=30)
        assert list_response.status_code == 200

        # threads.list returns JSON (non-streaming)
        data = list_response.json()
        print(f"\n--- threads.list response ---\n{json.dumps(data, indent=2, default=str)[:2000]}")

        # Validate response structure
        assert "data" in data, "Response should contain a 'data' key with thread list"
        threads = data["data"]
        assert isinstance(threads, list), "'data' should be a list of threads"
        assert len(threads) >= 1, "Should have at least one thread after creation"

        # Verify the created thread is in the list
        thread_ids = [t["id"] for t in threads]
        assert created_thread_id in thread_ids, (
            f"Created thread {created_thread_id} should appear in threads.list, "
            f"got: {thread_ids}"
        )

        # Verify thread structure
        matching = [t for t in threads if t["id"] == created_thread_id][0]
        assert "title" in matching or "metadata" in matching or "id" in matching, (
            "Thread object should have expected fields"
        )
        print(f"\n--- Found thread in list: {json.dumps(matching, indent=2, default=str)[:500]}")

    @pytest.mark.asyncio
    async def test_thread_list_isolated_by_user(self, client: AsyncClient) -> None:
        """Threads created by one user must not appear for a different user."""

        # ── Step 1: Create a thread as the default user (bob-user-123) ──
        create_body = {
            "type": "threads.create",
            "params": {
                "input": {
                    "content": [{"type": "input_text", "text": "isolation test — what cards do I have?"}],
                    "attachments": [],
                    "quoted_text": "",
                    "inference_options": {},
                },
            },
        }

        create_response = await client.post("/chatkit", json=create_body, timeout=120)
        assert create_response.status_code == 200

        events = parse_sse_events(create_response.text)
        thread_created = events[0]
        assert thread_created["type"] == "thread.created"
        created_thread_id = thread_created["thread"]["id"]

        print(f"\n--- Created thread as bob-user-123: {created_thread_id} ---")

        # Confirm the thread appears for bob-user-123
        list_body = {"type": "threads.list", "params": {"limit": 9999, "order": "desc"}}

        list_response = await client.post("/chatkit", json=list_body, timeout=30)
        assert list_response.status_code == 200
        demo_threads = list_response.json()["data"]
        demo_thread_ids = [t["id"] for t in demo_threads]
        assert created_thread_id in demo_thread_ids, "Thread should be visible for bob-user-123"

        # ── Step 2: List threads as a completely different user ───────
        with patch(
            "app.routers.chatkit.chat_routers.UserProfileHelper.get_user_id",
            return_value="other_test_user",
        ):
            other_response = await client.post("/chatkit", json=list_body, timeout=30)

        assert other_response.status_code == 200
        other_threads = other_response.json()["data"]
        other_thread_ids = [t["id"] for t in other_threads]

        print(f"\n--- other_test_user sees {len(other_threads)} thread(s): {other_thread_ids} ---")

        assert created_thread_id not in other_thread_ids, (
            f"Thread {created_thread_id} belongs to bob-user-123 and must NOT "
            f"appear in other_test_user's thread list"
        )
