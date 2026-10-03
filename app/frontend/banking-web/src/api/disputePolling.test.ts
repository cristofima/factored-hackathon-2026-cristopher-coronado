import { afterEach, expect, it, vi } from "vitest";
import { startDisputePolling } from "./disputePolling";
import { getSupportCaseDetail } from "./disputeClient";

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

it("waits for each request before scheduling another and aborts on cleanup", async () => {
    vi.useFakeTimers();
    let finish: (() => void) | undefined;
    const request = vi.fn((_signal: AbortSignal) => new Promise<void>((resolve) => {
        finish = resolve;
    }));
    const stop = startDisputePolling(request);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(request).toHaveBeenCalledTimes(1);
    finish?.();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(request).toHaveBeenCalledTimes(2);
    const signal = request.mock.calls[1][0];
    stop();
    expect(signal.aborted).toBe(true);
    finish?.();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(request).toHaveBeenCalledTimes(2);
});

it("clears a scheduled refresh when stopped", async () => {
    vi.useFakeTimers();
    const request = vi.fn(async () => undefined);
    const stop = startDisputePolling(request);
    await vi.advanceTimersByTimeAsync(0);
    stop();
    await vi.advanceTimersByTimeAsync(20_000);
    expect(request).toHaveBeenCalledTimes(1);
});

it("waits for a pending timeline after the case read fails before retrying", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("localStorage", { getItem: () => "synthetic-test-only" });
    let finishTimeline: ((response: Response) => void) | undefined;
    const fetchMock = vi.fn()
        .mockRejectedValueOnce(new Error("Controlled read failure"))
        .mockImplementationOnce(() => new Promise<Response>((resolve) => {
            finishTimeline = resolve;
        }))
        .mockResolvedValue(new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const errors: unknown[] = [];
    const stop = startDisputePolling(async (signal) => {
        try {
            await getSupportCaseDetail("SYNTHETIC-CASE", signal);
        } catch (error) {
            errors.push(error);
        }
    });
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(errors).toHaveLength(0);
    finishTimeline?.(new Response("[]", { status: 200 }));
    await vi.advanceTimersByTimeAsync(0);
    expect(errors).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    stop();
});