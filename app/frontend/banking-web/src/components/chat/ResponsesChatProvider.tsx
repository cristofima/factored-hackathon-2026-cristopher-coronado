import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  widgetRegistry,
  type ClientWidgetComponent,
} from "@/components/chat/widgets";
import type { ActionConfig } from "@/components/chat/widgets/types";
import type {
  AttachmentMeta,
  ChatContextValue,
  ComposerConfig,
  RetryConfig,
  ShellContainerConfig,
  StarterPrompt,
  Thread,
  ThreadItem,
  WelcomeHeaderConfig,
} from "./types";
import { useThreadStream, type StreamEvent } from "./useThreadStream";

const ChatContext = createContext<ChatContextValue | undefined>(undefined);
const generateId = (prefix: string) => `${prefix}_${crypto.randomUUID()}`;
const now = () => new Date().toISOString();

interface ChatProviderProps {
  children: React.ReactNode;
  starterPrompts?: StarterPrompt[];
  chatServerUrl?: string;
  threadListLimit?: number;
  threadListOrder?: "asc" | "desc";
  retryConfig?: RetryConfig;
  attachmentImageSize?: "sm" | "md" | "lg";
  maxVisibleAttachments?: number;
  composerConfig?: ComposerConfig;
  customWidgets?: Record<string, ClientWidgetComponent>;
  welcomeHeaderConfig?: WelcomeHeaderConfig;
  shellContainerConfig?: ShellContainerConfig;
  onAttachmentAdded?: (attachment: AttachmentMeta) => void;
  onAttachmentRemoved?: (attachmentId: string) => void;
  onThreadCreated?: (thread: Thread) => void;
  onThreadStarted?: (threadId: string) => void;
  onThreadItemAdded?: (item: ThreadItem) => void;
  onResponseEnd?: (threadId: string) => void;
  onMessageSent?: (message: {
    text: string;
    attachments?: AttachmentMeta[];
  }) => void;
  onError?: (error: {
    message: string;
    code?: string;
    threadId?: string;
  }) => void;
}

interface ApprovalRequest {
  id: string;
  type: "mcp_approval_request";
  name?: string;
  server_label?: string;
  arguments?: string | Record<string, unknown>;
}

interface ResponsesRequest {
  threadId: string;
  payload: Record<string, unknown>;
}

