## Development Tasks

This section provides step-by-step guidance for common development tasks in the banking assistant project.

### Task 1: Add a New Agent

Follow these steps to create and integrate a new agent into the system:

#### Step 1: Create the Agent File

Choose the implementation version you're working with:
- **Azure Chat version**: `app/backend/app/agents/azure_chat/your_agent_name.py`
- **Foundry v2 version**: `app/backend/app/agents/foundry_v2/your_agent_name.py`

Create a new Python file for your agent:

**For Azure Chat version:**
```python
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework import Agent, MCPStreamableHTTPTool
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class YourAgentName:
    """
    Your agent description and purpose.
    """
    
    instructions = """
    You are a specialized agent for [specific domain].
    Your responsibilities include:
    - [Responsibility 1]
    - [Responsibility 2]
    - [Responsibility 3]
    
    """
    
    name = "YourAgentName"
    description = "This agent handles [brief description of agent's purpose]"
    
    def __init__(self, 
                 azure_chat_client: AzureOpenAIChatClient,
                 your_service_mcp_server_url: str):
        self.azure_chat_client = azure_chat_client
        self.your_service_mcp_server_url = your_service_mcp_server_url
    
    async def build_af_agent(self) -> Agent:
        """Build and return the Agent with dynamic context."""
        
        logger.info(f"Initializing MCP server tools for {self.name}")
        
        # Use async context manager for MCP tools
        async with MCPStreamableHTTPTool(
            name="Your Service MCP client",
            url=self.your_service_mcp_server_url
        ) as your_mcp_server:
            
            return Agent(
                client=self.azure_chat_client,
                instructions=YourAgentName.instructions,
                name=YourAgentName.name,
                tools=[your_mcp_server],
            )
```

**For Foundry v2 version:**
```python
from agent_framework.azure import AzureAIClient
from agent_framework import Agent, MCPStreamableHTTPTool
# Similar structure but use AzureAIClient instead of AzureOpenAIChatClient
```

#### Step 2: Define Agent Tools

If your agent needs custom tools, create them in `app/backend/app/tools/`:

```python
# app/backend/app/tools/your_tool.py
from typing import Annotated
from agent_framework._tools import tool
from pydantic import Field

class YourToolHelper:
    """Helper class for your custom tool functionality."""
    
    def __init__(self, dependency_service=None):
        """Initialize the tool helper with any required dependencies."""
        self.dependency_service = dependency_service
    
    @tool
    def your_custom_tool(
        self,
        param1: Annotated[str, Field(description="Description of param1")],
        param2: Annotated[int, Field(description="Description of param2")]
    ) -> Annotated[dict, Field(description="Returns a dictionary with processing results")]:
        """Tool description for the LLM. This docstring explains what the tool does."""
        # Implement tool logic
        result = {"status": "success", "data": f"Processed {param1} with {param2}"}
        return result
```

**Key Points:**
- Use `@tool` decorator from `agent_framework._tools`
- Use `Annotated[type, Field(description="...")]` for parameters and return type
- The docstring serves as the tool description for the LLM
- Wrap tools in a class for better organization and dependency injection

**Register the tool in the DI container:**

Register your tool helper in `app/backend/app/config/container_azure_chat.py` (or `container_foundry_v2.py`):

First, add the import at the top of the file:
```python
from app.tools.your_tool import YourToolHelper
```

Then, add the tool helper as a singleton in the Container class:
```python
class Container(containers.DeclarativeContainer):
    """IoC container for application dependencies."""
    
    # ... existing providers ...
    
    # Your custom tool helper singleton
    your_tool_helper = providers.Singleton(
        YourToolHelper,
        dependency_service=some_dependency  # Pass any required dependencies
    )
```

Next, pass the tool helper to agents that need it. Update the agent provider:
```python
# In the Container class, update the agent that needs your tool
your_agent = providers.Factory(
    YourAgent,
    azure_chat_client=_azure_chat_client,
    your_service_mcp_server_url=f"{settings.YOUR_SERVICE_MCP_URL}/mcp",
    your_tool_helper=your_tool_helper  # Inject the tool helper
)
```

Finally, update your agent class to receive and use the tool:

```python
# In your_agent.py
class YourAgent:
    def __init__(self, 
                 azure_chat_client: AzureOpenAIChatClient,
                 your_service_mcp_server_url: str,
                 your_tool_helper: YourToolHelper):  # Add tool helper parameter
        self.azure_chat_client = azure_chat_client
        self.your_service_mcp_server_url = your_service_mcp_server_url
        self.your_tool_helper = your_tool_helper  # Store reference
    
    async def build_af_agent(self) -> Agent:
        # ... MCP tool initialization ...
        
        return Agent(
            client=self.azure_chat_client,
            instructions=YourAgent.instructions,
            name=YourAgent.name,
            tools=[
                your_mcp_server,
                self.your_tool_helper.your_custom_tool  # Add tool method to tools list
            ],
        )
```

#### Step 3: Register MCP Tools (if using Business API)

If your agent needs to call business APIs via MCP:

1. Ensure the business API service exposes MCP tools
2. Update `app/backend/app/config/settings.py` to include the MCP server URL:

```python
# In settings.py
YOUR_SERVICE_MCP_SERVER_URL: str = Field(
    default="http://localhost:8081/mcp",
    description="Your service MCP server URL"
)
```

3. Load MCP tools in your agent initialization

#### Step 4: Update the Dependency Injection Container

**For Azure Chat version**, edit `app/backend/app/config/container_azure_chat.py`:

First, add the import at the top of the file:
```python
from app.agents.azure_chat.your_agent_name import YourAgentName
```

Then, add the agent factory in the container class:
```python
# Inside the Container class
your_agent_name = providers.Factory(
    YourAgentName,
    azure_chat_client=_azure_chat_client,
    your_service_mcp_server_url=f"{settings.YOUR_SERVICE_MCP_URL}/mcp"
)
```

**For Foundry v2 version**, edit `app/backend/app/config/container_foundry_v2.py` similarly, but use the foundry client:
```python
your_agent_name = providers.Factory(
    YourAgentName,
    azure_ai_client=_azure_ai_client,
    your_service_mcp_server_url=f"{settings.YOUR_SERVICE_MCP_URL}/mcp"
)
```

#### Step 5: Update the Handoff Orchestrator

Edit the handoff orchestrator to include your new agent:

**File**: `app/backend/app/agents/azure_chat/handoff_orchestrator.py` (or `foundry_v2` version)

1. Update the HandoffOrchestrator class to include your agent in the workflow:
```python
class HandoffOrchestrator:
    triage_instructions = """
    You are a banking customer support agent triaging customer requests...
    
    # Triage rules
    - If request is related to [your domain], call handoff_to_YourAgentName.
    ...
    """
    
    def __init__(self, 
                 azure_chat_client: AzureOpenAIChatClient,
                 account_agent: AccountAgent,
                 transaction_agent: TransactionHistoryAgent,
                 payment_agent: PaymentAgent,
                 your_agent_name: YourAgentName):  # Add parameter
        self.azure_chat_client = azure_chat_client
        self.account_agent = account_agent
        self.transaction_agent = transaction_agent
        self.payment_agent = payment_agent
        self.your_agent_name = your_agent_name  # Store reference
        self.workflow = None
    
    async def initialize(self, checkpoint_storage: CheckpointStorage):
        """Initialize the workflow with async operations"""
        triage_agent = Agent(
            client=self.azure_chat_client,
            instructions=HandoffOrchestrator.triage_instructions,
            name="triage_agent"
        )
        
        self.workflow = (
            HandoffBuilder(
                name="banking_assistant_handoff",
                participants=[
                    triage_agent,
                    await self.account_agent.build_af_agent(),
                    await self.transaction_agent.build_af_agent(),
                    await self.payment_agent.build_af_agent(),
                    await self.your_agent_name.build_af_agent()  # Add here
                ],
            )
            .with_start_agent(triage_agent)
            .with_termination_condition(
                lambda conv: sum(1 for msg in conv if msg.role == "user") >= 20
            )
            .with_checkpointing(checkpoint_storage)
            .build()
        )
```

2. Update the orchestrator factory in your DI container to add the new agent:

**In `app/backend/app/config/container_azure_chat.py`:**

