import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Role } from "@/types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  role: Role | null;
  email: string | null;
  isAuthenticated: boolean;
  login: (params: { accessToken: string; refreshToken: string; role: Role; email: string }) => void;
  setAccessToken: (token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      role: null,
      email: null,
      isAuthenticated: false,
      login: ({ accessToken, refreshToken, role, email }) =>
        set({ accessToken, refreshToken, role, email, isAuthenticated: true }),
      setAccessToken: (token) => set({ accessToken: token }),
      logout: () =>
        set({ accessToken: null, refreshToken: null, role: null, email: null, isAuthenticated: false }),
    }),
    { name: "aerotwin-auth" },
  ),
);
