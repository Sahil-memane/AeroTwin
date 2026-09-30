import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { CopilotPanel } from "@/components/CopilotPanel";

interface AppShellProps {
  breadcrumb: string[];
  children: ReactNode;
  copilotEngineId?: string;
  copilotExpanded?: boolean;
  scrollable?: boolean;
}

export function AppShell({ breadcrumb, children, copilotEngineId, copilotExpanded, scrollable = true }: AppShellProps) {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-bg font-sans text-text">
      <Sidebar />
      <div className="relative flex min-w-0 flex-grow">
        <div className="flex min-w-0 flex-grow flex-col">
          <Topbar breadcrumb={breadcrumb} />
          <div className={scrollable ? "scrollbar-thin min-w-0 flex-grow overflow-y-auto overflow-x-hidden" : "flex flex-grow flex-col overflow-hidden"}>
            {children}
          </div>
        </div>
        <CopilotPanel engineId={copilotEngineId} defaultExpanded={copilotExpanded} />
      </div>
    </div>
  );
}
