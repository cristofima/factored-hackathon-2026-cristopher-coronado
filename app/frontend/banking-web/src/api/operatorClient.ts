import { z } from "zod";
import { getAuthToken } from "@/api/authToken";
import { ApiError, readApiError } from "@/api/errors";

const baseUrl = import.meta.env.VITE_RESPONSES_BFF_URL || "";
const operatorSchema = z.object({
  sub: z.string().trim().min(1),
  email: z.string().email(),
  locale: z.enum(["en", "es", "pt"]),
  name: z.string().nullable().optional(),
  first_name: z.string().min(1).max(50).nullable().optional(),
  last_name: z.string().min(1).max(50).nullable().optional(),
  role: z.literal("operator"),
  identity_version: z.number().int().min(1).safe(),
  customer_id: z.never().optional(),
  status: z.enum(["active", "inactive"]),
  updated_at: z.string().datetime({ offset: true }),
});
export type Operator = z.infer<typeof operatorSchema>;
export const createOperatorSchema = z.object({
  email: z.string().trim().toLowerCase().email().max(120),
  password: z.string().min(12).max(256),
  locale: z.enum(["en", "es", "pt"]),
  first_name: z.string().trim().min(1).max(50),
  last_name: z.string().trim().min(1).max(50),
}).strict();
export const resetPasswordSchema = z.object({ password: z.string().min(12).max(256) }).strict();
export type CreateOperator = z.infer<typeof createOperatorSchema>;
export type OperatorAction = "activate" | "deactivate" | "reset-password";

async function request(path: string, signal: AbortSignal, body?: unknown, method: "GET" | "POST" = "POST"): Promise<Response> {
  const token = getAuthToken();
  if (!token) throw new ApiError("AUTH_REQUIRED");
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal,
  });
  if (!response.ok) throw await readApiError(response);
  signal.throwIfAborted();
  return response;
}

export async function listOperators(signal: AbortSignal): Promise<Operator[]> {
  const response = await request("/admin/operators", signal, undefined, "GET");
  const parsed = z.array(operatorSchema).safeParse(await response.json());
  signal.throwIfAborted();
  if (!parsed.success) throw new ApiError("SERVICE_UNAVAILABLE");
  return parsed.data;
}

export async function createOperator(input: CreateOperator, signal: AbortSignal): Promise<void> {
  const parsed = createOperatorSchema.safeParse(input);
  if (!parsed.success) throw new ApiError("INVALID_REQUEST");
  await request("/admin/operators", signal, parsed.data);
}

export async function changeOperator(userId: string, action: OperatorAction, signal: AbortSignal, password?: string): Promise<void> {
  if (!userId.trim() || [".", ".."].includes(userId) || !["activate", "deactivate", "reset-password"].includes(action)) throw new ApiError("INVALID_REQUEST");
  let body: Record<string, string> | undefined;
  if (action === "reset-password") {
    const parsed = resetPasswordSchema.safeParse({ password });
    if (!parsed.success) throw new ApiError("INVALID_REQUEST");
    body = parsed.data;
  } else if (password !== undefined) throw new ApiError("INVALID_REQUEST");
  await request(`/admin/operators/${encodeURIComponent(userId)}/${action}`, signal, body);
}
