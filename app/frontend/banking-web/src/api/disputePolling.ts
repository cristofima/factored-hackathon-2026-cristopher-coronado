export function startDisputePolling(
    request: (signal: AbortSignal) => Promise<void>,
): () => void {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
        try {
            await request(controller.signal);
        } finally {
            if (!controller.signal.aborted) timer = setTimeout(poll, 10_000);
        }
    };

    void poll();
    return () => {
        controller.abort();
        clearTimeout(timer);
    };
}