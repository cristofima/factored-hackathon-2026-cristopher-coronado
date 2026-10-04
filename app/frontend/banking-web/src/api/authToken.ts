export const AUTH_TOKEN_KEY = "banking-auth-token";

export const getAuthToken = () => localStorage.getItem(AUTH_TOKEN_KEY);

// Used only for UI expiry scheduling; the verified BFF profile remains the identity source.
export function getTokenExpiry(token: string): number | null {
    try {
        const payload = token.split(".")[1];
        const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
        const { exp } = JSON.parse(atob(base64));
        return typeof exp === "number" && Number.isFinite(exp * 1000) && exp > 0
            ? exp * 1000 : null;
    } catch {
        return null;
    }
}