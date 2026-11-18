import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import { useAuth } from "./lib/auth";
import { LoginPage, RegisterPage } from "./pages/AuthPages";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Websites = lazy(() => import("./pages/Websites"));
const WebsiteDetail = lazy(() => import("./pages/WebsiteDetail"));
const NewScan = lazy(() => import("./pages/NewScan"));
const ScansList = lazy(() => import("./pages/ScansList"));
const ScanResults = lazy(() => import("./pages/ScanResults"));
const IssuesPage = lazy(() => import("./pages/IssuesPage"));
const IssueDetailPage = lazy(() => import("./pages/IssueDetail"));
const Compare = lazy(() => import("./pages/Compare"));
const Assistant = lazy(() => import("./pages/Assistant"));
const Contrast = lazy(() => import("./pages/Contrast"));
const Reports = lazy(() => import("./pages/Reports"));
const MonitoringPage = lazy(() => import("./pages/MonitoringPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const NotFound = lazy(() => import("./pages/NotFound"));

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Loading your workspace" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

function PublicOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  if (user) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
        <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<Dashboard />} />
          <Route path="websites" element={<Websites />} />
          <Route path="websites/:id" element={<WebsiteDetail />} />
          <Route path="scans" element={<ScansList />} />
          <Route path="scans/new" element={<NewScan />} />
          <Route path="scans/:id" element={<ScanResults />} />
          <Route path="issues" element={<IssuesPage />} />
          <Route path="issues/:id" element={<IssueDetailPage />} />
          <Route path="compare" element={<Compare />} />
          <Route path="assistant" element={<Assistant />} />
          <Route path="contrast" element={<Contrast />} />
          <Route path="reports" element={<Reports />} />
          <Route path="monitoring" element={<MonitoringPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
