"""Integration tests – Payment with human-in-the-loop approval flow.

Validates the multi-turn payment flow including tool_approval_request
widget emission and user approval via threads.custom_action.
"""

import json

import pytest
from httpx import AsyncClient

from conftest import get_events_by_type, parse_sse_events


class TestChatkitPaymentFlow:
    """Flow 3 – Multi-turn payment with human-in-the-loop approval.

    Canonical flow:
    1. User requests to pay a bill (amount, payee, invoice id, date).
    2. Server checks bill hasn't been paid, asks for payment method.
    3. User selects rechargeable visa card.
    4. Server validates card funds, asks confirmation → may emit client_widget
       (tool_approval_request) directly after method selection.
    5. If the agent asks for textual confirmation first, user says "proceed".
    6. Server emits client_widget (tool_approval_request) for processPayment.
    7. User approves via threads.custom_action.
    8. Server confirms payment was processed.

    The LLM may compress steps 2-4 so the test is flexible about when the
    approval widget appears.
    """

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _send_message(thread_id: str, text: str) -> dict:
        """Build a threads.add_user_message request body."""
        return {
            "type": "threads.add_user_message",
            "params": {
                "input": {
                    "content": [{"type": "input_text", "text": text}],
                    "attachments": [],
                    "quoted_text": "",
                    "inference_options": {},
                },
                "thread_id": thread_id,
            },
        }

    @staticmethod
    def _find_approval_widget(events: list[dict]) -> dict | None:
        """Return the first client_widget / tool_approval_request event, or None."""
        for e in events:
            if (
                e.get("type") == "thread.item.done"
                and e.get("item", {}).get("type") == "client_widget"
                and e.get("item", {}).get("name") == "tool_approval_request"
            ):
                return e
        return None

    @staticmethod
    def _build_approval_action(widget_event: dict, thread_id: str) -> dict:
        """Build a threads.custom_action approval request from a widget event."""
        item = widget_event["item"]
        args = item["args"]
        return {
            "type": "threads.custom_action",
            "params": {
                "item_id": item["id"],
                "action": {
                    "type": "approval",
                    "payload": {
                        "tool_name": args["tool_name"],
                        "tool_args": args["tool_args"],
                        "approved": True,
                        "call_id": args["call_id"],
                        "request_id": args.get("request_id"),
                    },
                    "handler": "server",
                    "loadingBehavior": "auto",
                },
                "thread_id": thread_id,
            },
        }

    # -- test -------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_payment_approval_flow(self, client: AsyncClient) -> None:
        """Full payment flow: bill request → method selection → approval → confirmation."""

        # ── Turn 1: create thread – user wants to pay a bill ─────────
        create_body = {
            "type": "threads.create",
            "params": {
                "input": {
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "I need to pay a bill. "
                                "Payee: Mario The Plumber, "
                                "Invoice ID: 1561672, "
                                "Invoice date: 2026-03-28, "
                                "Amount: 100 EUR"
                            ),
                        }
                    ],
                    "attachments": [],
                    "quoted_text": "",
                    "inference_options": {},
                },
            },
        }

        turn1 = await client.post("/chatkit", json=create_body, timeout=120)
        assert turn1.status_code == 200
        turn1_events = parse_sse_events(turn1.text)
        assert len(turn1_events) > 0

        thread_id = turn1_events[0]["thread"]["id"]
        print(f"\n--- Payment Turn 1: thread {thread_id}, {len(turn1_events)} events ---")

        # Collect all events across turns to find the approval widget
        all_events = list(turn1_events)
        approval_widget = self._find_approval_widget(turn1_events)

        # ── Turn 2: select payment method (if agent asked) ───────────
        if approval_widget is None:
            turn2 = await client.post(
                "/chatkit",
                json=self._send_message(thread_id, "use my rechargeable visa card"),
                timeout=120,
            )
            assert turn2.status_code == 200
            turn2_events = parse_sse_events(turn2.text)
            all_events.extend(turn2_events)
            print(f"--- Payment Turn 2 (card selection): {len(turn2_events)} events ---")
            approval_widget = self._find_approval_widget(turn2_events)

        # ── Turn 3: confirm payment (if agent asked for text confirm) ─
        if approval_widget is None:
            turn3 = await client.post(
                "/chatkit",
                json=self._send_message(thread_id, "Yes, proceed with the payment"),
                timeout=120,
            )
            assert turn3.status_code == 200
            turn3_events = parse_sse_events(turn3.text)
            all_events.extend(turn3_events)
            print(f"--- Payment Turn 3 (proceed): {len(turn3_events)} events ---")
            approval_widget = self._find_approval_widget(turn3_events)

        # ── Turn 4: additional nudge if agent still hasn't triggered approval ─
        if approval_widget is None:
            turn4 = await client.post(
                "/chatkit",
                json=self._send_message(thread_id, "go ahead and submit the payment now"),
                timeout=120,
            )
            assert turn4.status_code == 200
            turn4_events = parse_sse_events(turn4.text)
            all_events.extend(turn4_events)
            print(f"--- Payment Turn 4 (nudge): {len(turn4_events)} events ---")
            approval_widget = self._find_approval_widget(turn4_events)

        # At this point we MUST have an approval widget
        assert approval_widget is not None, (
            "Expected a tool_approval_request client_widget for processPayment "
            "but none appeared across all turns. Event types seen: "
            + str([e.get("type") for e in all_events])
        )

        widget_args = approval_widget["item"]["args"]
        print(f"\n--- Approval widget received ---")
        print(f"  tool_name: {widget_args['tool_name']}")
        print(f"  tool_args: {widget_args['tool_args']}")
        print(f"  call_id:   {widget_args['call_id']}")

        # Validate the approval widget contents
        assert widget_args["tool_name"] == "processPayment"
        # tool_args may be a JSON string or dict
        tool_args = widget_args["tool_args"]
        if isinstance(tool_args, str):
            tool_args = json.loads(tool_args)
        assert float(tool_args["amount"]) == 100.0, (
            f"Expected payment amount 100, got {tool_args['amount']}"
        )

        # ── Approval: user approves the payment ─────────────────────
        approval_body = self._build_approval_action(approval_widget, thread_id)
        approval_response = await client.post("/chatkit", json=approval_body, timeout=120)
        assert approval_response.status_code == 200

        approval_events = parse_sse_events(approval_response.text)
        print(f"\n--- Approval response: {len(approval_events)} events ---")
        for i, evt in enumerate(approval_events):
            evt_type = evt.get("type", "?")
            preview = json.dumps(evt, default=str)[:200]
            print(f"  [{i}] {evt_type}: {preview}")

        # Should have a processPayment task event
        task_events = [
            e for e in approval_events
            if e.get("type") == "thread.item.added"
            and e.get("item", {}).get("type") == "task"
        ]
        task_titles = [
            e["item"]["task"]["title"]
            for e in task_events
            if "task" in e.get("item", {})
        ]
        print(f"\n--- Approval task titles ---")
        for t in task_titles:
            print(f"  • {t}")

        # Should have a final assistant message confirming payment
        assistant_done = [
            e for e in get_events_by_type(approval_events, "thread.item.done")
            if e.get("item", {}).get("type") == "assistant_message"
        ]
        assert len(assistant_done) >= 1, (
            "Expected an assistant_message after payment approval"
        )

        final_text = assistant_done[-1]["item"]["content"][0]["text"]
        print(f"\n--- Payment confirmation (first 500 chars) ---\n{final_text[:500]}")

        # The assistant should confirm the payment was processed
        confirmation_keywords = ["paid", "processed", "confirmed", "successful", "submitted", "completed", "approved"]
        has_confirmation = any(kw in final_text.lower() for kw in confirmation_keywords)
        assert has_confirmation, (
            f"Expected payment confirmation in assistant response. Got: {final_text[:300]}"
        )
