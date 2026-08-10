/**
 * API client for all Data Catalog microservices.
 * Handles JWT authentication, token refresh, and error normalization.
 */

import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from 'axios';
import { Asset, Column, GlossaryTerm, LineageEdge, DataSource, User, AuditEvent } from '../types';

const API_GATEWAY = import.meta.env.VITE_API_GATEWAY_URL ?? 'http://localhost:4456';

// Service URLs (routed through API Gateway in production)
const SERVICES = {
  auth:           `${API_GATEWAY}/auth`,
  catalog:        `${API_GATEWAY}/catalog`,
  connector:      `${API_GATEWAY}/connector`,
  metadata:       `${API_GATEWAY}/metadata`,
  classification: `${API_GATEWAY}/classification`,
  terms:          `${API_GATEWAY}/terms`,
  lineage:        `${API_GATEWAY}/lineage`,
  audit:          `${API_GATEWAY}/audit`,
};

// --------------------------------------------------------------------------- #
//  Axios instance with JWT interceptors                                        #
// --------------------------------------------------------------------------- #

const apiClient: AxiosInstance = axios.create({
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach access token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auto-refresh on 401 — Zero Trust token refresh
let isRefreshing = false;
let failedQueue: Array<{ resolve: (v: unknown) => void; reject: (e: unknown) => void }> = [];

const processQueue = (error: Error | null, token: string | null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error);
    else resolve(token);
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          return apiClient(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem('refresh_token');
      if (!refreshToken) {
        window.location.href = '/login';
        return Promise.reject(error);
      }

      try {
        const resp = await axios.post(`${SERVICES.auth}/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const { access_token, refresh_token: newRefresh } = resp.data;
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('refresh_token', newRefresh);
        processQueue(null, access_token);
        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
        }
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError as Error, null);
        localStorage.clear();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }
    return Promise.reject(error);
  }
);

// --------------------------------------------------------------------------- #
//  Auth API                                                                    #
// --------------------------------------------------------------------------- #

export const authApi = {
  login: async (email: string, password: string) => {
    const resp = await axios.post(`${SERVICES.auth}/auth/login`, { email, password });
    return resp.data;
  },
  logout: async () => {
    const token = localStorage.getItem('access_token');
    if (token) {
      await axios.post(`${SERVICES.auth}/auth/logout`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {}); // Best-effort
    }
    localStorage.clear();
  },
  getMe: async (): Promise<User> => {
    const resp = await apiClient.get(`${SERVICES.auth}/users/me`);
    return resp.data;
  },
  checkPermission: async (resource: string, action: string) => {
    const resp = await apiClient.post(`${SERVICES.auth}/authz/check`, null, {
      params: { resource, action },
    });
    return resp.data.allowed as boolean;
  },
  listUsers: async (params?: { q?: string; role?: string; is_active?: boolean; page?: number; page_size?: number }): Promise<{ total: number; page: number; page_size: number; users: User[] }> => {
    const resp = await apiClient.get(`${SERVICES.auth}/users`, { params });
    return resp.data;
  },
  createUser: async (data: Partial<User> & { password: string }) => {
    const resp = await apiClient.post(`${SERVICES.auth}/users`, data);
    return resp.data;
  },
  updateUser: async (userId: string, data: { full_name?: string; role?: string; department?: string; is_active?: boolean }) => {
    const resp = await apiClient.put(`${SERVICES.auth}/users/${userId}`, data);
    return resp.data as User;
  },
  deleteUser: async (userId: string) => {
    await apiClient.delete(`${SERVICES.auth}/users/${userId}`);
  },
  getRoles: async () => {
    const resp = await apiClient.get(`${SERVICES.auth}/roles`);
    return resp.data;
  },
};

// --------------------------------------------------------------------------- #
//  Catalog API                                                                 #
// --------------------------------------------------------------------------- #

export const catalogApi = {
  searchAssets: async (params: {
    q?: string;
    domain?: string;
    sensitivity?: string;
    source_type?: string;
    limit?: number;
    offset?: number;
  }): Promise<{ total: number; assets: Asset[] }> => {
    const resp = await apiClient.get(`${SERVICES.catalog}/assets`, { params });
    return resp.data;
  },
  getAsset: async (fqn: string): Promise<Asset & { columns: Column[] }> => {
    const resp = await apiClient.get(`${SERVICES.catalog}/assets/${encodeURIComponent(fqn)}`);
    return resp.data;
  },
  updateAsset: async (fqn: string, updates: Partial<Asset>) => {
    const resp = await apiClient.patch(
      `${SERVICES.catalog}/assets/${encodeURIComponent(fqn)}`,
      updates
    );
    return resp.data;
  },
  getStats: async () => {
    const resp = await apiClient.get(`${SERVICES.catalog}/stats`);
    return resp.data;
  },
};

// --------------------------------------------------------------------------- #
//  Connector API                                                               #
// --------------------------------------------------------------------------- #

export const connectorApi = {
  listSources: async (): Promise<DataSource[]> => {
    const resp = await apiClient.get(`${SERVICES.connector}/sources`);
    return resp.data;
  },
  registerSource: async (source: Omit<DataSource, 'source_id'> & {
    username: string; password: string; port: number;
  }) => {
    const resp = await apiClient.post(`${SERVICES.connector}/sources`, source);
    return resp.data;
  },
  triggerHydration: async (sourceId: string) => {
    const resp = await apiClient.post(`${SERVICES.connector}/sources/${sourceId}/hydrate`);
    return resp.data;
  },
  getJobStatus: async (jobId: string) => {
    const resp = await apiClient.get(`${SERVICES.connector}/jobs/${jobId}`);
    return resp.data;
  },
  listJobs: async () => {
    const resp = await apiClient.get(`${SERVICES.connector}/jobs`);
    return resp.data;
  },
  getSource: async (sourceId: string) => {
    const resp = await apiClient.get(`${SERVICES.connector}/sources/${sourceId}`);
    return resp.data;
  },
  updateSource: async (sourceId: string, data: Record<string, any>) => {
    const resp = await apiClient.put(`${SERVICES.connector}/sources/${sourceId}`, data);
    return resp.data;
  },
  deleteSource: async (sourceId: string) => {
    await apiClient.delete(`${SERVICES.connector}/sources/${sourceId}`);
  },
  testConnection: async (config: {
    source_type: string; host: string; port: number;
    database: string; username: string; password: string;
  }) => {
    const resp = await apiClient.post(`${SERVICES.connector}/test-connection`, config);
    return resp.data;
  },
};

// --------------------------------------------------------------------------- #
//  Terms API                                                                   #
// --------------------------------------------------------------------------- #

export const termsApi = {
  listTerms: async (params?: {
    domain?: string; status?: string; q?: string; limit?: number;
  }): Promise<{ total: number; terms: GlossaryTerm[] }> => {
    const resp = await apiClient.get(`${SERVICES.terms}/terms`, { params });
    return resp.data;
  },
  getTerm: async (termId: string): Promise<GlossaryTerm> => {
    const resp = await apiClient.get(`${SERVICES.terms}/terms/${termId}`);
    return resp.data;
  },
  createTerm: async (term: Partial<GlossaryTerm>): Promise<GlossaryTerm> => {
    const resp = await apiClient.post(`${SERVICES.terms}/terms`, term);
    return resp.data;
  },
  updateTerm: async (termId: string, updates: Partial<GlossaryTerm>) => {
    const resp = await apiClient.put(`${SERVICES.terms}/terms/${termId}`, updates);
    return resp.data;
  },
  deleteTerm: async (termId: string) => {
    await apiClient.delete(`${SERVICES.terms}/terms/${termId}`);
  },
  suggestTerms: async (columnName: string, dataType: string, tableName?: string) => {
    const resp = await apiClient.post(`${SERVICES.terms}/terms/suggest`, {
      column_name: columnName,
      data_type: dataType,
      table_name: tableName,
    });
    return resp.data;
  },
  assignTerm: async (termId: string, assetFqn: string, assetType = 'COLUMN') => {
    const resp = await apiClient.post(`${SERVICES.terms}/assignments`, {
      term_id: termId,
      asset_fqn: assetFqn,
      asset_type: assetType,
    });
    return resp.data;
  },
};

// --------------------------------------------------------------------------- #
//  Lineage API                                                                 #
// --------------------------------------------------------------------------- #

export const lineageApi = {
  getLineage: async (fqn: string, direction = 'both', depth = 3) => {
    const resp = await apiClient.get(`${SERVICES.lineage}/lineage`, {
      params: { fqn, direction, depth },
    });
    return resp.data;
  },
  createEdge: async (edge: Partial<LineageEdge>) => {
    const resp = await apiClient.post(`${SERVICES.lineage}/lineage/edge`, edge);
    return resp.data;
  },
  getImpactAnalysis: async (assetFqn: string) => {
    const resp = await apiClient.get(
      `${SERVICES.lineage}/lineage/impact/${encodeURIComponent(assetFqn)}`
    );
    return resp.data;
  },
};

// --------------------------------------------------------------------------- #
//  Audit API                                                                   #
// --------------------------------------------------------------------------- #

export const auditApi = {
  queryEvents: async (params?: {
    user_email?: string; event_type?: string;
    resource_fqn?: string; start_time?: string; end_time?: string; limit?: number;
  }): Promise<{ total: number; events: AuditEvent[] }> => {
    const resp = await apiClient.get(`${SERVICES.audit}/audit/events`, { params });
    return resp.data;
  },
  getPiiAccessReport: async (days = 30) => {
    const resp = await apiClient.get(`${SERVICES.audit}/audit/pii-access-report`, {
      params: { days },
    });
    return resp.data;
  },
};

export default apiClient;
