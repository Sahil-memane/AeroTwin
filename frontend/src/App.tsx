import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Login } from "@/pages/Login";
import { Dashboard } from "@/pages/Dashboard";
import { EngineDetail } from "@/pages/EngineDetail";
import { SimulationReplay } from "@/pages/SimulationReplay";
// The 3D twin pulls in three.js (~0.6 MB); load it only when someone opens that page.
import { TwinIndex } from "@/pages/TwinIndex";
const EngineTwin = lazy(() => import("@/pages/EngineTwin").then((m) => ({ default: m.EngineTwin })));
import { Missions } from "@/pages/Missions";
import { MissionDetail } from "@/pages/MissionDetail";
import { Assets } from "@/pages/Assets";
import { Alerts } from "@/pages/Alerts";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/engines/:engineId"
          element={
            <ProtectedRoute>
              <EngineDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/twin"
          element={
            <ProtectedRoute>
              <TwinIndex />
            </ProtectedRoute>
          }
        />
        <Route
          path="/engines/:engineId/twin"
          element={
            <ProtectedRoute>
              <Suspense fallback={<div className="p-6 text-sm text-textMuted">Loading 3D twin…</div>}>
                <EngineTwin />
              </Suspense>
            </ProtectedRoute>
          }
        />
        <Route
          path="/engines/:engineId/simulation"
          element={
            <ProtectedRoute>
              <SimulationReplay />
            </ProtectedRoute>
          }
        />
        <Route
          path="/missions"
          element={
            <ProtectedRoute>
              <Missions />
            </ProtectedRoute>
          }
        />
        <Route
          path="/missions/:missionId"
          element={
            <ProtectedRoute>
              <MissionDetail />
            </ProtectedRoute>
          }
        />
        <Route
          path="/assets"
          element={
            <ProtectedRoute>
              <Assets />
            </ProtectedRoute>
          }
        />
        <Route
          path="/alerts"
          element={
            <ProtectedRoute>
              <Alerts />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
