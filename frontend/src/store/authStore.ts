/**
 * Zustand auth store — manages JWT state and user session.
 * Zero Trust: tokens expire in 15 min, refresh automatically.
 */

import { create } from 'zustand';
import { AuthState, User, UserRole } from '../types';
import { authApi } from '../services/api';

interface AuthStore extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  loadUser: () => Promise<void>;
  hasPermission: (resource: string, action: string) => Promise<boolean>;
  canRead: (sensitivityLevel: string) => boolean;
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  accessToken: localStorage.getItem('access_token'),
  refreshToken: localStorage.getItem('refresh_token'),
  isAuthenticated: !!localStorage.getItem('access_token'),
  role: (localStorage.getItem('user_role') as UserRole) || null,

  login: async (email: string, password: string) => {
    const data = await authApi.login(email, password);
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    localStorage.setItem('user_role', data.role);

    set({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      isAuthenticated: true,
      role: data.role,
    });

    // Load full user profile
    const user = await authApi.getMe();
    set({ user });
  },

  logout: async () => {
    await authApi.logout();
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      role: null,
    });
  },

  loadUser: async () => {
    try {
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true, role: user.role });
    } catch {
      set({ user: null, isAuthenticated: false });
    }
  },

  hasPermission: async (resource: string, action: string) => {
    try {
      return await authApi.checkPermission(resource, action);
    } catch {
      return false;
    }
  },

  // Local role-based sensitivity check (for UI gating)
  canRead: (sensitivityLevel: string) => {
    const role = get().role;
    if (!role) return false;
    const roleLevel: Record<UserRole, number> = {
      viewer: 0, data_analyst: 1, data_steward: 2, admin: 3,
    };
    const sensitivityLevel_map: Record<string, number> = {
      PUBLIC: 0, INTERNAL: 0, CONFIDENTIAL: 1, RESTRICTED: 2,
    };
    return roleLevel[role] >= (sensitivityLevel_map[sensitivityLevel] ?? 0);
  },
}));
