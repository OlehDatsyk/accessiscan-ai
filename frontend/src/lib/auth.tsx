import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { api, post, setSessionExpiredHandler, tokens } from "../api/client";
import type { TokenOut, User } from "../api/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Forget the local session (tokens and cached data) without calling the API. */
  endSession: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
const ME = ["me"];

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const hadTokens = !!tokens.access || !!tokens.refresh;
  const me = useQuery({
    queryKey: ME,
    queryFn: () => (tokens.access || tokens.refresh ? api<User>("/users/me") : Promise.resolve(null)),
    retry: false,
    staleTime: 5 * 60_000,
  });

  // Keep the observed "me" query and replace everything else, so the provider re-renders reliably.
  const endSession = useCallback(() => {
    tokens.clear();
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    qc.setQueryData(ME, null);
  }, [qc]);

  useEffect(() => setSessionExpiredHandler(endSession), [endSession]);

  const afterAuth = useCallback(
    async (t: TokenOut) => {
      tokens.set(t.access_token, t.refresh_token);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      qc.setQueryData(ME, await api<User>("/users/me"));
    },
    [qc],
  );

  const value = useMemo<AuthState>(
    () => ({
      user: me.data ?? null,
      loading: me.isLoading && hadTokens,
      login: async (email, password) => afterAuth(await post<TokenOut>("/auth/login", { email, password })),
      register: async (email, password, fullName) =>
        afterAuth(await post<TokenOut>("/auth/register", { email, password, full_name: fullName })),
      logout: async () => {
        const rt = tokens.refresh;
        endSession();
        if (rt) await post("/auth/logout", { refresh_token: rt }).catch(() => undefined);
      },
      endSession,
    }),
    [me.data, me.isLoading, hadTokens, afterAuth, endSession],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
