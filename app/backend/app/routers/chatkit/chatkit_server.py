import asyncio
from datetime import datetime
from typing import Any, AsyncIterator, Callable, AsyncGenerator
from typing_extensions import TypeVar
from agent_framework_chatkit import ThreadItemConverter
from chatkit.actions import Action
from chatkit.server import ChatKitServer
from chatkit.errors import ErrorCode
from app.routers.chatkit._chatkit_events_handler import ChatKitEventsHandler
from agent_framework.observability import get_tracer
from app.config.settings import settings


from chatkit.types import (
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
    WidgetItem,
    ErrorEvent,
    Page,
)

from app.agents.azure_chat.handoff_orchestrator import HandoffOrchestrator

from .attachment_handler import AttachmentHandler
from .chatkit_customization import ChatKitClientWidgetMixin
from .memory_store import MemoryStore
from .sqllite_store import SQLiteStore
import logging

logger = logging.getLogger(__name__)



class BankingAssistantChatKitServer(ChatKitClientWidgetMixin, ChatKitServer[dict[str, Any]]):
    """ChatKit server implementation using Agent Framework.

    This server integrates Agent Framework agents with ChatKit's server protocol,
    handling message conversion, agent execution, and response streaming.
    """
 
    _sqlite_store = SQLiteStore()

    def __init__(self, handoff_orchestrator: HandoffOrchestrator, origin: str | None = None):

        metadata_store = self._sqlite_store

        #need to use origin to set base url for attachment store
        if origin is None:
            origin = "http://localhost"
            logger.warning("Origin header is missing; defaulting base_url for attachment to http://localhost")
       
        attachment_metadata_handler = AttachmentHandler(
        base_url=origin,
        metadata_store=metadata_store,
         )
       
        super().__init__(metadata_store, attachment_metadata_handler)
    
        # Create ThreadItemConverter with attachment data fetcher
        self.converter = ThreadItemConverter()
        self.handoff_orchestrator = handoff_orchestrator

    async def _update_thread_title(
        self, thread: ThreadMetadata, user_message_content: UserMessageItem, context: dict[str, Any]
    ) -> None:
        """Update thread title simply using first message.

        Args:
            thread: The thread metadata to update.
            thread_items: All items in the thread.
            context: The context dictionary.
        """
        logger.info(f"Attempting to update thread title for thread: {thread.id}")
 

        # Pick the firs user message
        first_user_message: str = "Untitled thread"
       
        for content_part in user_message_content.content:
            if hasattr(content_part, "text") and isinstance(content_part.text, str):
                first_user_message = content_part.text
       
        if not first_user_message:
            logger.debug("No user messages found for title generation. Defaulting to 'Untitled thread'")
            
        thread.title = first_user_message[:50].strip()
        await self.store.save_thread(thread, context)
        logger.info(f"Updated thread {thread.id} title to: {thread.title}")

    
    # This is called by the ChatKit server when a new user message is received
    async def respond(
        self,
        thread: ThreadMetadata,
        input_user_message: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        """Handle incoming user messages and generate responses.

        This method converts ChatKit messages to Agent Framework format using ThreadItemConverter,
        runs the agent, converts the response back to ChatKit events using stream_agent_response,
        and creates interactive weather widgets when weather data is queried.
        """

        if input_user_message is None:
            logger.debug("Received None user message, skipping")
            return

        logger.info(f"Processing message for thread: {thread.id}")
        with get_tracer().start_as_current_span(f"Banking Assistant - {thread.id}") as current_span:

            try:
                
                #Extracting the attachments id. Only one is supported right now
                attachment_ids = []
                if input_user_message.attachments :
                    attachment_ids = [attachment.id for attachment in input_user_message.attachments]
                    logger.info(f"User message has attachments: {attachment_ids}")

                # Convert ChatKit user message to Agent Framework ChatMessage using ThreadItemConverter
                agent_messages = await self.converter.to_agent_input(input_user_message)

                if not agent_messages:
                    logger.warning("No messages after conversion")
                    return

                logger.info(f"Running agent with {len(agent_messages)} message(s)")


                #get last message
                last_message = agent_messages[-1]

                expanded_text_with_attachements = last_message.text
                

                if attachment_ids:
                    expanded_text_with_attachements += (f" [attachment_id: {attachment_ids[0]}]")
                
                af_events = self.handoff_orchestrator.processMessageStream(expanded_text_with_attachements, thread.id)

                chatkit_event_handler = ChatKitEventsHandler()

                async for event in chatkit_event_handler.handle_events(thread.id, af_events):
                    yield event

            # Update thread title based on first user message if not already set
                if not thread.title or thread.title == "New thread":
                    await self._update_thread_title(thread, input_user_message, context)

            except Exception as e:
                logger.error(f"Error processing message for thread {thread.id}: {e}", exc_info=True)
                yield ErrorEvent(message = f"An error occurred while processing your message for thread {thread.id}")

    #this is called by chatkit server when a custom action is received from the client like the ones defined in widgets.
    async def action(
        self,
        thread: ThreadMetadata,
        action: Action[str, Any],
        sender: WidgetItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        """Handle widget actions from the frontend.

        This method processes actions triggered by interactive widgets,
        such as city selection from the city selector widget.
        """

        logger.info(f"Received action: {action.type} for thread: {thread.id}")
        with get_tracer().start_as_current_span(f"Banking Assistant - {thread.id}") as current_span:

            try:
                if action.type == "approval":
                    # Extract city information from the action payload
                    approved = action.payload.get("approved", False)
                    call_id = action.payload.get("call_id", None)
                    request_id = action.payload.get("request_id", None)
                    tool_name = action.payload.get("tool_name", None)

                # Manage last user message. what about thread ? 
                    af_events = self.handoff_orchestrator.processToolApprovalResponse(thread.id,approved,call_id=call_id, request_id=request_id, tool_name=tool_name)

                    chatkit_event_handler = ChatKitEventsHandler()

                    async for event in chatkit_event_handler.handle_events(thread.id, af_events):
                        yield event

                
            except Exception as e:
                logger.error(f"Error processing message for thread {thread.id}: {e}", exc_info=True)
                yield ErrorEvent(message = f"An error occurred while processing your message for thread {thread.id}")

