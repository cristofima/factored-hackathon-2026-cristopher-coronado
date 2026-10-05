/**
 * Utility functions for client-managed widgets
 * 
 * These utilities help client-managed widgets send Responses approval events
 * and format display data.
 */

import { useChat } from "@/components/chat/ResponsesChatProvider";
import { useCallback, useEffect, useRef } from "react";

/**
 * Callbacks for widget action lifecycle events
 */
export interface WidgetActionCallbacks {
  onThreadStarted?: () => void;
  onThreadEnded?: () => void;
  onError?: (error: { message: string; code?: string }) => void;
}

/**
 * Hook to send widget actions as Responses MCP approval events with lifecycle callbacks
 * 
 * @param callbacks - Optional callbacks for action lifecycle events
 * @returns Function to send actions with proper context
 * 
 * @example
 * const sendWidgetAction = useSendWidgetAction({
 *   onThreadStarted: () => console.log('Thread started'),
 *   onThreadEnded: () => console.log('Thread ended'),
 *   onError: (error) => console.error('Error:', error)
 * });
 * sendWidgetAction(itemId, { type: "approval", payload: {...} });
 */
export function useSendWidgetAction(callbacks?: WidgetActionCallbacks) {
  const { sendWidgetAction, activeThreadId } = useChat();
  const callbacksRef = useRef(callbacks);
  const pendingRef = useRef(false);
  const mountedRef = useRef(true);
  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  return useCallback(async (itemId: string, action: {
    type: string;
    payload?: Record<string, unknown>;
    handler?: "server" | "client";
    loadingBehavior?: "auto" | "manual";
  }) => {
    if (pendingRef.current) return;
    if (!activeThreadId) {
      callbacksRef.current?.onError?.({
        message: "No active thread - cannot send widget action",
        code: "NO_ACTIVE_THREAD"
      });
      return;
    }

    pendingRef.current = true;
    callbacksRef.current?.onThreadStarted?.();

    // Format action with defaults
    const formattedAction = {
      type: action.type,
      payload: action.payload || {},
      handler: action.handler || "server",
      loadingBehavior: action.loadingBehavior || "auto",
    };

    try {
      const outcome = await sendWidgetAction(activeThreadId, itemId, formattedAction);
      if (!mountedRef.current) return;
      if (outcome === "success") callbacksRef.current?.onThreadEnded?.();
      else callbacksRef.current?.onError?.({ message: "Approval response not completed" });
    } catch {
      if (mountedRef.current) callbacksRef.current?.onError?.({ message: "Approval response not completed" });
    } finally {
      pendingRef.current = false;
    }
  }, [sendWidgetAction, activeThreadId]);
}

/**
 * Format object as Python-style string representation
 * Useful for displaying arguments in code blocks
 * @param obj - Object to format
 * @returns Python-style string
 */
export function formatAsPython(obj: unknown): string {
  return JSON.stringify(obj, null, 2)
    .replace(/"/g, "'")
    .replace(/null/g, "None")
    .replace(/true/g, "True")
    .replace(/false/g, "False");
}

/**
 * Create a markdown code block with Python syntax
 * @param content - Content to display in code block
 * @returns Markdown formatted code block
 */
export function createPythonCodeBlock(content: string): string {
  return `\`\`\`py\n${content}\n\`\`\``;
}
