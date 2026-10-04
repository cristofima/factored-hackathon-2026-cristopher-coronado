import { z } from "zod";
import { AUTH_TOKEN_KEY, getAuthToken } from "@/api/authToken";
import { ApiError, readApiError } from "@/api/errors";

const AUTH_API_URL = import.meta.env.VITE_RESPONSES_BFF_URL || "";
const ACCOUNT_API_URL = import.meta.env.VITE_ACCOUNT_API_URL || "";

export type UserRole = "customer" | "operator" | "admin";

interface IdentityProfile {
    id: string;
    email: string;
    locale: string;
    name: string | null;
    identityVersion: number;
}

export type AuthenticatedUser = IdentityProfile & (
    | { role: "customer"; customerId: string }
    | { role: "operator" | "admin"; customerId?: never }
);

const profileFields = {
    sub: z.string().trim().min(1),
    email: z.string().email(),
    locale: z.string().min(1),
    name: z.string().nullable().optional(),
    identity_version: z.number().int().min(1).safe(),
};

const profileSchema = z.discriminatedUnion("role", [
    z.object({ ...profileFields, role: z.literal("customer"), customer_id: z.string().trim().min(1) }),
    z.object({ ...profileFields, role: z.literal("operator"), customer_id: z.never().optional() }),
    z.object({ ...profileFields, role: z.literal("admin"), customer_id: z.never().optional() }),
]);

export function mapUser(value: unknown): AuthenticatedUser {
    const parsed = profileSchema.safeParse(value);
    if (!parsed.success) throw new ApiError("AUTH_REQUIRED");
    const user = parsed.data;
    const profile = {
        id: user.sub, email: user.email, locale: user.locale,
        name: user.name ?? null, identityVersion: user.identity_version,
    };
    return user.role === "customer"
        ? { ...profile, role: user.role, customerId: user.customer_id }
        : { ...profile, role: user.role };
}

const loginSchema = z.object({ access_token: z.string().min(1), user: z.unknown() });

export interface AccountSummary {
    product_id: string;
    type: string;
    status: string | null;
    opened: string | null;
    number: string | null;
    currency: string;
    balance: string | null;
}

export const getAccounts = async (signal?: AbortSignal): Promise<AccountSummary[]> => {
    const token = getAuthToken();
    if (!token) {
        throw new ApiError("AUTH_REQUIRED");
    }
    const response = await fetch(`${ACCOUNT_API_URL}/accounts`, {
        headers: { Authorization: `Bearer ${token}` },
        signal,
    });
    if (!response.ok) {
        throw await readApiError(response);
    }
    return response.json();
};

export interface CardSummary extends AccountSummary {
    product_id: string;
    expires: string | null;
    credit_limit: string | null;
}

export const getCards = async (signal?: AbortSignal): Promise<CardSummary[]> => {
    const token = getAuthToken();
    if (!token) throw new ApiError("AUTH_REQUIRED");
    const response = await fetch(`${ACCOUNT_API_URL}/cards`, {
        headers: { Authorization: `Bearer ${token}` }, signal,
    });
    if (!response.ok) {
        throw await readApiError(response);
    }
    return response.json();
};

export const login = async (email: string, password: string, signal?: AbortSignal): Promise<AuthenticatedUser> => {
    const response = await fetch(`${AUTH_API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        signal,
    });

    if (!response.ok) {
        throw await readApiError(response);
    }

    const parsed = loginSchema.safeParse(await response.json());
    if (!parsed.success) throw new ApiError("AUTH_REQUIRED");
    const user = mapUser(parsed.data.user);
    signal?.throwIfAborted();
    localStorage.setItem(AUTH_TOKEN_KEY, parsed.data.access_token);
    return user;
};

export const restoreUser = async (signal?: AbortSignal): Promise<AuthenticatedUser | null> => {
    const token = getAuthToken();
    if (!token) {
        return null;
    }

    const response = await fetch(`${AUTH_API_URL}/auth/me`, {
        signal,
        headers: { Authorization: `Bearer ${token}` },
    });
    signal?.throwIfAborted();
    if (!response.ok) {
        if (getAuthToken() === token) localStorage.removeItem(AUTH_TOKEN_KEY);
        return null;
    }

    signal?.throwIfAborted();
    try {
        const user = mapUser(await response.json());
        signal?.throwIfAborted();
        if (getAuthToken() !== token) throw new DOMException("Session changed", "AbortError");
        return user;
    } catch (error) {
        signal?.throwIfAborted();
        if (getAuthToken() === token) localStorage.removeItem(AUTH_TOKEN_KEY);
        throw error;
    }
};