```python
# Update the handoff_orchestrator_chatkit factory
handoff_orchestrator_chatkit = providers.Factory(
    HandoffOrchestratorChatKit,
    azure_chat_client=_azure_chat_client,
    account_agent=account_agent_chatkit,
    transaction_agent=transaction_agent_chatkit,
    payment_agent=payment_agent_chatkit,
    your_agent_name=your_agent_name  # Add your new agent
)
```

#### Step 7: Add Tests

Create a test file: `app/backend/tests/test_your_agent_chatkit.py`

```python
import pytest
from app.agents.azure_chat.your_agent_name import YourAgentName

@pytest.mark.asyncio
async def test_your_agent_initialization():
    """Test agent initializes correctly."""
    agent = YourAgentName(model="gpt-4", tools=[])
    assert agent.name == "your_agent_name"
    assert agent.instructions is not None

```

Run tests:
```bash
cd app/backend
uv run pytest tests/test_your_agent_chatkit.py -v
```

#### Step 8: Test End-to-End

1. Start the backend server:
   ```bash
   cd app/backend
   PROFILE=dev ENABLE_SENSITIVE_DATA=true \
     uv run uvicorn app.main_chatkit_server:app --reload --port 8080
   ```
   
   Or use VSCode debugger: Select **DEV - Chatkit Backend App** and press F5

2. Start the frontend:
   ```bash
   cd app/frontend/banking-web
   npm run dev
   ```

3. Test routing to your new agent through the chat interface

---

### Task 2: Change Agentic Orchestration Logic

Follow these steps to modify how agents are selected and how handoffs occur:

#### Step 1: Locate the Orchestrator File

Navigate to the handoff orchestrator for your implementation:
- **Azure Chat**: `app/backend/app/agents/azure_chat/handoff_orchestrator.py`
- **Foundry v2**: `app/backend/app/agents/foundry_v2/handoff_orchestrator.py`

#### Step 2: Understand Current Orchestration

Review and update actual triage agent instructions from `handoff_orchestrator.py`:

```python
class HandoffOrchestrator:
    
    triage_instructions = """
      You are a banking customer support agent triaging customer requests about their banking account, movements, payments.
      You have to evaluate the whole conversation with the customer and handoff to AccountAgent, TransactionHistoryAgent, PaymentAgent. 
      When delegation is required, call the matching handoff too based on triage rules.
      
      
      # Triage rules
      - If the user request is related to bank account information like account balance, payment methods, cards and beneficiaries book you must call handoff_to_AccountAgent.
      - If the user request is related to banking movements and payments history, you must call handoff_to_TransactionHistoryAgent.
      - If the user request is related to initiate a payment request, upload a bill or invoice image for payment or manage an on-going payment process, you must call handoff_to_PaymentAgent.
      - If the user request is not related to account, transactions or payments you must respond to the user that you are not able to help with the request.

      
    """
```

**Key Points:**
- The triage agent evaluates the entire conversation context
- Routing is based on domain-specific rules (account, transactions, payments)
- Out-of-scope requests are handled by the triage agent itself
- Handoff functions are automatically generated by the framework (`handoff_to_AccountAgent`, etc.)


#### Step 6: Test Routing Changes

Create or update tests in `app/backend/tests/`:

```python
@pytest.mark.asyncio
async def test_orchestrator_routes_to_payment_agent():
    """Test routing logic for payment requests."""
    # Test implementation
    pass

@pytest.mark.asyncio  
async def test_orchestrator_context_passing():
    """Test context is preserved across handoffs."""
    # Test implementation
    pass
```

#### Step 7: Validate End-to-End

1. Test various user queries that should trigger different routing paths
2. Verify context is preserved across handoffs
3. Check logs for correct agent selection:
   ```bash
   # View logs with routing decisions
   cd app/backend
   PROFILE=dev ENABLE_SENSITIVE_DATA=true \
     uv run uvicorn app.main_chatkit_server:app --reload --log-level debug --port 8080
   ```
   
   Or use VSCode debugger with breakpoints for step-by-step debugging

---

### Task 3: Customize Chat Protocol Event Handlers

The Microsoft Agent Framework (MAF) emits generic workflow events during agent execution. To expose agents through different chat protocols, you need to translate these MAF events into protocol-specific events.

**Current Implementation:** The banking assistant includes a built-in ChatKit protocol handler that translates MAF events to [ChatKit protocol events](./docs/chat-server-protocol.md).

#### Step 1: Understand MAF to Protocol Translation

The translation happens in protocol-specific event handlers:

**Example: ChatKit Events Handler** (`app/backend/app/routers/chatkit/_chatkit_events_handler.py`)

```python
class ChatKitEventsHandler:
    """Translates MAF events to ChatKit protocol events."""
    
    async def handle_events(
        self, 
        thread_id: str, 
        af_events: AsyncIterable[WorkflowEvent]
    ) -> AsyncGenerator[ThreadStreamEvent, None]:
        """Process MAF events and yield ChatKit-compatible events."""
        
        async for event in af_events:
            if isinstance(event, AgentResponseUpdate):
                # Translate to ChatKit ThreadItemAddedEvent
                chatkit_event = self._handle_text_content(
                    thread_id, 
                    event.message_id, 
                    event.content
                )
                yield chatkit_event
            
            elif event.type == "output" and all(item.type == "function_call" for item in event.data.contents):
                # Translate to ChatKit ProgressUpdateEvent
                yield ProgressUpdateEvent(
                    type="thread.progress.update",
                    message=f"Processing: {event.tool_name}..."
                )
```

