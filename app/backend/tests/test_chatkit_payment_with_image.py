"""Legacy integration test for payment with invoice OCR, currently disabled.

Validates the full payment flow when the user uploads an invoice image
and says "pay this bill". The agent uses Document Intelligence to extract
invoice details, then proceeds with the human-in-the-loop approval flow.

This scenario is skipped until invoice extraction is explicitly restored. Requires:
- Azure OpenAI credentials
- Azure Storage Account (for blob upload)
- Azure Document Intelligence (for invoice scanning)
"""

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from conftest import get_events_by_type, parse_sse_events

# Path to the sample invoice image
INVOICE_IMAGE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "gori.png"


@pytest.mark.skip(reason="Invoice OCR is not available in the current deployment")
class TestChatkitPaymentWithImageFlow:
    """Flow 4 – Payment with invoice image upload and human-in-the-loop approval.

    Steps:
    0.1) Client calls attachments.create to get upload metadata.
    0.2) Client uploads the real image file to the upload URL.
    1)   Client sends threads.create with the attachment id and "pay this bill".
    2)   Agent scans the invoice via Document Intelligence, presents extracted
         data (vendor, amount, date, invoice id) for user confirmation.
    3)   User confirms the extracted data is correct.
    4)   Agent asks for payment method selection.
    5)   User selects payment method (rechargeable visa card).
    6)   Agent emits tool_approval_request widget for processPayment.
    7)   User approves via threads.custom_action.
    8)   Agent confirms payment was processed.
    """

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _send_message(thread_id: str, text: str, attachments: list | None = None) -> dict:
        """Build a threads.add_user_message request body."""
        return {
            "type": "threads.add_user_message",
            "params": {
                "input": {
                    "content": [{"type": "input_text", "text": text}],
                    "attachments": attachments or [],
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
    async def test_payment_with_image_upload_flow(self, client: AsyncClient) -> None:
        """Full payment flow: upload invoice image → pay this bill → approval → confirmation."""

        assert INVOICE_IMAGE.exists(), f"Sample invoice not found at {INVOICE_IMAGE}"

        # ── Step 0.1: Create attachment metadata ─────────────────────
        attachment_create_body = {
            "type": "attachments.create",
            "params": {
                "name": "gori.png",
                "size": INVOICE_IMAGE.stat().st_size,
                "mime_type": "image/png",
            },
        }

        attach_response = await client.post(
            "/chatkit",
            json=attachment_create_body,
            headers={"Origin": "http://test"},
            timeout=30,
        )
        assert attach_response.status_code == 200

        attachment_meta = attach_response.json()
        attachment_id = attachment_meta["id"]
        assert attachment_id, "Attachment must have an id"
        assert attachment_meta["type"] == "image"
        assert attachment_meta["mime_type"] == "image/png"
        assert attachment_meta["upload_descriptor"] is not None, "upload_descriptor should be set before upload"
        print(f"\n--- Attachment created: {attachment_id} ---")
        print(f"  upload_descriptor: {attachment_meta['upload_descriptor']}")

        # ── Step 0.2: Upload the actual file ─────────────────────────
        file_bytes = INVOICE_IMAGE.read_bytes()
        upload_response = await client.post(
            f"/upload/{attachment_id}",
            files={"file": ("gori.png", file_bytes, "image/png")},
            timeout=30,
        )
        assert upload_response.status_code == 200

        upload_result = upload_response.json()
        assert upload_result["id"] == attachment_id
        assert upload_result.get("upload_descriptor") is None, "upload_descriptor should be cleared after upload"
        print(f"--- File uploaded: {len(file_bytes)} bytes ---")

        # ── Step 1: Create thread with attachment – "pay this bill" ──
        create_body = {
            "type": "threads.create",
            "params": {
                "input": {
                    "content": [{"type": "input_text", "text": "pay this bill"}],
                    "attachments": [attachment_id],
                    "quoted_text": "",
                    "inference_options": {},
                },
            },
        }

        turn1 = await client.post(
            "/chatkit",
            json=create_body,
            headers={"Origin": "http://test"},
            timeout=120,
        )
        assert turn1.status_code == 200
        turn1_events = parse_sse_events(turn1.text)
        assert len(turn1_events) > 0

        thread_id = turn1_events[0]["thread"]["id"]
        print(f"\n--- Turn 1: thread {thread_id}, {len(turn1_events)} events ---")
        for i, evt in enumerate(turn1_events):
            evt_type = evt.get("type", "?")
            preview = json.dumps(evt, default=str)[:200]
            print(f"  [{i}] {evt_type}: {preview}")

        # The agent should have scanned the invoice using Document Intelligence
        # and responded with the extracted data for user confirmation.
        task_events = [
            e for e in turn1_events
            if e.get("type") == "thread.item.added"
            and e.get("item", {}).get("type") == "task"
        ]
        task_titles = [
            e["item"].get("task", {}).get("title", "")
            for e in task_events
            if "task" in e.get("item", {})
        ]
        print(f"\n--- Task titles ---")
        for t in task_titles:
            print(f"  • {t}")

        # The first assistant reply should mention extracted invoice data
        assistant_msgs_turn1 = [
            e for e in get_events_by_type(turn1_events, "thread.item.done")
            if e.get("item", {}).get("type") == "assistant_message"
        ]
        assert len(assistant_msgs_turn1) >= 1, (
            "Expected assistant to reply with extracted invoice data after scanning"
        )
        turn1_text = assistant_msgs_turn1[-1]["item"]["content"][0]["text"]
        print(f"\n--- Turn 1 assistant message (first 500 chars) ---\n{turn1_text[:500]}")

        # Collect all events across turns
        all_events = list(turn1_events)
        approval_widget = self._find_approval_widget(turn1_events)

        # ── Turn 2: user confirms the extracted data ─────────────────
        if approval_widget is None:
            turn2 = await client.post(
                "/chatkit",
                json=self._send_message(thread_id, "Yes, the data looks correct. Please proceed."),
                headers={"Origin": "http://test"},
                timeout=120,
            )
            assert turn2.status_code == 200
            turn2_events = parse_sse_events(turn2.text)
            all_events.extend(turn2_events)
            print(f"\n--- Turn 2 (data confirmation): {len(turn2_events)} events ---")
            approval_widget = self._find_approval_widget(turn2_events)

        # ── Turn 3: select payment method ────────────────────────────
        if approval_widget is None:
            turn3 = await client.post(
                "/chatkit",
                json=self._send_message(thread_id, "use my rechargeable visa card"),
                headers={"Origin": "http://test"},
                timeout=120,
            )
            assert turn3.status_code == 200
            turn3_events = parse_sse_events(turn3.text)
            all_events.extend(turn3_events)
            print(f"\n--- Turn 3 (card selection): {len(turn3_events)} events ---")
            approval_widget = self._find_approval_widget(turn3_events)

        # ── Turn 4: confirm payment (if agent asked for text confirm) ─
        if approval_widget is None:
            turn4 = await client.post(
                "/chatkit",
                json=self._send_message(thread_id, "Yes, proceed with the payment"),
                headers={"Origin": "http://test"},
                timeout=120,
            )
            assert turn4.status_code == 200
            turn4_events = parse_sse_events(turn4.text)
            all_events.extend(turn4_events)
            print(f"\n--- Turn 4 (proceed): {len(turn4_events)} events ---")
            approval_widget = self._find_approval_widget(turn4_events)

        # ── Turn 5: additional nudge if agent still hasn't triggered approval ─
        if approval_widget is None:
            turn5 = await client.post(
                "/chatkit",
                json=self._send_message(thread_id, "go ahead and submit the payment now"),
                headers={"Origin": "http://test"},
                timeout=120,
            )
            assert turn5.status_code == 200
            turn5_events = parse_sse_events(turn5.text)
            all_events.extend(turn5_events)
            print(f"\n--- Turn 5 (nudge): {len(turn5_events)} events ---")
            approval_widget = self._find_approval_widget(turn5_events)

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
        # The invoice total is 85.20 EUR — verify the amount is reasonable
        amount = float(tool_args["amount"])
        assert amount > 0, f"Payment amount should be positive, got {amount}"
        print(f"  parsed amount: {amount}")

        # ── Approval: user approves the payment ─────────────────────
        approval_body = self._build_approval_action(approval_widget, thread_id)
        approval_response = await client.post(
            "/chatkit",
            json=approval_body,
            headers={"Origin": "http://test"},
            timeout=120,
        )
        assert approval_response.status_code == 200

        approval_events = parse_sse_events(approval_response.text)
        print(f"\n--- Approval response: {len(approval_events)} events ---")
        for i, evt in enumerate(approval_events):
            evt_type = evt.get("type", "?")
            preview = json.dumps(evt, default=str)[:200]
            print(f"  [{i}] {evt_type}: {preview}")

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
