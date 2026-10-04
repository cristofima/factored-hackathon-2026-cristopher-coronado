import { useEffect, useRef } from "react";
import { getAuthToken } from "@/api/authToken";
import { readApiError, type ApiErrorCode } from "@/api/errors";
import type { RetryConfig } from "./types";

export interface StreamEvent {
  type: string;
  thread?: unknown;
  item?: unknown;
  icon?: string;
  text?: string;
  stream_options?: unknown;
  message?: string;
  code?: string;
  allow_retry?: boolean;
  http_status?: number;
  response?: unknown;
  delta?: unknown;
}

interface ThreadStreamRequest {
  payload?: unknown;
  threadId?: string;
  type?: string;
  params?: {
    thread_id?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface UseThreadStreamOptions {
  url: string;
  request: ThreadStreamRequest | null;
  onEvent: (event: StreamEvent) => void;
  onConversation?: (threadId: string, conversationId: string) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
  enabled: boolean;
  retryConfig?: RetryConfig;
}

// Default retryable HTTP status codes
const DEFAULT_RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504];

// Convert HTTP error to ErrorEvent format
function createHttpErrorEvent(status: number, code: ApiErrorCode, retryableStatusCodes: number[]): StreamEvent {
  const isRetryable = retryableStatusCodes.includes(status);

  return {
    type: "error",
    code,
    message: code,
    allow_retry: isRetryable,
    http_status: status,
  };
}

/**
 * Custom hook for handling Server-Sent Events (SSE) streaming from the chat server.
 * Automatically manages connection lifecycle and event parsing.
 */
export function useThreadStream({ url, request, onEvent, onConversation, onError, onComplete, enabled, retryConfig }: UseThreadStreamOptions) {
  const abortControllerRef = useRef<AbortController | null>(null);
  const onEventRef = useRef(onEvent);
  const onConversationRef = useRef(onConversation);
  const onErrorRef = useRef(onError);
  const onCompleteRef = useRef(onComplete);
  const retryConfigRef = useRef(retryConfig);

  // Update refs when callbacks change
  useEffect(() => {
    onEventRef.current = onEvent;
    onConversationRef.current = onConversation;
    onErrorRef.current = onError;
    onCompleteRef.current = onComplete;
    retryConfigRef.current = retryConfig;
  });

  useEffect(() => {
    if (!enabled || !request) {
      return;
    }

    // Create a new AbortController for this stream
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const { signal } = controller;
    const token = getAuthToken();
    const isCurrent = () => !signal.aborted && getAuthToken() === token;

    const startStream = async () => {
      try {
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(request.payload ?? request),
          signal,
        });

        if (!isCurrent()) return;

        if (!response.ok) {
          // Convert HTTP error to error event instead of throwing
          const retryableStatusCodes = retryConfigRef.current?.retryableStatusCodes ?? DEFAULT_RETRYABLE_STATUS_CODES;
          const error = await readApiError(response);
          if (!isCurrent()) return;
          const errorEvent = createHttpErrorEvent(response.status, error.code, retryableStatusCodes);

          // Emit the error event so it's handled like SSE errors
          onEventRef.current(errorEvent);

          // Also call onComplete to clean up streaming state
          if (isCurrent()) onCompleteRef.current?.();
          return;
        }

        const conversationId = response.headers.get("X-Conversation-Id");
        if (conversationId && typeof request.threadId === "string") {
          onConversationRef.current?.(request.threadId, conversationId);
        }

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) {
          throw new Error("Response body is not readable");
        }

        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (!isCurrent()) return;

          if (done) {
            onCompleteRef.current?.();
            break;
          }

          // Decode the chunk and add to buffer
          buffer += decoder.decode(value, { stream: true });

          // Process complete messages (lines starting with "data: ")
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // Keep incomplete line in buffer

          for (const line of lines) {
            if (!isCurrent()) return;
            const trimmed = line.trim();

            // SSE events start with "data: "
            if (trimmed.startsWith("data: ")) {
              const jsonStr = trimmed.substring(6); // Remove "data: " prefix

              try {
                const event = JSON.parse(jsonStr) as StreamEvent;
                onEventRef.current(event);
              } catch (parseError) {
                console.error("Failed to parse SSE event:", jsonStr, parseError);
              }
            }
          }
        }
      } catch (error) {
        if (!isCurrent()) return;
        if (error instanceof Error) {
          if (error.name === "AbortError") {
            console.log("Stream aborted");
          } else {
            console.error("Stream error:", error);
            onErrorRef.current?.(error);
          }
        }
      }
    };

    startStream();

    // Cleanup function
    return () => {
      controller.abort();
    };
  }, [url, request, enabled]); // Only depend on url, request, and enabled - callbacks are stable via refs

  // Return cancel function
  const cancel = () => {
    abortControllerRef.current?.abort();
  };

  return { cancel };
}