**MAF Events Source:** Review all available MAF events in the [MAF Events Source](https://github.com/microsoft/agent-framework/blob/main/python/packages/core/agent_framework/_workflows/_events.py).


#### Step 2: Add a New Chat Protocol (Example: M365 Agents Activity Protocol)

To support a new chat protocol like Microsoft 365 Agents Activity Protocol:

##### 2.1: Create Protocol Event Handler

Create `app/backend/app/routers/m365/_m365_events_handler.py`:

```python
from typing import AsyncGenerator, AsyncIterable
from agent_framework import AgentResponseUpdate, WorkflowEvent
from datetime import datetime

# M365 Activity Protocol types (pseudo-code - use actual M365 types)
class ActivityStreamEvent:
    """Base class for M365 activity events."""
    pass

class ActivityMessageEvent(ActivityStreamEvent):
    """M365 activity message event."""
    def __init__(self, activity_id: str, text: str, timestamp: datetime):
        self.type = "activity.message"
        self.activity_id = activity_id
        self.text = text
        self.timestamp = timestamp

class ActivityProgressEvent(ActivityStreamEvent):
    """M365 activity progress event."""
    def __init__(self, activity_id: str, status: str, progress: int):
        self.type = "activity.progress"
        self.activity_id = activity_id
        self.status = status
        self.progress = progress


class M365EventsHandler:
    """Translates MAF events to M365 Agents Activity Protocol events."""
    
    def __init__(self) -> None:
        self.activity_started = False
        self.accumulated_text = ""
    
    async def handle_events(
        self, 
        activity_id: str, 
        af_events: AsyncIterable[WorkflowEvent]
    ) -> AsyncGenerator[ActivityStreamEvent, None]:
        """Process MAF events and yield M365-compatible activity events."""
        
        async for event in af_events:
            # Translate MAF events to M365 Activity Protocol
            if isinstance(event, AgentResponseUpdate):
                # Convert text response to M365 activity message
                if event.content:
                    yield ActivityMessageEvent(
                        activity_id=activity_id,
                        text=event.content,
                        timestamp=datetime.now()
                    )
            
            elif event.type == "tool_call_start":
                # Convert tool execution to M365 progress update
                yield ActivityProgressEvent(
                    activity_id=activity_id,
                    status=f"Executing {event.tool_name}",
                    progress=50
                )
            
            elif event.type == "tool_call_end":
                # Tool completed
                yield ActivityProgressEvent(
                    activity_id=activity_id,
                    status=f"Completed {event.tool_name}",
                    progress=100
                )
            
            elif event.type == "error":
                # Error handling for M365
                yield ActivityMessageEvent(
                    activity_id=activity_id,
                    text=f"Error: {event.error}",
                    timestamp=datetime.now()
                )
```

##### 2.2: Create Protocol Router

Create `app/backend/app/routers/m365/m365_server.py`:

```python
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.routers.m365._m365_events_handler import M365EventsHandler
from app.config.container_azure_chat import Container
import json

router = APIRouter(prefix="/m365")

@router.post("/activities/run")
async def run_activity(
    request: dict,  # M365 activity request schema
    container: Container = Depends(lambda: Container())
):
    """
    M365 Agents Activity Protocol endpoint.
    Runs an agent activity and streams responses using M365 protocol.
    """
    
    async def stream_m365_events():
        """Stream M365 activity events using Server-Sent Events."""
        
        # Get orchestrator from DI container
        orchestrator = container.handoff_orchestrator_chatkit()
        
        # Run the agent workflow
        af_events = orchestrator.run(
            activity_id=request.get("activityId"),
            user_message=request.get("message")
        )
        
        # Translate MAF events to M365 events
        m365_handler = M365EventsHandler()
        async for m365_event in m365_handler.handle_events(
            activity_id=request.get("activityId"),
            af_events=af_events
        ):
            # Stream as Server-Sent Events
            event_data = json.dumps(m365_event.__dict__)
            yield f"data: {event_data}\n\n"
    
    return StreamingResponse(
        stream_m365_events(),
        media_type="text/event-stream"
    )

@router.get("/activities/{activity_id}/status")
async def get_activity_status(activity_id: str):
    """Get the status of a running activity."""
    # Implementation for status checking
    return {"status": "running", "activity_id": activity_id}
```

##### 2.3: Register Router in Main Application

create `main_m365_server.py`:

```python
from app.routers.m365 import m365_server

# Register the M365 protocol router
app.include_router(m365_server.router, tags=["m365"])
```

##### 2.4: Directory Structure

The final structure for a new protocol:

```
app/backend/app/routers/
├── chatkit/                          # ChatKit protocol implementation
│   ├── _chatkit_events_handler.py    # MAF → ChatKit translation
│   ├── chatkit_server.py             # ChatKit API endpoints
│   └── attachments.py                # ChatKit attachment handling
├── m365/                             # M365 protocol implementation (NEW)
│   ├── _m365_events_handler.py       # MAF → M365 translation
│   └── m365_server.py                # M365 API endpoints
└── simple_chat/                      # Simple chat protocol
    └── ...
```

#### Key Takeaways

- **Protocol independence**: MAF events are protocol-agnostic
- **Event handlers**: Each protocol needs its own translation layer
- **Endpoint structure**: Each protocol gets its own router with protocol-specific endpoints
- **Reusable agents**: The same agent workflows work with any protocol
- **Multiple protocols**: You can support ChatKit, M365, custom protocols simultaneously

---

### Task 4: Customize Thread and Attachment Metadata Store

The ChatKit server uses a **metadata store** (`Store`) to persist thread metadata, thread items, and attachment metadata, and an **attachment metadata store** (`AttachmentStore`) to handle attachment creation and upload URLs. By default, the banking assistant uses `SQLiteStore` — a local SQLite-based implementation suitable for development and demos.

For production scenarios you typically want a cloud-native, scalable database. This task walks through replacing the default stores with custom implementations backed by **Azure Cosmos DB**.

#### Architecture Overview

The banking assistant uses **dependency injection** (via `dependency-injector`) to manage store instances. Both the metadata store and the attachment metadata store are registered as **singletons** in the DI container (`container_azure_chat.py`) and injected into the ChatKit server and routers.

Currently, both stores are created directly inside `chatkit_server.py`:

```python
# Current approach in chatkit_server.py (before customization)
class BankingAssistantChatKitServer(ChatKitServer[dict[str, Any]]):
    metadata_store = SQLiteStore()  # ← Thread & item persistence

    def __init__(self, handoff_orchestrator, origin=None):
        attachment_metadata_store = AttachmentMetadataStore(  # ← Attachment metadata
            base_url=origin,
            metadata_store=BankingAssistantChatKitServer.metadata_store,
        )
        super().__init__(BankingAssistantChatKitServer.metadata_store, attachment_metadata_store)
```

With this customization, we move store creation into the DI container and inject them wherever needed:

```python
# Target approach — stores are injected via DI container
class BankingAssistantChatKitServer(ChatKitServer[dict[str, Any]]):

    def __init__(self, handoff_orchestrator, metadata_store, attachment_metadata_store):
        super().__init__(metadata_store, attachment_metadata_store)
        self.handoff_orchestrator = handoff_orchestrator
```

- **`Store[TContext]`** (from `chatkit.store`): Abstract base class for thread metadata, thread items, and attachment metadata persistence.
- **`AttachmentStore[TContext]`** (from `chatkit.store`): Abstract base class for attachment creation (upload URL generation) and deletion.
- **Singleton registration**: Both stores are registered once in the DI container and shared across `BankingAssistantChatKitServer` and attachment routers.

You can replace either or both with your own implementations.

#### Step 1: Install Azure Cosmos DB SDK

Add the Azure Cosmos DB SDK to your project dependencies:

```bash
cd app/backend
uv add azure-cosmos
```

Or add it to `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "azure-cosmos>=4.7.0",
]
```

#### Step 2: Create the Cosmos DB Metadata Store

Create a new file `app/backend/app/routers/chatkit/cosmosdb_store.py`:

```python
"""Azure Cosmos DB-based store implementation for ChatKit data persistence.

This module provides a complete Store implementation using Azure Cosmos DB
for scalable, cloud-native thread and attachment metadata persistence.
"""

import uuid
from typing import Any
from datetime import datetime

from azure.cosmos.aio import CosmosClient, ContainerProxy
from azure.cosmos import PartitionKey, exceptions

from chatkit.store import Store, NotFoundError
from chatkit.types import (
    Attachment,
    Page,
    ThreadMetadata,
)
from app.common.chatkit.types import ThreadItem

from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)


class ThreadData(BaseModel):
    """Model for serializing thread data."""
    thread: ThreadMetadata


class ItemData(BaseModel):
    """Model for serializing thread item data."""
    item: ThreadItem


class AttachmentData(BaseModel):
    """Model for serializing attachment data."""
    attachment: Attachment


class CosmosDBStore(Store[dict[str, Any]]):
    """Azure Cosmos DB-based store implementation for ChatKit data.

    This implementation uses Azure Cosmos DB for persistent, scalable storage
    of threads, messages, and attachments.

    Features:
    - Horizontally scalable with Cosmos DB partitioning
    - User isolation via partition keys
    - Async operations with azure-cosmos async client
    - Complete Store protocol implementation

    Container design:
    - threads: partitioned by user_id, stores thread metadata
    - items: partitioned by thread_id, stores thread items
    - attachments: partitioned by user_id, stores attachment metadata
    """

    def __init__(
        self,
        cosmos_client: CosmosClient,
        database_name: str = "chatkit",
    ):
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self._threads_container: ContainerProxy | None = None
        self._items_container: ContainerProxy | None = None
        self._attachments_container: ContainerProxy | None = None

    async def initialize(self) -> None:
        """Initialize database and containers. Call once at startup."""
        database = await self.cosmos_client.create_database_if_not_exists(
            id=self.database_name
        )

        self._threads_container = await database.create_container_if_not_exists(
            id="threads",
            partition_key=PartitionKey(path="/user_id"),
        )
        self._items_container = await database.create_container_if_not_exists(
            id="items",
            partition_key=PartitionKey(path="/thread_id"),
        )
        self._attachments_container = await database.create_container_if_not_exists(
            id="attachments",
            partition_key=PartitionKey(path="/user_id"),
        )
        logger.info(f"CosmosDB store initialized with database: {self.database_name}")

    @property
    def threads_container(self) -> ContainerProxy:
        assert self._threads_container is not None, "Call initialize() first"
        return self._threads_container

    @property
    def items_container(self) -> ContainerProxy:
        assert self._items_container is not None, "Call initialize() first"
        return self._items_container

    @property
    def attachments_container(self) -> ContainerProxy:
        assert self._attachments_container is not None, "Call initialize() first"
        return self._attachments_container

    # -- ID generation ---------------------------------------------------

    def generate_thread_id(self, context: dict[str, Any]) -> str:
        return f"thr_{uuid.uuid4().hex[:8]}"

    def generate_item_id(
        self,
        item_type: str,
        thread: ThreadMetadata,
        context: dict[str, Any],
    ) -> str:
        prefix_map = {
            "message": "msg",
            "tool_call": "tc",
            "task": "tsk",
            "workflow": "wf",
            "attachment": "atc",
        }
        prefix = prefix_map.get(item_type, "itm")
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    # -- Thread metadata -------------------------------------------------

    async def load_thread(self, thread_id: str, context: dict[str, Any]) -> ThreadMetadata:
        user_id = context.get("user_id", "demo_user")
        try:
            item = await self.threads_container.read_item(
                item=thread_id, partition_key=user_id
            )
            return ThreadData.model_validate_json(item["data"]).thread
        except exceptions.CosmosResourceNotFoundError:
            raise NotFoundError(f"Thread {thread_id} not found")

    async def save_thread(self, thread: ThreadMetadata, context: dict[str, Any]) -> None:
        user_id = context.get("user_id", "demo_user")
        thread_data = ThreadData(thread=thread)

        document = {
            "id": thread.id,
            "user_id": user_id,
            "created_at": thread.created_at.isoformat() if thread.created_at else datetime.utcnow().isoformat(),
            "data": thread_data.model_dump_json(),
        }
        await self.threads_container.upsert_item(document)

    async def load_threads(
        self,
        limit: int,
        after: str | None,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadMetadata]:
        user_id = context.get("user_id", "demo_user")
        order_direction = "ASC" if order == "asc" else "DESC"

        if after:
            # Get the created_at of the cursor thread
            try:
                after_item = await self.threads_container.read_item(
                    item=after, partition_key=user_id
                )
                created_after = after_item["created_at"]
            except exceptions.CosmosResourceNotFoundError:
                raise NotFoundError(f"Thread {after} not found")

            comparator = ">" if order == "asc" else "<"
            query = (
                f"SELECT * FROM c WHERE c.user_id = @user_id "
                f"AND c.created_at {comparator} @created_after "
                f"ORDER BY c.created_at {order_direction} "
                f"OFFSET 0 LIMIT @limit"
            )
            parameters = [
                {"name": "@user_id", "value": user_id},
                {"name": "@created_after", "value": created_after},
                {"name": "@limit", "value": limit + 1},
            ]
        else:
            query = (
                f"SELECT * FROM c WHERE c.user_id = @user_id "
                f"ORDER BY c.created_at {order_direction} "
                f"OFFSET 0 LIMIT @limit"
            )
            parameters = [
                {"name": "@user_id", "value": user_id},
                {"name": "@limit", "value": limit + 1},
            ]

        items = [
            item async for item in self.threads_container.query_items(
                query=query, parameters=parameters
            )
        ]

        threads = [ThreadData.model_validate_json(item["data"]).thread for item in items]
        has_more = len(threads) > limit
        if has_more:
            threads = threads[:limit]

        return Page[ThreadMetadata](
            data=threads,
            has_more=has_more,
            after=threads[-1].id if threads else None,
        )

    async def delete_thread(self, thread_id: str, context: dict[str, Any]) -> None:
        user_id = context.get("user_id", "demo_user")

        # Delete thread metadata
        try:
            await self.threads_container.delete_item(
                item=thread_id, partition_key=user_id
            )
        except exceptions.CosmosResourceNotFoundError:
            pass

        # Delete all items belonging to this thread
        query = "SELECT c.id FROM c WHERE c.thread_id = @thread_id"
        parameters = [{"name": "@thread_id", "value": thread_id}]
        items = [
            item async for item in self.items_container.query_items(
                query=query, parameters=parameters
            )
        ]
        for item in items:
            await self.items_container.delete_item(
                item=item["id"], partition_key=thread_id
            )

    # -- Thread items ----------------------------------------------------

    async def load_thread_items(
        self,
        thread_id: str,
        after: str | None,
        limit: int,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadItem]:
        order_direction = "ASC" if order == "asc" else "DESC"

        if after:
            try:
                after_item = await self.items_container.read_item(
                    item=after, partition_key=thread_id
                )
                created_after = after_item["created_at"]
            except exceptions.CosmosResourceNotFoundError:
                raise NotFoundError(f"Item {after} not found")

            comparator = ">" if order == "asc" else "<"
            query = (
                f"SELECT * FROM c WHERE c.thread_id = @thread_id "
                f"AND c.created_at {comparator} @created_after "
                f"ORDER BY c.created_at {order_direction} "
                f"OFFSET 0 LIMIT @limit"
            )
            parameters = [
                {"name": "@thread_id", "value": thread_id},
                {"name": "@created_after", "value": created_after},
                {"name": "@limit", "value": limit + 1},
            ]
        else:
            query = (
                f"SELECT * FROM c WHERE c.thread_id = @thread_id "
                f"ORDER BY c.created_at {order_direction} "
                f"OFFSET 0 LIMIT @limit"
            )
            parameters = [
                {"name": "@thread_id", "value": thread_id},
                {"name": "@limit", "value": limit + 1},
            ]

        items_raw = [
            item async for item in self.items_container.query_items(
                query=query, parameters=parameters
            )
        ]

        items = [ItemData.model_validate_json(item["data"]).item for item in items_raw]
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        return Page[ThreadItem](
            data=items,
            has_more=has_more,
            after=items[-1].id if items else None,
        )

    async def add_thread_item(
        self, thread_id: str, item: ThreadItem, context: dict[str, Any]
    ) -> None:
        user_id = context.get("user_id", "demo_user")
        item_data = ItemData(item=item)

        document = {
            "id": item.id,
            "thread_id": thread_id,
            "user_id": user_id,
            "created_at": item.created_at.isoformat(),
            "data": item_data.model_dump_json(),
        }
        await self.items_container.create_item(document)

    async def save_item(
        self, thread_id: str, item: ThreadItem, context: dict[str, Any]
    ) -> None:
        user_id = context.get("user_id", "demo_user")
        item_data = ItemData(item=item)

        document = {
            "id": item.id,
            "thread_id": thread_id,
            "user_id": user_id,
            "created_at": item.created_at.isoformat(),
            "data": item_data.model_dump_json(),
        }
        await self.items_container.upsert_item(document)

    async def load_item(
        self, thread_id: str, item_id: str, context: dict[str, Any]
    ) -> ThreadItem:
        try:
            item = await self.items_container.read_item(
                item=item_id, partition_key=thread_id
            )
            return ItemData.model_validate_json(item["data"]).item
        except exceptions.CosmosResourceNotFoundError:
            raise NotFoundError(f"Item {item_id} not found in thread {thread_id}")

    async def delete_thread_item(
        self, thread_id: str, item_id: str, context: dict[str, Any]
    ) -> None:
        try:
            await self.items_container.delete_item(
                item=item_id, partition_key=thread_id
            )
        except exceptions.CosmosResourceNotFoundError:
            pass

    # -- Attachments -----------------------------------------------------

    async def save_attachment(
        self, attachment: Attachment, context: dict[str, Any]
    ) -> None:
        user_id = context.get("user_id", "demo_user")
        attachment_data = AttachmentData(attachment=attachment)

        document = {
            "id": attachment.id,
            "user_id": user_id,
            "data": attachment_data.model_dump_json(),
        }
        await self.attachments_container.upsert_item(document)

    async def load_attachment(
        self, attachment_id: str, context: dict[str, Any]
    ) -> Attachment:
        user_id = context.get("user_id", "demo_user")
        try:
            item = await self.attachments_container.read_item(
                item=attachment_id, partition_key=user_id
            )
            return AttachmentData.model_validate_json(item["data"]).attachment
        except exceptions.CosmosResourceNotFoundError:
            raise NotFoundError(f"Attachment {attachment_id} not found")

    async def delete_attachment(
        self, attachment_id: str, context: dict[str, Any]
    ) -> None:
        user_id = context.get("user_id", "demo_user")
        try:
            await self.attachments_container.delete_item(
                item=attachment_id, partition_key=user_id
            )
        except exceptions.CosmosResourceNotFoundError:
            pass
```

#### Step 3: Create the Cosmos DB Attachment Metadata Store

Create a new file `app/backend/app/routers/chatkit/cosmosdb_attachment_store.py`:

```python
"""Azure Cosmos DB-backed AttachmentStore for ChatKit.

This module provides an AttachmentStore implementation that generates
upload/preview URLs and persists attachment metadata to Cosmos DB
via the CosmosDBStore.
"""

from typing import Any

from chatkit.store import AttachmentStore
from chatkit.types import (
    Attachment,
    AttachmentCreateParams,
    FileAttachment,
    ImageAttachment,
)
from pydantic import AnyUrl

from .cosmosdb_store import CosmosDBStore

import logging

logger = logging.getLogger(__name__)


class CosmosDBAttachmentMetadataStore(AttachmentStore[dict[str, Any]]):
    """AttachmentStore that generates upload URLs and delegates
    metadata persistence to CosmosDBStore.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        metadata_store: CosmosDBStore | None = None,
    ):
        """Initialize the Cosmos DB-backed attachment store.

        Args:
            base_url: Base URL for generating upload and preview URLs.
            metadata_store: CosmosDBStore instance for persisting attachment metadata.
        """
        self.base_url = base_url.rstrip("/")
        self.metadata_store = metadata_store

    async def create_attachment(
        self, input: AttachmentCreateParams, context: dict[str, Any]
    ) -> Attachment:
        """Create an attachment with upload URL for two-phase upload."""
        attachment_id = self.generate_attachment_id(input.mime_type, context)

        upload_url = f"{self.base_url}/upload/{attachment_id}"

        if input.mime_type.startswith("image/"):
            preview_url = f"{self.base_url}/preview/{attachment_id}"
            attachment = ImageAttachment(
                id=attachment_id,
                type="image",
                mime_type=input.mime_type,
                name=input.name,
                upload_url=AnyUrl(upload_url),
                preview_url=AnyUrl(preview_url),
            )
        else:
            attachment = FileAttachment(
                id=attachment_id,
                type="file",
                mime_type=input.mime_type,
                name=input.name,
                upload_url=AnyUrl(upload_url),
            )

        if self.metadata_store is not None:
            await self.metadata_store.save_attachment(attachment, context)

        return attachment

    async def delete_attachment(
        self, attachment_id: str, context: dict[str, Any]
    ) -> None:
        """Delete attachment metadata from Cosmos DB."""
        if self.metadata_store is not None:
            await self.metadata_store.delete_attachment(attachment_id, context)
```

#### Step 4: Register Stores as Singletons in the DI Container

Register `CosmosDBStore` and `CosmosDBAttachmentMetadataStore` as **singletons** in `app/backend/app/config/container_azure_chat.py`. This ensures a single shared instance is used across the ChatKit server and attachment routers.

##### 4.1: Add Imports

Add the following imports at the top of `container_azure_chat.py`:

```python
from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
from app.routers.chatkit.cosmosdb_store import CosmosDBStore
from app.routers.chatkit.cosmosdb_attachment_store import CosmosDBAttachmentMetadataStore
```

##### 4.2: Add Singleton Providers

Add the Cosmos DB store singletons to the `Container` class, alongside the existing ChatKit providers:

```python
class Container(containers.DeclarativeContainer):
    """IoC container for application dependencies."""

    # ... existing providers (blob_proxy, agents, etc.) ...

    ############# ChatKit Stores #############

    # Azure Cosmos DB async client singleton
    _cosmos_client = providers.Singleton(
        AsyncCosmosClient,
        url=settings.COSMOS_DB_ENDPOINT,
        credential=providers.Factory(get_azure_credential_async),
    )

    # CosmosDB metadata store singleton — thread & item persistence
    cosmosdb_metadata_store = providers.Singleton(
        CosmosDBStore,
        cosmos_client=_cosmos_client,
        database_name=settings.COSMOS_DB_DATABASE,
    )

    # CosmosDB attachment metadata store singleton — upload URL generation & attachment metadata
    cosmosdb_attachment_metadata_store = providers.Singleton(
        CosmosDBAttachmentMetadataStore,
        metadata_store=cosmosdb_metadata_store,
    )
```

> **Note:** The `CosmosDBAttachmentMetadataStore` does not receive `base_url` at construction time because the origin varies per request. Instead, the `base_url` is set at request time inside the ChatKit server (see Step 5).

##### 4.3: Full Container Example (relevant section)

Here is how the ChatKit stores section looks in context with the existing providers:

```python
class Container(containers.DeclarativeContainer):
    """IoC container for application dependencies."""
   
    # Helpers
    blob_service_client = providers.Singleton(
        BlobServiceClient,
        credential=providers.Factory(get_azure_credential),
        account_url=f"https://{settings.AZURE_STORAGE_ACCOUNT}.blob.core.windows.net"
    )

    blob_proxy = providers.Singleton(
        BlobStorageProxy,
        client=blob_service_client,
        container_name=settings.AZURE_STORAGE_CONTAINER
    )

    # ... other existing providers ...

    ############# ChatKit Stores #############

    # Azure Cosmos DB async client singleton
    _cosmos_client = providers.Singleton(
        AsyncCosmosClient,
        url=settings.COSMOS_DB_ENDPOINT,
        credential=providers.Factory(get_azure_credential_async),
    )

    # CosmosDB metadata store singleton — thread & item persistence
    cosmosdb_metadata_store = providers.Singleton(
        CosmosDBStore,
        cosmos_client=_cosmos_client,
        database_name=settings.COSMOS_DB_DATABASE,
    )

    # CosmosDB attachment metadata store singleton — upload URL generation & attachment metadata
    cosmosdb_attachment_metadata_store = providers.Singleton(
        CosmosDBAttachmentMetadataStore,
        metadata_store=cosmosdb_metadata_store,
    )

    ############# ChatKit based agents and orchestrator #############

    # ... existing agent and orchestrator providers ...
```

#### Step 5: Update the ChatKit Server to Accept Injected Stores

Update `app/backend/app/routers/chatkit/chatkit_server.py` to receive stores via constructor parameters instead of creating them internally.

##### 5.1: Update Imports

Remove the SQLite store imports and add the Cosmos DB store imports:

```python
# Before
from .sqllite_store import SQLiteStore
from .attachement_store import AttachmentMetadataStore

# After
from .cosmosdb_store import CosmosDBStore
from .cosmosdb_attachment_store import CosmosDBAttachmentMetadataStore
```

##### 5.2: Update the Server Class

Replace the store initialization so stores are received as constructor parameters (injected by the DI container):

```python
class BankingAssistantChatKitServer(ChatKitServer[dict[str, Any]]):

    def __init__(
        self,
        handoff_orchestrator: HandoffOrchestrator,
        metadata_store: CosmosDBStore,
        attachment_metadata_store: CosmosDBAttachmentMetadataStore,
        origin: str | None = None,
    ):
        if origin is None:
            origin = "http://localhost"
            logger.warning("Origin header is missing; defaulting base_url for attachment to http://localhost")

        # Set the per-request base_url on the attachment store
        attachment_metadata_store.base_url = origin.rstrip("/")

        super().__init__(metadata_store, attachment_metadata_store)

        self.converter = ThreadItemConverter()
        self.handoff_orchestrator = handoff_orchestrator
```

##### 5.3: Update the Chat Router to Inject Stores

Update `app/backend/app/routers/chatkit/chat_routers.py` to inject the stores via DI:

```python
@router.post("/chatkit")
@inject
async def chatkit_endpoint(
    request: Request,
    handoff_orchestrator: HandoffOrchestrator = Depends(Provide[Container.handoff_orchestrator_chatkit]),
    metadata_store: CosmosDBStore = Depends(Provide[Container.cosmosdb_metadata_store]),
    attachment_metadata_store: CosmosDBAttachmentMetadataStore = Depends(Provide[Container.cosmosdb_attachment_metadata_store]),
):
    origin = request.headers.get("origin")

    chatkit_server = BankingAssistantChatKitServer(
        handoff_orchestrator=handoff_orchestrator,
        metadata_store=metadata_store,
        attachment_metadata_store=attachment_metadata_store,
        origin=origin,
    )

    # ... rest of the handler ...
```

#### Step 6: Add Configuration Settings

Add Cosmos DB configuration to `app/backend/app/config/settings.py`:

```python
# In settings.py
COSMOS_DB_ENDPOINT: str = Field(
    default="https://localhost:8081",
    description="Azure Cosmos DB endpoint URL"
)
COSMOS_DB_DATABASE: str = Field(
    default="chatkit",
    description="Cosmos DB database name for ChatKit metadata"
)
```

Set the environment variables or add them to your `.env` file:

```env
COSMOS_DB_ENDPOINT=https://your-cosmosdb-account.documents.azure.com:443/
COSMOS_DB_DATABASE=chatkit
```

#### Step 7: Initialize the Store at Startup

The Cosmos DB store requires async initialization (creating the database and containers). Add initialization to the FastAPI lifespan in `app/backend/app/main_chatkit_server.py`:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize Cosmos DB containers
    cosmosdb_store = app.state.container.cosmosdb_metadata_store()
    await cosmosdb_store.initialize()
    yield
    # Shutdown: close Cosmos DB client
    cosmos_client = app.state.container._cosmos_client()
    await cosmos_client.close()
    logger.info("Shutting down application...")
    app.state.container.unwire()

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
```

Since the store is registered as a `Singleton` in the container, calling `container.cosmosdb_metadata_store()` returns the same instance every time, so the `initialize()` call at startup prepares the shared instance.

#### Step 8: Update the Attachment Router to Use DI (Optional)

If you also use the attachment router at `app/backend/app/routers/chatkit/attachment_routers.py` for direct upload/download endpoints, update it to inject the Cosmos DB store via DI instead of creating a local `SQLiteStore`:

```python
# In attachment_routers.py
# Remove:
#   from .sqllite_store import SQLiteStore
#   metadata_store = SQLiteStore()

# Instead, inject the singleton via DI:
from dependency_injector.wiring import Provide, inject

@router.post("/upload/{attachment_id}")
@inject
async def upload_file(
    attachment_id: str,
    file: UploadFile = File(...),
    blob_proxy: BlobStorageProxy = Depends(Provide[Container.blob_proxy]),
    metadata_store: CosmosDBStore = Depends(Provide[Container.cosmosdb_metadata_store]),
):
    # metadata_store is now the same singleton used by the ChatKit server
    ...
```

This ensures both the ChatKit server and the attachment upload endpoints share the same Cosmos DB-backed store singleton, managed by the DI container.

#### Key Takeaways

- **`Store` protocol**: Implement all abstract methods from `chatkit.store.Store` — this covers threads, thread items, and attachment metadata persistence.
- **`AttachmentStore` protocol**: Implement `create_attachment` and `delete_attachment` from `chatkit.store.AttachmentStore` — this handles upload URL generation and delegates metadata persistence to the `Store`.
- **Dependency injection**: Register both `CosmosDBStore` and `CosmosDBAttachmentMetadataStore` as `providers.Singleton` in `container_azure_chat.py`. This guarantees a single shared instance across the entire application, matching the existing DI patterns used for agents and helpers.
- **Async initialization**: Cosmos DB containers must be created before the server accepts requests; use FastAPI's lifespan event to call `initialize()` on the singleton from the container.
- **Partition strategy**: Use `user_id` for threads and attachments (tenant isolation) and `thread_id` for items (efficient querying per conversation).
- **Drop-in replacement**: The `Store` and `AttachmentStore` abstractions, combined with the DI container, mean you can swap SQLite for Cosmos DB (or any other backend) by changing only the container registration — no agent or ChatKit server logic needs to change.

---

### Task 5: Customize Workflow Checkpoint Store

The Handoff orchestrator uses a **checkpoint store** (`CheckpointStorage`) to persist workflow state across conversation turns. Checkpoints capture the full execution state of a workflow — messages, agent states, pending events — so that multi-turn conversations can be paused and resumed seamlessly.

By default, the banking assistant uses `InMemoryCheckpointStorage`, a simple in-memory dictionary store suitable for development. For production scenarios you need a durable, scalable backend. This task walks through creating a custom `CheckpointStorage` implementation backed by **Azure Cosmos DB** and wiring it into the `HandoffBuilder`.

#### Architecture Overview

The checkpoint store is consumed in two places:

1. **`HandoffBuilder.with_checkpointing(checkpoint_storage)`** — configures the workflow to persist checkpoints after each step.
2. **`HandoffOrchestrator._get_or_create_checkpoint_store(thread_id)`** — resolves the store instance per conversation thread.

```python
# Current default in handoff_orchestrator.py
from agent_framework import InMemoryCheckpointStorage, CheckpointStorage

class HandoffOrchestrator:
    thread_checkpoint_store: dict[str, CheckpointStorage] = {}

    async def _get_or_create_checkpoint_store(self, thread_id: str) -> CheckpointStorage:
        checkpoint_storage = HandoffOrchestrator.thread_checkpoint_store.get(thread_id, None)
        if checkpoint_storage is not None:
            return checkpoint_storage
        checkpoint_storage = InMemoryCheckpointStorage()
        HandoffOrchestrator.thread_checkpoint_store[thread_id] = checkpoint_storage
        return checkpoint_storage
```

The `CheckpointStorage` protocol (defined in `agent_framework`) requires these async methods:

| Method | Description |
|--------|-------------|
| `save(checkpoint)` | Persist a `WorkflowCheckpoint` and return its ID |
| `load(checkpoint_id)` | Load a checkpoint by ID |
| `list_checkpoints(workflow_name)` | List all checkpoints for a workflow |
| `delete(checkpoint_id)` | Delete a checkpoint by ID |
| `get_latest(workflow_name)` | Get the most recent checkpoint for a workflow |
| `list_checkpoint_ids(workflow_name)` | List checkpoint IDs for a workflow |

#### Step 1: Install Azure Cosmos DB SDK

Add the Azure Cosmos DB SDK to your project dependencies:

```bash
cd app/backend
uv add azure-cosmos
```

Or add it to `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "azure-cosmos>=4.7.0",
]
```

#### Step 2: Create the Cosmos DB Checkpoint Store

Create a new file `app/backend/app/common/cosmosdb_checkpoint_store.py`:

```python
"""Azure Cosmos DB-based CheckpointStorage implementation.

Provides a durable, scalable checkpoint store for agent workflow state,
replacing InMemoryCheckpointStorage for production deployments.

Each instance is bound to a specific thread_id — the Cosmos DB container
uses thread_id as the partition key so all checkpoints for a conversation
are co-located for efficient queries.
"""

