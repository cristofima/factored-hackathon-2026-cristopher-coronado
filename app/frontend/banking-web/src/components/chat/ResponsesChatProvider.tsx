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
import { useTranslation } from "react-i18next";
import { readToolCase, readToolPreview, toolOutputFailed, toolProgressKey, type ToolOutputItem } from "./responseItems";

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
  [key: string]: unknown;
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
  const assistantItemsRef = useRef(new Map<string, string>());
  const visibleOutputRef = useRef(false);
  const reportedErrorRef = useRef(false);
  const lastMessageRef = useRef<string | null>(null);
  const { t } = useTranslation();
  const toolCallsRef = useRef(new Map<string, { id: string; name: string }>());
  const streamOutcomeRef = useRef<"success" | "error" | "cancelled">("error");
  const actionRef = useRef<((outcome: "success" | "error" | "cancelled") => void) | null>(null);
  const completedApprovalsRef = useRef(new Set<string>());
  const streamFailedRef = useRef(false);

  useEffect(() => () => {
    const settle = actionRef.current;
    actionRef.current = null;
    settle?.("cancelled");
  }, []);

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
        [threadId]: (previous[threadId] ?? []).some((existing) => existing.id === item.id)
          ? (previous[threadId] ?? []).map((existing) => existing.id === item.id ? item : existing)
          : [...(previous[threadId] ?? []), item],
      }));
      onThreadItemAdded?.(item);
    },
    [onThreadItemAdded],
  );

  const reportStreamError = useCallback((threadId: string, code = "SERVICE_UNAVAILABLE", allowRetry = true, httpStatus?: number) => {
    if (reportedErrorRef.current) return;
    reportedErrorRef.current = true;
    const message = t(code === "AUTH_REQUIRED" ? "Session expired"
      : code === "ACCESS_DENIED" ? "Access denied" : "The response could not be completed.");
    addItem(threadId, {
      id: generateId("error"), thread_id: threadId, created_at: now(),
      type: "error", code, message, allow_retry: allowRetry, http_status: httpStatus,
    });
    onError?.({ message, code: code === "stream_error" ? "SERVICE_UNAVAILABLE" : code, threadId });
  }, [addItem, onError, t]);

  const handleTextDelta = useCallback((threadId: string, delta: string, outputId?: string) => {
    if (!delta) return;
    const key = outputId === undefined ? "fallback" : `output:${outputId}`;
    const itemId = assistantItemsRef.current.get(key) ?? generateId("assistant");
    assistantItemsRef.current.set(key, itemId);
    if (delta.trim()) visibleOutputRef.current = true;
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

      visibleOutputRef.current = true;
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
      if (event.type === "response.completed") {
        if (!streamFailedRef.current) streamOutcomeRef.current = "success";
        return;
      }
      if (event.type === "response.incomplete") {
        streamOutcomeRef.current = "error";
        streamFailedRef.current = true;
      }

      if (
        event.type === "response.output_text.delta" &&
        typeof event.delta === "string"
      ) {
        setHasReceivedStreamEvent(true);
        const outputId = typeof event.item_id === "string" ? event.item_id
          : typeof event.message_id === "string" ? event.message_id : undefined;
        handleTextDelta(threadId, event.delta, outputId);
        return;
      }

      if (event.type === "response.output_item.added" || event.type === "response.output_item.done") {
        const item = event.item as ToolOutputItem | undefined;
        if (item?.type === "mcp_approval_request" && item.id) {
          setHasReceivedStreamEvent(true);
          handleApprovalRequest(threadId, item as ApprovalRequest);
          return;
        }
        if (!item) return;
        const callId = item.call_id ?? item.id;
        const key = toolProgressKey(item.name);
        if (event.type === "response.output_item.added" &&
          (item.type === "function_call" || item.type === "mcp_call") && callId && key &&
          !toolCallsRef.current.has(callId)) {
          const taskId = `tool_${threadId}_${callId}`;
          toolCallsRef.current.set(callId, { id: taskId, name: key });
          addItem(threadId, {
            id: taskId, thread_id: threadId, created_at: now(), type: "task",
            task: { type: "custom", title: t(key), status_indicator: "loading" },
          });
        }
        // A call declaration or outputless MCP completion is not a successful result.
        if (event.type === "response.output_item.done" && (item.output !== undefined || item.error)) {
          const failed = Boolean(item.error) || toolOutputFailed(item.output);
          if (failed) {
            streamOutcomeRef.current = "error";
            streamFailedRef.current = true;
          }
          const call = callId ? toolCallsRef.current.get(callId) : undefined;
          if (call) {
            if (failed) {
              addItem(threadId, {
                id: call.id, thread_id: threadId, created_at: now(), type: "task",
                task: { type: "custom", title: t("Tool result unavailable"), status_indicator: "none" },
              });
            } else {
              setThreadItems((previous) => ({
                ...previous,
                [threadId]: (previous[threadId] ?? []).filter((entry) => entry.id !== call.id),
              }));
            }
          }
          const preview = !item.error ? readToolPreview(item.output) : null;
          if (preview && call) {
            visibleOutputRef.current = true;
            addItem(threadId, {
              id: `preview_${threadId}_${call.id}`, thread_id: threadId,
              created_at: now(), type: "client_widget", name: "dispute_preview",
              args: { preview },
            });
          }
          const supportCase = !item.error ? readToolCase(item.output) : null;
          if (supportCase) visibleOutputRef.current = true;
          if (supportCase?.status === "WAITING_USER_APPROVAL") {
            addItem(threadId, {
              id: `consent_${threadId}_${supportCase.caseId}`, thread_id: threadId,
              created_at: now(), type: "client_widget", name: "dispute_consent",
              args: { caseId: supportCase.caseId },
            });
          }
        }
        return;
      }

      if (event.type === "error" || event.type === "response.failed") {
        streamOutcomeRef.current = "error";
        streamFailedRef.current = true;
        const responseError = (
          event.response as
            | { error?: { message?: string; code?: string } }
            | undefined
        )?.error;
        const receivedCode = event.code ?? responseError?.code;
        const code = receivedCode === "AUTH_REQUIRED" || receivedCode === "ACCESS_DENIED"
          ? receivedCode : "SERVICE_UNAVAILABLE";
        reportStreamError(threadId, code, Boolean(event.allow_retry),
          typeof event.http_status === "number" ? event.http_status : undefined);
      }
    },
    [addItem, handleApprovalRequest, handleTextDelta, reportStreamError, t],
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
    if (!threadId) return;
    if (!visibleOutputRef.current && streamOutcomeRef.current !== "cancelled") {
      streamOutcomeRef.current = "error";
      streamFailedRef.current = true;
      reportStreamError(threadId);
    }
    const assistantItemIds = new Set(assistantItemsRef.current.values());
    if (threadId) {
      setThreadItems((previous) => ({
        ...previous,
        [threadId]: (previous[threadId] ?? []).map((item) =>
          item.type === "task" && item.task.type === "custom" && item.task.status_indicator === "loading"
            ? { ...item, task: { ...item.task, title: t("Tool result unavailable"), status_indicator: "none" } }
            : item,
        ),
      }));
      toolCallsRef.current.clear();
    }
    if (assistantItemIds.size) {
      setThreadItems((previous) => ({
        ...previous,
        [threadId]: (previous[threadId] ?? []).map((item) =>
          assistantItemIds.has(item.id) && item.type === "assistant_message"
            ? { ...item, streaming: false }
            : item,
        ),
      }));
    }
    setIsStreaming(false);
    setCurrentRequest(null);
    assistantItemsRef.current.clear();
    streamingThreadRef.current = null;
    const settle = actionRef.current;
    actionRef.current = null;
    settle?.(streamOutcomeRef.current);
    onResponseEnd?.(threadId);
  }, [onResponseEnd, reportStreamError, t]);

  const { cancel } = useThreadStream({
    url: chatServerUrl ?? "/responses",
    request: currentRequest,
    onEvent: handleStreamEvent,
    onConversation: handleConversation,
    onError: () => {
      streamOutcomeRef.current = "error";
      streamFailedRef.current = true;
      const threadId = streamingThreadRef.current;
      if (threadId) reportStreamError(threadId, "stream_error");
      finishStream();
    },
    onComplete: finishStream,
    enabled: currentRequest !== null,
    retryConfig,
  });

  const submitInput = useCallback(
    (threadId: string, input: unknown) => {
      if (streamingThreadRef.current) return;
      streamOutcomeRef.current = "error";
      streamFailedRef.current = false;
      toolCallsRef.current.clear();
      const conversationId = threads.find((thread) => thread.id === threadId)
        ?.metadata?.conversationId;
      streamingThreadRef.current = threadId;
      assistantItemsRef.current.clear();
      visibleOutputRef.current = false;
      reportedErrorRef.current = false;
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
      if (!trimmed || streamingThreadRef.current) return;
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
    (threadId: string, itemId: string, action: ActionConfig): Promise<"success" | "error" | "cancelled"> => {
      const key = `${threadId}:${itemId}`;
      if (completedApprovalsRef.current.has(key)) return Promise.resolve("success");
      const widget = (threadItems[threadId] ?? []).find((item) => item.id === itemId && item.type === "client_widget");
      const previewDecision = widget?.type === "client_widget" && widget.name === "dispute_preview" && action.type === "dispute_preview_decision";
      const approval = widget?.type === "client_widget" && widget.name === "tool_approval_request" && action.type === "approval";
      if (streamingThreadRef.current || (!previewDecision && !approval)) return Promise.resolve("error");
      if (previewDecision && action.payload?.declined !== true && typeof action.payload?.caseId !== "string") return Promise.resolve("error");
      const result = new Promise<"success" | "error" | "cancelled">((resolve) => {
        actionRef.current = (outcome) => {
          if (outcome === "success") completedApprovalsRef.current.add(key);
          resolve(outcome);
        };
      });
      submitInput(threadId, previewDecision ? [{
        role: "user", content: [{ type: "input_text", text: action.payload?.declined === true
          ? "I declined the dispute proposal. Do not create a support case."
          : `I explicitly consented to creation and human review. The authenticated application already recorded support case ${action.payload?.caseId}. Do not create another dispute; acknowledge the recorded request without claiming financial effects.` }],
      }] : [{
        type: "mcp_approval_response", approval_request_id: itemId,
        approve: Boolean(action?.payload?.approved),
      }]);
      return result;
    },
    [submitInput, threadItems],
  );

  const createThread = useCallback(
    (initialMessage?: string) => {
      if (streamingThreadRef.current) return;
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
      streamOutcomeRef.current = "cancelled";
      cancel();
      finishStream();
    },
    retryLastMessage: () => {
      if (lastMessageRef.current) sendMessage(lastMessageRef.current);
    },
    sendWidgetAction,
    isApprovalCompleted: (threadId, itemId) => completedApprovalsRef.current.has(`${threadId}:${itemId}`),
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
