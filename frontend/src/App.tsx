/**
 * Data Catalog Platform — Main Application
 * React 18 + TypeScript + TailwindCSS
 */

import { useEffect, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  Database, Search, GitBranch, BookOpen, Shield, BarChart2,
  Settings, LogOut, Bell, User, ChevronDown, Layers, Code2
} from 'lucide-react';
import { useAuthStore } from './store/authStore';

// Lazy-loaded pages
const LoginPage       = lazy(() => import('./pages/LoginPage'));
const CatalogBrowse   = lazy(() => import('./pages/CatalogBrowse'));
const AssetDetail     = lazy(() => import('./pages/AssetDetail'));
const LineageGraph    = lazy(() => import('./pages/LineageGraph'));
const Glossary        = lazy(() => import('./pages/Glossary'));
const Classification  = lazy(() => import('./pages/Classification'));
const Dashboard       = lazy(() => import('./pages/Dashboard'));
const AdminSources    = lazy(() => import('./pages/AdminSources'));
const AdminUsers      = lazy(() => import('./pages/AdminUsers'));
const AuditLog        = lazy(() => import('./pages/AuditLog'));
const ApiDocs         = lazy(() => import('./pages/ApiDocs'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

// --------------------------------------------------------------------------- #
//  Navigation                                                                  #
// --------------------------------------------------------------------------- #

const NAV_ITEMS = [
  { path: '/dashboard',       label: 'Dashboard',       icon: BarChart2,  minRole: 0 },
  { path: '/catalog',         label: 'Catalog',         icon: Database,   minRole: 0 },
  { path: '/lineage',         label: 'Lineage',         icon: GitBranch,  minRole: 1 },
  { path: '/glossary',        label: 'Glossary',        icon: BookOpen,   minRole: 0 },
  { path: '/classification',  label: 'Classification',  icon: Shield,     minRole: 1 },
  { path: '/admin/sources',   label: 'Sources',         icon: Layers,     minRole: 2 },
  { path: '/admin/users',     label: 'Users',           icon: User,       minRole: 3 },
  { path: '/audit',           label: 'Audit Log',       icon: Settings,   minRole: 3 },
  { path: '/api-docs',        label: 'API Docs',        icon: Code2,      minRole: 2 },
];

const ROLE_LEVEL: Record<string, number> = {
  viewer: 0, data_analyst: 1, data_steward: 2, admin: 3,
};

function Sidebar() {
  const { user, role, logout } = useAuthStore();
  const location = useLocation();
  const userLevel = ROLE_LEVEL[role ?? 'viewer'] ?? 0;

  const sensitivityColor: Record<string, string> = {
    admin: 'bg-red-100 text-red-700',
    data_steward: 'bg-yellow-100 text-yellow-700',
    data_analyst: 'bg-blue-100 text-blue-700',
    viewer: 'bg-gray-100 text-gray-700',
  };

  return (
    <aside className="w-64 min-h-screen bg-slate-900 text-white flex flex-col">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-indigo-600 rounded-lg flex items-center justify-center">
            <Database size={20} />
          </div>
          <div>
            <div className="font-bold text-sm leading-tight">DataCatalog</div>
            <div className="text-slate-400 text-xs">Enterprise Platform</div>
          </div>
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_ITEMS.filter(item => userLevel >= item.minRole).map(({ path, label, icon: Icon }) => {
          const isActive = location.pathname.startsWith(path);
          return (
            <Link
              key={path}
              to={path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <Icon size={17} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* User section */}
      <div className="px-4 py-4 border-t border-slate-700">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 bg-indigo-500 rounded-full flex items-center justify-center text-xs font-bold">
            {user?.full_name?.[0] ?? 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">{user?.full_name}</div>
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${sensitivityColor[role ?? 'viewer']}`}>
              {role?.replace('_', ' ')}
            </span>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-2 w-full px-3 py-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg text-sm transition-colors"
        >
          <LogOut size={15} />
          Sign out
        </button>
      </div>
    </aside>
  );
}

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 sticky top-0 z-10">
          <div className="text-sm text-gray-500">
            <span className="font-medium text-gray-800">Data Catalog</span> Platform
          </div>
          <div className="flex items-center gap-3">
            <button className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
              <Bell size={18} />
            </button>
          </div>
        </header>
        <div className="flex-1 p-6">
          {children}
        </div>
      </main>
    </div>
  );
}

// --------------------------------------------------------------------------- #
//  Protected route                                                             #
// --------------------------------------------------------------------------- #

function ProtectedRoute({ children, minRole = 0 }: { children: React.ReactNode; minRole?: number }) {
  const { isAuthenticated, role } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  const userLevel = ROLE_LEVEL[role ?? 'viewer'] ?? 0;
  if (userLevel < minRole) return <Navigate to="/dashboard" replace />;
  return <AppLayout>{children}</AppLayout>;
}

// --------------------------------------------------------------------------- #
//  Root App                                                                    #
// --------------------------------------------------------------------------- #

function AppRoutes() {
  const { isAuthenticated, loadUser } = useAuthStore();

  useEffect(() => {
    if (isAuthenticated) loadUser();
  }, []);

  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-500 text-sm">Loading...</p>
        </div>
      </div>
    }>
      <Routes>
        <Route path="/login" element={
          isAuthenticated ? <Navigate to="/dashboard" replace /> : <LoginPage />
        } />
        <Route path="/" element={<Navigate to={isAuthenticated ? "/dashboard" : "/login"} replace />} />

        <Route path="/dashboard" element={
          <ProtectedRoute><Dashboard /></ProtectedRoute>
        } />
        <Route path="/catalog" element={
          <ProtectedRoute><CatalogBrowse /></ProtectedRoute>
        } />
        <Route path="/catalog/:fqn" element={
          <ProtectedRoute><AssetDetail /></ProtectedRoute>
        } />
        <Route path="/lineage" element={
          <ProtectedRoute minRole={1}><LineageGraph /></ProtectedRoute>
        } />
        <Route path="/glossary" element={
          <ProtectedRoute><Glossary /></ProtectedRoute>
        } />
        <Route path="/classification" element={
          <ProtectedRoute minRole={1}><Classification /></ProtectedRoute>
        } />
        <Route path="/admin/sources" element={
          <ProtectedRoute minRole={2}><AdminSources /></ProtectedRoute>
        } />
        <Route path="/admin/users" element={
          <ProtectedRoute minRole={3}><AdminUsers /></ProtectedRoute>
        } />
        <Route path="/audit" element={
          <ProtectedRoute minRole={3}><AuditLog /></ProtectedRoute>
        } />
        <Route path="/api-docs" element={
          <ProtectedRoute minRole={2}><ApiDocs /></ProtectedRoute>
        } />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