import logging
import pickle
import base64
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.aio import CosmosClient, ContainerProxy
from azure.cosmos import PartitionKey, exceptions

from agent_framework import CheckpointStorage, WorkflowCheckpoint
from agent_framework._workflows._checkpoint import CheckpointID
from agent_framework._workflows._exceptions import WorkflowCheckpointException

logger = logging.getLogger(__name__)


class CosmosDBCheckpointStorage:
    """Azure Cosmos DB implementation of CheckpointStorage.

    Stores workflow checkpoints as documents in a Cosmos DB container,
    partitioned by thread_id. Each instance is scoped to a single
    conversation thread — all reads, writes, and queries are automatically
    filtered to that thread's partition.

    The thread_id is stored as a field in the Cosmos DB document for
    partitioning and filtering, but it is NOT mapped back to the
    WorkflowCheckpoint dataclass during deserialization (since
    WorkflowCheckpoint has no thread_id field).

    Attributes:
        _client: Cosmos DB async client (injected by DI container).
        _thread_id: Conversation thread ID used as partition key.
        _database_name: Name of the Cosmos DB database.
        _container_name: Name of the container for checkpoint documents.
        _container: Cached reference to the Cosmos DB container proxy.
    """

    def __init__(
        self,
        cosmos_client: CosmosClient,
        thread_id: str,
        database_name: str = "agent_workflows",
        container_name: str = "checkpoints",
    ):
        """Initialize the Cosmos DB checkpoint store.

        Args:
            cosmos_client: An existing CosmosClient instance (provided by the DI container).
            thread_id: Conversation thread ID — used as the Cosmos DB partition key.
            database_name: Name of the database to use.
            container_name: Name of the container for checkpoints.
        """
        self._client = cosmos_client
        self._thread_id = thread_id
        self._database_name = database_name
        self._container_name = container_name
        self._container: ContainerProxy | None = None

    async def initialize(self) -> None:
        """Create the database and container if they don't exist.

        Must be called before any other operations, typically during
        application startup.
        """
        database = await self._client.create_database_if_not_exists(self._database_name)
        self._container = await database.create_container_if_not_exists(
            id=self._container_name,
            partition_key=PartitionKey(path="/thread_id"),
        )
        logger.info(
            f"Initialized Cosmos DB checkpoint storage: "
            f"database={self._database_name}, container={self._container_name}"
        )

    def _get_container(self) -> ContainerProxy:
        """Get the container proxy, raising if not initialized."""
        if self._container is None:
            raise WorkflowCheckpointException(
                "CosmosDBCheckpointStorage not initialized. Call initialize() first."
            )
        return self._container

    def _serialize_checkpoint(self, checkpoint: WorkflowCheckpoint) -> dict[str, Any]:
        """Serialize a WorkflowCheckpoint to a Cosmos DB document.

        Adds thread_id to the document for partition key routing.
        Complex Python objects in the checkpoint state (e.g., messages,
        pending events) are pickled and base64-encoded for safe JSON storage.

        Args:
            checkpoint: The checkpoint to serialize.

        Returns:
            A JSON-serializable dictionary suitable for Cosmos DB.
        """
        doc = {
            "id": checkpoint.checkpoint_id,
            "thread_id": self._thread_id,  # Partition key — NOT a WorkflowCheckpoint field
            "workflow_name": checkpoint.workflow_name,
            "graph_signature_hash": checkpoint.graph_signature_hash,
            "previous_checkpoint_id": checkpoint.previous_checkpoint_id,
            "timestamp": checkpoint.timestamp,
            "iteration_count": checkpoint.iteration_count,
            "metadata": checkpoint.metadata,
            "version": checkpoint.version,
            # Pickle complex fields that may contain non-JSON-serializable objects
            "messages_b64": base64.b64encode(pickle.dumps(checkpoint.messages)).decode("utf-8"),
            "state_b64": base64.b64encode(pickle.dumps(checkpoint.state)).decode("utf-8"),
            "pending_request_info_events_b64": base64.b64encode(
                pickle.dumps(checkpoint.pending_request_info_events)
            ).decode("utf-8"),
        }
        return doc

    @staticmethod
    def _deserialize_checkpoint(doc: dict[str, Any]) -> WorkflowCheckpoint:
        """Deserialize a Cosmos DB document back to a WorkflowCheckpoint.

        The thread_id field present in the document is intentionally
        NOT passed to WorkflowCheckpoint — it is a Cosmos DB partitioning
        concern, not part of the agent framework's checkpoint model.

        Args:
            doc: The Cosmos DB document.

        Returns:
            A reconstructed WorkflowCheckpoint instance (without thread_id).
        """
        return WorkflowCheckpoint(
            workflow_name=doc["workflow_name"],
            graph_signature_hash=doc["graph_signature_hash"],
            checkpoint_id=doc["id"],
            previous_checkpoint_id=doc.get("previous_checkpoint_id"),
            timestamp=doc["timestamp"],
            messages=pickle.loads(base64.b64decode(doc["messages_b64"])),
            state=pickle.loads(base64.b64decode(doc["state_b64"])),
            pending_request_info_events=pickle.loads(
                base64.b64decode(doc["pending_request_info_events_b64"])
            ),
            iteration_count=doc.get("iteration_count", 0),
            metadata=doc.get("metadata", {}),
            version=doc.get("version", "1.0"),
        )

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Save a checkpoint to Cosmos DB.

        Uses upsert to allow both create and update operations.
        The document is automatically routed to the thread_id partition.

        Args:
            checkpoint: The WorkflowCheckpoint to save.

        Returns:
            The checkpoint ID of the saved document.
        """
        container = self._get_container()
        doc = self._serialize_checkpoint(checkpoint)
        await container.upsert_item(doc)
        logger.debug(f"Saved checkpoint {checkpoint.checkpoint_id} to Cosmos DB (thread={self._thread_id})")
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a checkpoint by ID within this thread's partition.

        Args:
            checkpoint_id: The ID of the checkpoint to load.

        Returns:
            The loaded WorkflowCheckpoint.

        Raises:
            WorkflowCheckpointException: If the checkpoint is not found.
        """
        container = self._get_container()
        try:
            query = "SELECT * FROM c WHERE c.id = @id AND c.thread_id = @thread_id"
            params = [
                {"name": "@id", "value": checkpoint_id},
                {"name": "@thread_id", "value": self._thread_id},
            ]
            items = [
                item async for item in container.query_items(
                    query=query,
                    parameters=params,
                    partition_key=self._thread_id,
                )
            ]
            if not items:
                raise WorkflowCheckpointException(
                    f"No checkpoint found with ID {checkpoint_id} in thread {self._thread_id}"
                )
            return self._deserialize_checkpoint(items[0])
        except exceptions.CosmosResourceNotFoundError:
            raise WorkflowCheckpointException(
                f"No checkpoint found with ID {checkpoint_id} in thread {self._thread_id}"
            )

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List all checkpoints for a workflow within this thread's partition.

        Args:
            workflow_name: The workflow name to filter by.

        Returns:
            A list of WorkflowCheckpoint objects.
        """
        container = self._get_container()
        query = "SELECT * FROM c WHERE c.workflow_name = @name AND c.thread_id = @thread_id"
        params = [
            {"name": "@name", "value": workflow_name},
            {"name": "@thread_id", "value": self._thread_id},
        ]
        items = [
            item async for item in container.query_items(
                query=query,
                parameters=params,
                partition_key=self._thread_id,
            )
        ]
        return [self._deserialize_checkpoint(item) for item in items]

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        """Delete a checkpoint by ID within this thread's partition.

        Args:
            checkpoint_id: The ID of the checkpoint to delete.

        Returns:
            True if deleted, False if not found.
        """
        container = self._get_container()
        try:
            await container.delete_item(
                item=checkpoint_id,
                partition_key=self._thread_id,
            )
            logger.debug(f"Deleted checkpoint {checkpoint_id} from Cosmos DB (thread={self._thread_id})")
            return True
        except exceptions.CosmosResourceNotFoundError:
            return False

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Get the latest checkpoint for a workflow within this thread's partition.

        Uses Cosmos DB ORDER BY to retrieve the most recent checkpoint
        based on the ISO 8601 timestamp.

        Args:
            workflow_name: The workflow name to filter by.

        Returns:
            The latest checkpoint, or None if no checkpoints exist.
        """
        container = self._get_container()
        query = (
            "SELECT * FROM c WHERE c.workflow_name = @name AND c.thread_id = @thread_id "
            "ORDER BY c.timestamp DESC OFFSET 0 LIMIT 1"
        )
        params = [
            {"name": "@name", "value": workflow_name},
            {"name": "@thread_id", "value": self._thread_id},
        ]
        items = [
            item async for item in container.query_items(
                query=query,
                parameters=params,
                partition_key=self._thread_id,
            )
        ]
        if not items:
            return None
        latest = self._deserialize_checkpoint(items[0])
        logger.debug(
            f"Latest checkpoint for workflow {workflow_name} (thread={self._thread_id}): "
            f"{latest.checkpoint_id}"
        )
        return latest

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        """List checkpoint IDs for a workflow within this thread's partition.

        Args:
            workflow_name: The workflow name to filter by.

        Returns:
            A list of checkpoint IDs.
        """
        container = self._get_container()
        query = "SELECT c.id FROM c WHERE c.workflow_name = @name AND c.thread_id = @thread_id"
        params = [
            {"name": "@name", "value": workflow_name},
            {"name": "@thread_id", "value": self._thread_id},
        ]
        items = [
            item async for item in container.query_items(
                query=query,
                parameters=params,
                partition_key=self._thread_id,
            )
        ]
        return [item["id"] for item in items]