export function ChatProvider({
  children,
  starterPrompts = [],
  chatServerUrl,
  retryConfig,
  attachmentImageSize = "lg",
  maxVisibleAttachments = 3,
  composerConfig,
  customWidgets,
  welcomeHeaderConfig,
  shellContainerConfig,
  onThreadCreated,
  onThreadStarted,
  onThreadItemAdded,
  onResponseEnd,
  onMessageSent,
  onError,
}: ChatProviderProps) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [threadItems, setThreadItems] = useState<Record<string, ThreadItem[]>>(
    {},
  );
  const [currentRequest, setCurrentRequest] = useState<ResponsesRequest | null>(
    null,
  );
  const [isStreaming, setIsStreaming] = useState(false);
  const [hasReceivedStreamEvent, setHasReceivedStreamEvent] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const streamingThreadRef = useRef<string | null>(null);
  const assistantItemRef = useRef<string | null>(null);
  const lastMessageRef = useRef<string | null>(null);

  useEffect(() => {
    Object.entries(customWidgets ?? {}).forEach(([name, component]) => {
      widgetRegistry.register(name, component);
    });
  }, [customWidgets]);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId),
    [activeThreadId, threads],
  );
  const items = useMemo(
    () => (activeThreadId ? (threadItems[activeThreadId] ?? []) : []),
    [activeThreadId, threadItems],
  );

  const addItem = useCallback(
    (threadId: string, item: ThreadItem) => {
      setThreadItems((previous) => ({
        ...previous,
        [threadId]: [...(previous[threadId] ?? []), item],
      }));
      onThreadItemAdded?.(item);
    },
    [onThreadItemAdded],
  );

  const handleTextDelta = useCallback((threadId: string, delta: string) => {
    const itemId = assistantItemRef.current ?? generateId("assistant");
    assistantItemRef.current = itemId;
    setThreadItems((previous) => {
      const existing = previous[threadId] ?? [];
      const index = existing.findIndex((item) => item.id === itemId);
      if (index < 0) {
        return {
          ...previous,
          [threadId]: [
            ...existing,
            {
              id: itemId,
              thread_id: threadId,
              created_at: now(),
              type: "assistant_message",
              content: [{ type: "output_text", text: delta, annotations: [] }],
              streaming: true,
            },
          ],
        };
      }

      const updated = [...existing];
      const item = updated[index];
      if (item.type === "assistant_message") {
        updated[index] = {
          ...item,
          content: [{ ...item.content[0], text: item.content[0].text + delta }],
        };
      }
      return { ...previous, [threadId]: updated };
    });
  }, []);

  const handleApprovalRequest = useCallback(
    (threadId: string, request: ApprovalRequest) => {
      let toolArgs: Record<string, unknown> = {};
      if (typeof request.arguments === "string") {
        try {
          toolArgs = JSON.parse(request.arguments) as Record<string, unknown>;
        } catch {
          toolArgs = { raw: request.arguments };
        }
      } else if (request.arguments) {
        toolArgs = request.arguments;
      }

      addItem(threadId, {
        id: request.id,
        thread_id: threadId,
        created_at: now(),
        type: "client_widget",
        name: "tool_approval_request",
        args: {
          tool_name: request.name ?? request.server_label ?? "MCP tool",
          tool_args: toolArgs,
          call_id: request.id,
          request_id: request.id,
        },
      });
    },
    [addItem],
  );

  const handleStreamEvent = useCallback(
    (event: StreamEvent) => {
      const threadId = streamingThreadRef.current;
      if (!threadId) return;
      setHasReceivedStreamEvent(true);

      if (
        event.type === "response.output_text.delta" &&
        typeof event.delta === "string"
      ) {
        handleTextDelta(threadId, event.delta);
        return;
      }

      if (event.type === "response.output_item.added") {
        const item = event.item as ApprovalRequest | undefined;
        if (item?.type === "mcp_approval_request")
          handleApprovalRequest(threadId, item);
        return;
      }

      if (event.type === "error" || event.type === "response.failed") {
        const responseError = (
          event.response as
            | { error?: { message?: string; code?: string } }
            | undefined
        )?.error;
        const message =
          typeof event.message === "string"
            ? event.message
            : (responseError?.message ??
              "The response could not be completed.");
        const code =
          typeof event.code === "string"
            ? event.code
            : (responseError?.code ?? "response_error");
        addItem(threadId, {
          id: generateId("error"),
          thread_id: threadId,
          created_at: now(),
          type: "error",
          code,
          message,
          allow_retry: Boolean(event.allow_retry),
          http_status:
            typeof event.http_status === "number"
              ? event.http_status
              : undefined,
        });
        onError?.({ message, code, threadId });
      }
    },
    [addItem, handleApprovalRequest, handleTextDelta, onError],
  );

  const handleConversation = useCallback(
    (threadId: string, conversationId: string) => {
      setThreads((previous) =>
        previous.map((thread) =>
          thread.id === threadId
            ? { ...thread, metadata: { ...thread.metadata, conversationId } }
            : thread,
        ),
      );
    },
    [],
  );

  const finishStream = useCallback(() => {
    const threadId = streamingThreadRef.current;
    const assistantItemId = assistantItemRef.current;
    if (threadId && assistantItemId) {
      setThreadItems((previous) => ({
        ...previous,
        [threadId]: (previous[threadId] ?? []).map((item) =>
          item.id === assistantItemId && item.type === "assistant_message"
            ? { ...item, streaming: false }
            : item,
        ),
      }));
    }
    setIsStreaming(false);
    setCurrentRequest(null);
    assistantItemRef.current = null;
    streamingThreadRef.current = null;
    if (threadId) onResponseEnd?.(threadId);
  }, [onResponseEnd]);

  const { cancel } = useThreadStream({
    url: chatServerUrl ?? "/responses",
    request: currentRequest,
    onEvent: handleStreamEvent,
    onConversation: handleConversation,
    onError: (error) => {
      const threadId = streamingThreadRef.current;
      if (threadId) {
        addItem(threadId, {
          id: generateId("error"),
          thread_id: threadId,
          created_at: now(),
          type: "error",
          code: "stream_error",
          message: error.message,
          allow_retry: true,
        });
      }
      onError?.({ message: error.message, threadId: threadId ?? undefined });
      finishStream();
    },
    onComplete: finishStream,
    enabled: currentRequest !== null,
    retryConfig,
  });

  const submitInput = useCallback(
    (threadId: string, input: unknown) => {
      const conversationId = threads.find((thread) => thread.id === threadId)
        ?.metadata?.conversationId;
      streamingThreadRef.current = threadId;
      assistantItemRef.current = null;
      setIsStreaming(true);
      setHasReceivedStreamEvent(false);
      setCurrentRequest({
        threadId,
        payload: {
          input,
          stream: true,
          ...(typeof conversationId === "string"
            ? { conversation: conversationId }
            : {}),
        },
      });
    },
    [threads],
  );

  const createLocalThread = useCallback(
    (title: string) => {
      const thread: Thread = {
        id: generateId("thread"),
        title: title.slice(0, 48),
        created_at: now(),
        status: { type: "active" },
      };
      setThreads((previous) => [thread, ...previous]);
      setActiveThreadId(thread.id);
      onThreadCreated?.(thread);
      onThreadStarted?.(thread.id);
      return thread.id;
    },
    [onThreadCreated, onThreadStarted],
  );

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      lastMessageRef.current = trimmed;
      const threadId = activeThreadId ?? createLocalThread(trimmed);

      addItem(threadId, {
        id: generateId("user"),
        thread_id: threadId,
        created_at: now(),
        type: "user_message",
        content: [{ type: "input_text", text: trimmed }],
        attachments: [],
      });
      onMessageSent?.({ text: trimmed });
      submitInput(threadId, [
        { role: "user", content: [{ type: "input_text", text: trimmed }] },
      ]);
    },
    [activeThreadId, addItem, createLocalThread, onMessageSent, submitInput],
  );

  const sendWidgetAction = useCallback(
    (threadId: string, itemId: string, action: ActionConfig) => {
      submitInput(threadId, [
        {
          type: "mcp_approval_response",
          approval_request_id: itemId,
          approve: Boolean(action?.payload?.approved),
        },
      ]);
    },
    [submitInput],
  );

  const createThread = useCallback(
    (initialMessage?: string) => {
      setHistoryOpen(false);
      setHasReceivedStreamEvent(false);
      if (!initialMessage) {
        setActiveThreadId(null);
        return;
      }

      const threadId = createLocalThread(initialMessage);
      lastMessageRef.current = initialMessage;
      addItem(threadId, {
        id: generateId("user"),
        thread_id: threadId,
        created_at: now(),
        type: "user_message",
        content: [{ type: "input_text", text: initialMessage }],
        attachments: [],
      });
      submitInput(threadId, [
        {
          role: "user",
          content: [{ type: "input_text", text: initialMessage }],
        },
      ]);
    },
    [addItem, createLocalThread, submitInput],
  );

  const value: ChatContextValue = {
    threads,
    activeThreadId,
    activeThread,
    items,
    isStreaming,
    hasReceivedStreamEvent,
    historyOpen,
    starterPrompts,
    chatServerUrl,
    progressUpdate: null,
    attachmentImageSize,
    maxVisibleAttachments,
    composerConfig,
    welcomeHeaderConfig,
    shellContainerConfig,
    sendMessage,
    cancelStreaming: () => {
      cancel();
      finishStream();
    },
    retryLastMessage: () => {
      if (lastMessageRef.current) sendMessage(lastMessageRef.current);
    },
    sendWidgetAction,
    createThread,
    selectThread: (threadId) => {
      setActiveThreadId(threadId);
      setHistoryOpen(false);
    },
    toggleHistory: () => setHistoryOpen((open) => !open),
    openHistory: () => setHistoryOpen(true),
    closeHistory: () => setHistoryOpen(false),
    getThreadItems: (threadId) => threadItems[threadId] ?? [],
    onThreadCreated,
    onThreadStarted,
    onThreadItemAdded,
    onResponseEnd,
    onMessageSent,
    onError,
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) throw new Error("useChat must be used within a ChatProvider");
  return context;
};
