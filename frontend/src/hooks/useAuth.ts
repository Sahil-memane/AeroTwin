import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/services/resources";
import { ApiError } from "@/services/apiClient";

export function useAuth() {
  const navigate = useNavigate();
  const { isAuthenticated, role, email, login: setLogin, logout: clearAuth } = useAuthStore();

  async function login(emailInput: string, password: string) {
    try {
      const tokens = await authApi.login(emailInput, password);
      setLogin({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        role: tokens.role,
        email: emailInput,
      });
      return { ok: true as const };
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) return { ok: false as const, error: "Invalid email or password." };
        if (err.status === 423) return { ok: false as const, error: "Account locked or inactive." };
        if (err.status === 429) return { ok: false as const, error: "Too many attempts — try again shortly." };
      }
      return { ok: false as const, error: "Could not reach the AeroTwin backend." };
    }
  }

  function logout() {
    clearAuth();
    navigate("/login", { replace: true });
  }

  return { isAuthenticated, role, email, login, logout };
}