```

#### Step 3: Update the Handoff Orchestrator

Update `app/backend/app/agents/azure_chat/handoff_orchestrator.py` to receive a `CosmosDBCheckpointStorage` instance via dependency injection instead of creating stores internally.

##### 3.1: Update Imports

```python
# Before
from agent_framework import CheckpointStorage, InMemoryCheckpointStorage

# After
from agent_framework import CheckpointStorage
from app.common.cosmosdb_checkpoint_store import CosmosDBCheckpointStorage
```

##### 3.2: Update the Constructor

Accept the `CosmosClient` and Cosmos DB configuration via dependency injection. The orchestrator will create per-thread `CosmosDBCheckpointStorage` instances using these:

```python
class HandoffOrchestrator:

    thread_checkpoint_store: dict[str, CheckpointStorage] = {}

    def __init__(self, 
                 azure_chat_client: AzureOpenAIChatClient,
                 account_agent: AccountAgent,
                 transaction_agent: TransactionHistoryAgent,
                 payment_agent: PaymentAgent,
                 cosmos_client: CosmosClient,                          # NEW — injected by DI
                 cosmos_db_database: str = "agent_workflows",          # NEW
                 cosmos_db_container: str = "checkpoints",             # NEW
                ):
        self.azure_chat_client = azure_chat_client
        self.account_agent = account_agent
        self.transaction_agent = transaction_agent
        self.payment_agent = payment_agent
        self.cosmos_client = cosmos_client
        self.cosmos_db_database = cosmos_db_database
        self.cosmos_db_container = cosmos_db_container
        self.workflow = None
