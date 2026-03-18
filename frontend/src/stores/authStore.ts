import { create } from "zustand";
import { loginUser, loginWithCode } from "@/api";
import type { AuthUser, QuickCode } from "@/types";

const TIMEOUT_MS = 5 * 60 * 1000;
const IDLE_RESET_MS = 30 * 60 * 1000;
const QUICK_CODE_TTL_MS = 10 * 60 * 1000;

// Timer IDs live outside the store so that resetTimer (called on every
// mouse-move / keydown) never triggers a Zustand state update or re-render.
let _activityTimer: ReturnType<typeof setTimeout> | null = null;
let _idleResetTimer: ReturnType<typeof setTimeout> | null = null;
let _quickCodeTimer: ReturnType<typeof setTimeout> | null = null;

export interface AuthState {
  isAuthenticated: boolean;
  timedOut: boolean;
  shouldResetToHome: boolean;
  authUser: AuthUser | null;
  quickCode: QuickCode | null;
  token: string | null;
  clearQuickCode: () => void;
  resetTimer: () => void;
  logout: () => void;
  clearHomeReset: () => void;
  _applyLoginData: (data: {
    username: string;
    is_admin: boolean;
    access_token?: string | null;
    quick_code?: string;
  }) => void;
  login: (username: string, password: string) => Promise<void>;
  loginByCode: (code: string) => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  isAuthenticated: false,
  timedOut: false,
  shouldResetToHome: false,
  authUser: null,
  quickCode: null,
  token: null,

  clearQuickCode: () => {
    if (_quickCodeTimer) clearTimeout(_quickCodeTimer);
    _quickCodeTimer = null;
    set({ quickCode: null });
  },

  resetTimer: () => {
    if (_activityTimer) clearTimeout(_activityTimer);
    _activityTimer = setTimeout(() => get().logout(), TIMEOUT_MS);
  },

  logout: () => {
    if (_activityTimer) clearTimeout(_activityTimer);
    if (_quickCodeTimer) clearTimeout(_quickCodeTimer);
    _activityTimer = null;
    _quickCodeTimer = null;

    if (_idleResetTimer) clearTimeout(_idleResetTimer);
    _idleResetTimer = setTimeout(
      () => set({ shouldResetToHome: true }),
      IDLE_RESET_MS,
    );

    set({ isAuthenticated: false, authUser: null, token: null, timedOut: true, quickCode: null });
  },

  clearHomeReset: () => set({ shouldResetToHome: false }),

  // Internal — called after any successful login response
  _applyLoginData: (data) => {
    if (_idleResetTimer) clearTimeout(_idleResetTimer);
    _idleResetTimer = null;

    set({
      isAuthenticated: true,
      authUser: { username: data.username, isAdmin: data.is_admin },
      token: data.access_token ?? null,
      timedOut: false,
      shouldResetToHome: false,
    });

    if (data.quick_code) {
      if (_quickCodeTimer) clearTimeout(_quickCodeTimer);
      const expiresAt = Date.now() + QUICK_CODE_TTL_MS;
      _quickCodeTimer = setTimeout(() => set({ quickCode: null }), QUICK_CODE_TTL_MS);
      set({ quickCode: { code: data.quick_code, expiresAt } });
    }

    get().resetTimer();
  },

  login: async (username, password) => {
    const data = await loginUser(username, password);
    get()._applyLoginData(data);
  },

  loginByCode: async (code) => {
    const data = await loginWithCode(code);
    get()._applyLoginData(data);
  },
}));
