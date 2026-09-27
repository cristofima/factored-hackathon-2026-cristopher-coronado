"""ChatKit Server Customizations — Mixin for ClientWidgetItem support.

The openai-chatkit library defines a closed ``ThreadItem`` discriminated union
(user_message | assistant_message | client_tool_call | widget | generated_image |
workflow | task | hidden_context_item | sdk_hidden_context | end_of_turn).

Our application introduces a **custom item type** — ``ClientWidgetItem``
(discriminator ``type: "client_widget"``) — to let agents emit lightweight,
pre-built widget directives that the frontend renders on its own (as opposed to
server-managed ``WidgetItem`` which carries a full widget tree).

Because ``client_widget`` is not part of the upstream ``ThreadItem`` union,
several internal ``ChatKitServer`` methods that construct or validate ``Thread``
objects with pydantic will reject threads containing ``ClientWidgetItem``.

This mixin overrides those methods so that ``ClientWidgetItem`` instances flow
through the system correctly:

* **_load_full_thread** — called by ``threads.get_by_id`` to load a thread from
  the store. The base implementation creates ``Thread(**meta, items=items)``
  which triggers pydantic validation and fails on ``client_widget``.
  We use ``Thread.model_construct()`` to bypass validation.

* **_to_thread_response** — called before every thread payload is sent to the
  client. Same ``model_construct()`` approach so ``ClientWidgetItem`` items are
  included in the response (the client needs to render them).

* **_process_events** — wraps the event stream from ``respond()`` / ``action()``
  and persists items to the store. The base implementation only handles the
  upstream ``ThreadItemDoneEvent``. We extend the match to also accept
  ``CustomThreadItemDoneEvent`` which wraps our extended ``ThreadItem`` union
  that includes ``ClientWidgetItem``.

* **_process_streaming_impl** — routes incoming streaming requests to handlers.
  The ``ThreadsCustomActionReq`` case needs to accept ``ClientWidgetItem`` as a
  valid sender (not just ``WidgetItem``). We convert it to a stub ``WidgetItem``
  so the downstream ``action()`` handler receives the expected type.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, AsyncIterator, Callable

from chatkit.errors import CustomStreamError, ErrorCode, StreamError
from chatkit.server import agents_sdk_user_agent_override
from chatkit.types import (
    ClientToolCallItem,
    ErrorEvent,
    HiddenContextItem,
    Page,
    SDKHiddenContextItem,
    StreamingReq,
    StreamOptionsEvent,
    Thread,
    ThreadCreatedEvent,
    ThreadItem,
    ThreadItemAddedEvent,
    ThreadItemDoneEvent,
    ThreadItemRemovedEvent,
    ThreadItemReplacedEvent,
    ThreadItemUpdatedEvent,
    ThreadMetadata,
    ThreadsAddClientToolOutputReq,
    ThreadsAddUserMessageReq,
    ThreadsCreateReq,
    ThreadsCustomActionReq,
    ThreadsRetryAfterItemReq,
    ThreadStreamEvent,
    ThreadUpdatedEvent,
    UserMessageItem,
    WidgetItem,
)
from chatkit.widgets import Card
from typing_extensions import assert_never

from app.common.chatkit.types import ClientWidgetItem, CustomThreadItemDoneEvent

logger = logging.getLogger(__name__)


class ChatKitClientWidgetMixin:
    """Mixin that teaches ChatKitServer to handle ``ClientWidgetItem``.

    Must be listed **before** ``ChatKitServer`` in the MRO so that these
    overrides take precedence.
    """

    # ── _load_full_thread ────────────────────────────────────────────
    # WHY: The base ``_load_full_thread`` constructs ``Thread(...)`` which runs
    # pydantic validation. Threads that contain ``ClientWidgetItem`` (type
    # discriminator ``client_widget``) fail validation because the upstream
    # ``ThreadItem`` union doesn't recognise that tag.
    # FIX: Use ``Thread.model_construct()`` to skip validation entirely.
    async def _load_full_thread(self, thread_id: str, context: dict[str, Any]) -> Thread:
        thread_meta = await self.store.load_thread(thread_id, context=context)
        thread_items = await self.store.load_thread_items(
            thread_id, after=None, limit=20, order="asc", context=context,
        )
        return Thread.model_construct(
            **thread_meta.model_dump(),
            items=thread_items,
        )

    # ── _to_thread_response ──────────────────────────────────────────
    # WHY: When items contain ``ClientWidgetItem`` the upstream ``Thread``
    # constructor rejects the unknown discriminator tag. We bypass
    # validation with ``model_construct()`` only in that case.
    # CAVEAT: ``model_construct()`` objects produce ``MockValSer`` when
    # nested inside another pydantic model's ``model_dump_json()``, so we
    # must avoid it for thread-metadata-only contexts (e.g. threads.list)
    # where items are empty and the result will be serialised inside a
    # ``Page`` container.
    def _to_thread_response(self, thread) -> Thread:
        def is_hidden(item) -> bool:
            return isinstance(item, (HiddenContextItem, SDKHiddenContextItem))

        items = thread.items if isinstance(thread, Thread) else Page()
        items.data = [item for item in items.data if not is_hidden(item)]

        has_client_widgets = any(
            isinstance(item, ClientWidgetItem) for item in items.data
        )

        if has_client_widgets:
            return Thread.model_construct(
                id=thread.id,
                title=thread.title,
                created_at=thread.created_at,
                items=items,
                status=thread.status,
                allowed_image_domains=getattr(thread, "allowed_image_domains", None),
            )

        return Thread(
            id=thread.id,
            title=thread.title,
            created_at=thread.created_at,
            items=items,
            status=thread.status,
            allowed_image_domains=getattr(thread, "allowed_image_domains", None),
        )

    # ── _process_events ──────────────────────────────────────────────
    # WHY: The base ``_process_events`` only matches ``ThreadItemDoneEvent``
    # when persisting completed items to the store. Our agents emit
    # ``CustomThreadItemDoneEvent`` for ``ClientWidgetItem`` (because the
    # standard event's ``item`` field uses the upstream union that would
    # reject the custom type). We must match both event types.
    # FIX: Extended match clause to include ``CustomThreadItemDoneEvent``.
    # The rest of the method is kept in sync with upstream v1.6.3 (stream
    # options, pending-item tracking for cancellation, etc.).
    async def _process_events(
        self,
        thread: ThreadMetadata,
        context: dict[str, Any],
        stream: Callable[[], AsyncIterator[ThreadStreamEvent]],
    ) -> AsyncIterator[ThreadStreamEvent]:
        await asyncio.sleep(0)  # allow the response to start streaming

        # Send initial stream options
        yield StreamOptionsEvent(
            stream_options=self.get_stream_options(thread, context)
        )

        last_thread = thread.model_copy(deep=True)

        # Keep track of items that were streamed but not yet saved
        # so that we can persist them when the stream is cancelled.
        pending_items: dict[str, ThreadItem] = {}

        try:
            with agents_sdk_user_agent_override():
                async for event in stream():
                    if isinstance(event, ThreadItemAddedEvent):
                        # Stash an isolated copy in case we need to persist unfinished items
                        # on cancellation; downstream handlers keep using the original event.item.
                        pending_items[event.item.id] = event.item.model_copy(deep=True)

                    match event:
                        case ThreadItemDoneEvent() | CustomThreadItemDoneEvent():
                            await self.store.add_thread_item(
                                thread.id, event.item, context=context  # type: ignore
                            )
                            pending_items.pop(event.item.id, None)
                        case ThreadItemRemovedEvent():
                            await self.store.delete_thread_item(
                                thread.id, event.item_id, context=context  # type: ignore
                            )
                            pending_items.pop(event.item_id, None)
                        case ThreadItemReplacedEvent():
                            await self.store.save_item(
                                thread.id, event.item, context=context  # type: ignore
                            )
                            pending_items.pop(event.item.id, None)
                        case ThreadItemUpdatedEvent():
                            # Keep pending assistant message and workflow items up to date
                            self._update_pending_items(pending_items, event)

                    # special case - don't send hidden context items back to the client
                    should_swallow_event = isinstance(
                        event, ThreadItemDoneEvent
                    ) and isinstance(event.item, (HiddenContextItem, SDKHiddenContextItem))

                    if not should_swallow_event:
                        yield event

                    # in case user updated the thread while streaming
                    if thread != last_thread:
                        last_thread = thread.model_copy(deep=True)
                        await self.store.save_thread(thread, context=context)  # type: ignore
                        yield ThreadUpdatedEvent(
                            thread=self._to_thread_response(thread)
                        )
                # in case user updated the thread while streaming
                if thread != last_thread:
                    last_thread = thread.model_copy(deep=True)
                    await self.store.save_thread(thread, context=context)  # type: ignore
                    yield ThreadUpdatedEvent(thread=self._to_thread_response(thread))
        except asyncio.CancelledError:
            await self.handle_stream_cancelled(
                thread, list(pending_items.values()), context
            )
            raise
        except CustomStreamError as e:
            yield ErrorEvent(
                code="custom",
                message=e.message,
                allow_retry=e.allow_retry,
            )
        except StreamError as e:
            yield ErrorEvent(
                code=e.code,
                allow_retry=e.allow_retry,
            )
        except Exception as e:
            yield ErrorEvent(
                code=ErrorCode.STREAM_ERROR,
                allow_retry=True,
            )
            logger.exception(e)

        if thread != last_thread:
            # in case user updated the thread at the end of the stream
            await self.store.save_thread(thread, context=context)  # type: ignore
            yield ThreadUpdatedEvent(thread=self._to_thread_response(thread))

    # ── _process_streaming_impl ──────────────────────────────────────
    # WHY: The ``ThreadsCustomActionReq`` handler in the base class checks
    # ``isinstance(item, WidgetItem)`` and rejects anything else.
    # ``ClientWidgetItem`` is not a ``WidgetItem``, so actions on client
    # widgets (e.g. payment approval) would fail.
    # FIX: Accept ``ClientWidgetItem`` as a valid sender and wrap it in a
    # stub ``WidgetItem`` so the downstream ``action()`` method receives
    # the type it expects.
    async def _process_streaming_impl(
        self, request: StreamingReq, context: dict[str, Any]
    ) -> AsyncGenerator[ThreadStreamEvent, None]:
        match request:
            case ThreadsCreateReq():
                thread = Thread(
                    id=self.store.generate_thread_id(context),  # type: ignore
                    created_at=datetime.now(),
                    items=Page(),  # type: ignore
                )
                await self.store.save_thread(
                    ThreadMetadata(**thread.model_dump()),
                    context=context,
                )
                yield ThreadCreatedEvent(thread=self._to_thread_response(thread))
                user_message = await self._build_user_message_item(
                    request.params.input, thread, context
                )
                async for event in self._process_new_thread_item_respond(
                    thread,
                    user_message,
                    context,
                ):
                    yield event

            case ThreadsAddUserMessageReq():
                thread = await self.store.load_thread(
                    request.params.thread_id, context=context
                )
                user_message = await self._build_user_message_item(
                    request.params.input, thread, context
                )
                async for event in self._process_new_thread_item_respond(
                    thread,
                    user_message,
                    context,
                ):
                    yield event

            case ThreadsAddClientToolOutputReq():
                thread = await self.store.load_thread(
                    request.params.thread_id, context=context
                )
                items = await self.store.load_thread_items(
                    thread.id, None, 1, "desc", context
                )
                tool_call = next(
                    (
                        item
                        for item in items.data
                        if isinstance(item, ClientToolCallItem)
                        and item.status == "pending"
                    ),
                    None,
                )
                if not tool_call:
                    raise ValueError(
                        f"Last thread item in {thread.id} was not a ClientToolCallItem"
                    )

                tool_call.output = request.params.result
                tool_call.status = "completed"

                await self.store.save_item(thread.id, tool_call, context=context)

                await self._cleanup_pending_client_tool_call(thread, context)

                async for event in self._process_events(
                    thread,
                    context,
                    lambda: self.respond(thread, None, context),
                ):
                    yield event

            case ThreadsRetryAfterItemReq():
                thread_metadata = await self.store.load_thread(
                    request.params.thread_id, context=context
                )

                items_to_remove: list[ThreadItem] = []
                user_message_item = None

                async for item in self._paginate_thread_items_reverse(
                    request.params.thread_id, context
                ):
                    if item.id == request.params.item_id:
                        if not isinstance(item, UserMessageItem):
                            raise ValueError(
                                f"Item {request.params.item_id} is not a user message"
                            )
                        user_message_item = item
                        break
                    items_to_remove.append(item)

                if user_message_item:
                    for item in items_to_remove:
                        await self.store.delete_thread_item(
                            request.params.thread_id, item.id, context=context
                        )
                    async for event in self._process_events(
                        thread_metadata,
                        context,
                        lambda: self.respond(
                            thread_metadata,
                            user_message_item,
                            context,
                        ),
                    ):
                        yield event

            case ThreadsCustomActionReq():
                thread_metadata = await self.store.load_thread(
                    request.params.thread_id, context=context
                )

                item = {}
                if request.params.item_id:
                    item = await self.store.load_item(
                        request.params.thread_id,
                        request.params.item_id,
                        context=context,
                    )

                if item and not isinstance(item, WidgetItem) and not isinstance(item, ClientWidgetItem):
                    yield ErrorEvent(
                        code=ErrorCode.STREAM_ERROR,
                        message=f"Item {request.params.item_id} is not neither a widget item nor a client widget item",
                        allow_retry=False,
                    )
                    return

                # Convert ClientWidgetItem to a stub WidgetItem so the
                # downstream action() handler receives the type it expects.
                fake_widget_root = Card(children=[])
                fake_widget_item: WidgetItem | None = None

                if isinstance(item, ClientWidgetItem):
                    fake_widget_item = WidgetItem(
                        id=item.id,
                        thread_id=item.thread_id,
                        created_at=item.created_at,
                        widget=fake_widget_root,
                    )
                elif isinstance(item, WidgetItem):
                    fake_widget_item = item

                async for event in self._process_events(
                    thread_metadata,
                    context,
                    lambda: self.action(
                        thread_metadata,
                        request.params.action,
                        fake_widget_item,
                        context,
                    ),
                ):
                    yield event

            case _:
                assert_never(request)