```

##### 3.3: Create Per-Thread Checkpoint Stores

Each thread gets its own `CosmosDBCheckpointStorage` instance bound to that `thread_id`. All instances share the same DI-managed `CosmosClient` and target the same Cosmos DB container — the `thread_id` partition key isolates data per conversation:

```python
async def _get_or_create_checkpoint_store(self, thread_id: str) -> CheckpointStorage:
    checkpoint_storage = HandoffOrchestrator.thread_checkpoint_store.get(thread_id, None)
    if checkpoint_storage is not None:
        return checkpoint_storage

    logger.info(f"Creating checkpoint storage for thread_id: {thread_id}")
    checkpoint_storage = CosmosDBCheckpointStorage(
        cosmos_client=self.cosmos_client,
        thread_id=thread_id,
        database_name=self.cosmos_db_database,
        container_name=self.cosmos_db_container,
    )
    await checkpoint_storage.initialize()
    HandoffOrchestrator.thread_checkpoint_store[thread_id] = checkpoint_storage
    return checkpoint_storage
```

##### 3.4: No Changes to `initialize()` or `processMessageStream()`

The `HandoffBuilder.with_checkpointing(checkpoint_storage)` call and the workflow's `run()` method both accept any `CheckpointStorage` implementation, so the rest of the orchestrator code remains unchanged:

```python
async def initialize(self, checkpoint_storage: CheckpointStorage):
    """Initialize the workflow — works with any CheckpointStorage implementation."""
    triage_agent = Agent(
        client=self.azure_chat_client,
        instructions=HandoffOrchestrator.triage_instructions,
        name="triage_agent"
    )

    self.workflow = (
        HandoffBuilder(
            name="banking_assistant_handoff",
            participants=[triage_agent, 
                          await self.account_agent.build_af_agent(),
                          await self.transaction_agent.build_af_agent(),
                          await self.payment_agent.build_af_agent()],
        )
        .with_start_agent(triage_agent)
        .with_termination_condition(
            lambda conv: sum(1 for msg in conv if msg.role == "user") >= 20
        )
        .with_checkpointing(checkpoint_storage)  # ← Accepts any CheckpointStorage
        .build()
    )
