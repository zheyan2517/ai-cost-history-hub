/**
 * Agent Cost Dashboard sidecar client (Scheme A).
 * Desktop (Tauri): invokes Rust commands that manage the Python process.
 * Browser / WebUI: falls back to coordinator open-cost flow is unavailable —
 * user should use the unified portal or start-cost-dashboard.bat.
 */

import { api } from "@/services/api";
import { isTauri } from "@/utils/platform";

export type CostDashboardOpenResult = {
  url: string;
  port: number;
  started: boolean;
};

export type CostDashboardStatus = {
  running: boolean;
  url?: string | null;
  port?: number | null;
  pid?: number | null;
};

export function canUseDesktopCostDashboard(): boolean {
  return isTauri();
}

export async function openCostDashboard(): Promise<CostDashboardOpenResult> {
  if (!isTauri()) {
    throw new Error(
      "Cost Dashboard sidecar is only available in the desktop app. " +
        "Use E:\\xiangmu\\wangquanti\\start.bat or start-cost-dashboard.bat instead."
    );
  }
  return api<CostDashboardOpenResult>("open_cost_dashboard");
}

export async function stopCostDashboard(): Promise<boolean> {
  if (!isTauri()) return false;
  return api<boolean>("stop_cost_dashboard");
}

export async function getCostDashboardStatus(): Promise<CostDashboardStatus> {
  if (!isTauri()) {
    return { running: false };
  }
  return api<CostDashboardStatus>("cost_dashboard_status");
}
