import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { type AuthenticatedUser, login as authenticate, restoreUser } from "@/api/authClient";
import { AUTH_TOKEN_KEY, getAuthToken, getTokenExpiry } from "@/api/authToken";
import { resetToasts } from "@/hooks/use-toast";
import { clearChatSnapshot } from "@/components/chat/sessionHistory";

interface AuthContextValue {
  user: AuthenticatedUser | null;
  loading: boolean;
  sessionKey: number;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionKey, setSessionKey] = useState(0);
  const pending = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    void queryClient.cancelQueries();
    queryClient.clear();
    resetToasts();
    toast.dismiss();
    setUser(null);
    setSessionKey((key) => key + 1);
    return controller;
  }, [queryClient]);

  const logout = useCallback(() => {
    clearChatSnapshot();
    reset();
    localStorage.removeItem(AUTH_TOKEN_KEY);
    setLoading(false);
  }, [reset]);

  useEffect(() => {
    const restore = () => {
      const controller = reset();
      setLoading(true);
      void restoreUser(controller.signal)
        .then((profile) => {
          if (!controller.signal.aborted) setUser(profile);
        })
        .catch(() => {
          if (!controller.signal.aborted) setUser(null);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    };
    restore();
    const onStorage = (event: StorageEvent) => {
      if (event.key === AUTH_TOKEN_KEY || event.key === null) {
        clearChatSnapshot();
        restore();
      }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      pending.current?.abort();
      window.removeEventListener("storage", onStorage);
    };
  }, [reset]);

  useEffect(() => {
    if (!user || loading) return;
    const token = getAuthToken();
    const expiresAt = token ? getTokenExpiry(token) : null;
    let timer: ReturnType<typeof setTimeout>;
    const checkExpiry = () => {
      if (getAuthToken() !== token) return;
      if (expiresAt === null || expiresAt <= Date.now()) {
        logout();
        return;
      }
      clearTimeout(timer);
      timer = setTimeout(checkExpiry, Math.min(expiresAt - Date.now(), 2_147_483_647));
    };
    checkExpiry();
    window.addEventListener("focus", checkExpiry);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("focus", checkExpiry);
    };
  }, [user, loading, logout]);

  const login = useCallback(async (email: string, password: string) => {
    clearChatSnapshot();
    const controller = reset();
    setLoading(true);
    localStorage.removeItem(AUTH_TOKEN_KEY);
    try {
      const profile = await authenticate(email, password, controller.signal);
      controller.signal.throwIfAborted();
      setUser(profile);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [reset]);

  const value = useMemo(() => ({ user, loading, sessionKey, login, logout }),
    [user, loading, sessionKey, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
};