```

#### Step 4: Update Configuration Settings

Add Cosmos DB checkpoint configuration to `app/backend/app/config/settings.py`:

```python
# In settings.py
COSMOS_DB_CHECKPOINT_ENDPOINT: str = Field(
    default="https://localhost:8081",
    description="Azure Cosmos DB endpoint URL for workflow checkpoints"
)
COSMOS_DB_CHECKPOINT_DATABASE: str = Field(
    default="agent_workflows",
    description="Cosmos DB database name for workflow checkpoints"
)
```

Set the environment variables or add them to your `.env` file:

```env
COSMOS_DB_CHECKPOINT_ENDPOINT=https://your-cosmosdb-account.documents.azure.com:443/
COSMOS_DB_CHECKPOINT_DATABASE=agent_workflows
```

#### Step 5: Update the Dependency Injection Container

Register the Cosmos DB client in `app/backend/app/config/container_azure_chat.py` and pass it to the orchestrator. The `CosmosDBCheckpointStorage` instances are created per-thread by the orchestrator at runtime (since each needs a different `thread_id`).

##### 5.1: Add Imports

At the top of the file, add:

```python
from azure.cosmos.aio import CosmosClient
```

##### 5.2: Register the Cosmos DB Client in the Container

Add the `CosmosClient` as a `Singleton` provider inside the `Container` class — one connection pool shared across the app:

```python
class Container(containers.DeclarativeContainer):
    """IoC container for application dependencies."""

    # ... existing providers ...

    # Cosmos DB async client for workflow checkpoint persistence
    cosmos_client = providers.Singleton(
        CosmosClient,
        url=settings.COSMOS_DB_CHECKPOINT_ENDPOINT,
        credential=providers.Factory(get_azure_credential_async),
    )
