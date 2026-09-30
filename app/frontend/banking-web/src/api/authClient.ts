import { AUTH_TOKEN_KEY, getAuthToken } from "@/api/authToken";

const AUTH_API_URL = import.meta.env.VITE_RESPONSES_BFF_URL || "";

export interface AuthenticatedUser {
    id: string;
    customerId: string;
    email: string;
    locale: string;
    name: string | null;
}

interface AuthenticatedUserResponse {
    sub: string;
    customer_id: string;
    email: string;
    locale: string;
    name?: string | null;
}

interface LoginResponse {
    access_token: string;
    user: AuthenticatedUserResponse;
}

export interface AccountSummary {
    id: string;
    type: string;
    status: string | null;
    opened: string | null;
    number: string | null;
    currency: string;
}

export const getAccounts = async (signal?: AbortSignal): Promise<AccountSummary[]> => {
    const token = getAuthToken();
    if (!token) {
        throw new Error("Sign in to view your accounts");
    }
    const response = await fetch(`${AUTH_API_URL}/auth/me/accounts`, {
        headers: { Authorization: `Bearer ${token}` },
        signal,
    });
    if (!response.ok) {
        throw new Error(response.status === 401
            ? "Your session has expired. Sign in again."
            : "Accounts are temporarily unavailable");
    }
    return response.json();
};

const mapUser = (user: AuthenticatedUserResponse): AuthenticatedUser => ({
    id: user.sub,
    customerId: user.customer_id,
    email: user.email,
    locale: user.locale,
    name: user.name ?? null,
});

export const login = async (email: string, password: string): Promise<AuthenticatedUser> => {
    const response = await fetch(`${AUTH_API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
        throw new Error(response.status === 401 ? "Invalid email or password" : "Sign in is unavailable");
    }

    const result = (await response.json()) as LoginResponse;
    localStorage.setItem(AUTH_TOKEN_KEY, result.access_token);
    return mapUser(result.user);
};

export const restoreUser = async (): Promise<AuthenticatedUser | null> => {
    const token = getAuthToken();
    if (!token) {
        return null;
    }

    const response = await fetch(`${AUTH_API_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        return null;
    }

    return mapUser((await response.json()) as AuthenticatedUserResponse);
};