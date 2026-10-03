import { z } from "zod";
import { getAuthToken } from "@/api/authToken";
import { ApiError, readApiError } from "@/api/errors";

const baseUrl = import.meta.env.VITE_RESPONSES_BFF_URL || "";
const customerSchema = z.object({
  sub: z.string().regex(/^[A-Za-z0-9_-]+$/).max(128),
  customer_id: z.string().trim().min(1),
  email: z.string().email(),
  locale: z.enum(["en", "es", "pt"]),
  name: z.string().nullable().optional(),
  role: z.literal("customer"),
  identity_version: z.number().int().min(1).safe(),
  status: z.enum(["active", "inactive"]),
  updated_at: z.string().datetime({ offset: true }),
});
export type CustomerUser = z.infer<typeof customerSchema>;
export type CustomerUserAction = "activate" | "deactivate";

async function request(path: string, method: "GET" | "POST", signal: AbortSignal): Promise<Response> {
  const token = getAuthToken();
  if (!token) throw new ApiError("AUTH_REQUIRED");
  const response = await fetch(`${baseUrl}${path}`, {
    method, headers: { Authorization: `Bearer ${token}` }, signal,
  });
  if (!response.ok) throw await readApiError(response);
  signal.throwIfAborted();
  return response;
}

export async function listCustomerUsers(signal: AbortSignal): Promise<CustomerUser[]> {
  const response = await request("/admin/customers", "GET", signal);
  let body: unknown;
  try { body = await response.json(); }
  catch { signal.throwIfAborted(); throw new ApiError("SERVICE_UNAVAILABLE"); }
  signal.throwIfAborted();
  const parsed = z.array(customerSchema).safeParse(body);
  if (!parsed.success) throw new ApiError("SERVICE_UNAVAILABLE");
  return parsed.data;
}

export async function changeCustomerUser(userId: string, action: CustomerUserAction, signal: AbortSignal): Promise<void> {
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(userId) || !["activate", "deactivate"].includes(action)) {
    throw new ApiError("INVALID_REQUEST");
  }
  await request(`/admin/customers/${encodeURIComponent(userId)}/${action}`, "POST", signal);
}
