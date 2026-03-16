import { create } from "zustand";
import { loginUser, loginWithCode } from "@/api";

const TIMEOUT_MS = 5 * 60 * 1000;
const IDLE_RESET_MS = 30 * 60 * 1000;
const QUICK_CODE_TTL_MS = 10 * 60 * 1000;

// Timer IDs live outside the store so that resetTimer (called on every
// mouse-move / keydown) never triggers a Zustand state update or re-render.
let _activityTimer = null;
let _idleResetTimer = null;
let _quickCodeTimer = null;

export const useAuthStore = create((set, get) => ({
  isAuthenticated: false,
  timedOut: false,
  shouldResetToHome: false,
  authUser: null,   // { username, isAdmin }
  quickCode: null,  // { code, expiresAt }
  token: null,

  clearQuickCode: () => {
    clearTimeout(_quickCodeTimer);
    _quickCodeTimer = null;
    set({ quickCode: null });
  },

  resetTimer: () => {
    clearTimeout(_activityTimer);
    _activityTimer = setTimeout(() => get().logout(), TIMEOUT_MS);
  },

  logout: () => {
    clearTimeout(_activityTimer);
    clearTimeout(_quickCodeTimer);
    _activityTimer = null;
    _quickCodeTimer = null;

    clearTimeout(_idleResetTimer);
    _idleResetTimer = setTimeout(
      () => set({ shouldResetToHome: true }),
      IDLE_RESET_MS
    );

    set({ isAuthenticated: false, authUser: null, token: null, timedOut: true, quickCode: null });
  },

  clearHomeReset: () => set({ shouldResetToHome: false }),

  // Internal — called after any successful login response
  _applyLoginData: (data) => {
    clearTimeout(_idleResetTimer);
    _idleResetTimer = null;

    set({
      isAuthenticated: true,
      authUser: { username: data.username, isAdmin: data.is_admin },
      token: data.access_token ?? null,
      timedOut: false,
      shouldResetToHome: false,
    });

    if (data.quick_code) {
      clearTimeout(_quickCodeTimer);
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
