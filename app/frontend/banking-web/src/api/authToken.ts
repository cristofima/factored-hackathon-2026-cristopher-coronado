export const AUTH_TOKEN_KEY = "banking-auth-token";

export const getAuthToken = () => localStorage.getItem(AUTH_TOKEN_KEY);