```

##### 5.3: Wire the Client into the Orchestrator

Update the `handoff_orchestrator_chatkit` factory to inject the `CosmosClient` and the database/container config. The orchestrator will create per-thread `CosmosDBCheckpointStorage` instances internally:

```python
    # A specialized chatkit Supervisor Agent implemented using agent framework handoff built-in orchestration
    handoff_orchestrator_chatkit = providers.Factory(
        HandoffOrchestratorChatKit,
        azure_chat_client=_azure_chat_client,
        account_agent=account_agent_chatkit,
        transaction_agent=transaction_agent_chatkit,
        payment_agent=payment_agent_chatkit,
        cosmos_client=cosmos_client,                                     # NEW — DI-managed singleton
        cosmos_db_database=settings.COSMOS_DB_CHECKPOINT_DATABASE,       # NEW
        cosmos_db_container="checkpoints",                               # NEW
    )
```

#### Step 6: Handle Application Lifecycle

Close the Cosmos DB client on shutdown. In `app/backend/app/main_chatkit_server.py`:

```python
from contextlib import asynccontextmanager
from app.config.container_azure_chat import Container

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — checkpoint stores initialize lazily per thread
    yield
    # Shutdown — close the Cosmos DB client to release connections
    cosmos_client = Container.cosmos_client()
    await cosmos_client.close()

app = FastAPI(lifespan=lifespan)
```

#### Key Takeaways

- **`CheckpointStorage` protocol**: Implement all six async methods (`save`, `load`, `list_checkpoints`, `delete`, `get_latest`, `list_checkpoint_ids`) — the `HandoffBuilder` and workflow engine use these to persist and restore state between turns.
- **Serialization strategy**: Workflow checkpoints contain complex Python objects (agent messages, pending events). The example uses pickle + base64 encoding to store them as strings within JSON documents. Only load checkpoints from trusted sources.
- **Partition key**: Using `thread_id` as the Cosmos DB partition key keeps all checkpoints for a conversation co-located. Every query is scoped to a single thread’s partition, ensuring efficient reads and strong data isolation between conversations.
- **thread_id is a store concern, not a checkpoint concern**: The `thread_id` field is written to the Cosmos DB document for partitioning and filtering, but it is intentionally NOT passed to `WorkflowCheckpoint` during deserialization — the agent framework’s checkpoint model has no notion of thread identity.
- **Drop-in replacement**: Because `HandoffBuilder.with_checkpointing()` accepts any `CheckpointStorage` implementation, you can swap `InMemoryCheckpointStorage` for Cosmos DB (or Redis, PostgreSQL, etc.) without modifying the workflow, agents, or ChatKit protocol layer.
- **Dependency injection**: The `CosmosClient` is registered as a `Singleton` provider in the DI container (`container_azure_chat.py`), following the same pattern used for `BlobServiceClient` and `DocumentIntelligenceClient`. The orchestrator receives this shared client and creates per-thread `CosmosDBCheckpointStorage` instances at runtime (since each needs a different `thread_id`).
- **Async initialization**: Each `CosmosDBCheckpointStorage` instance calls `initialize()` to ensure the Cosmos DB database and container exist. This is idempotent — subsequent calls for other threads are no-ops if the container already exists.
