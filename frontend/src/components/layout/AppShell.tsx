import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { CopilotPanel } from "@/components/CopilotPanel";

interface AppShellProps {
  breadcrumb: string[];
  children: ReactNode;
  copilotEngineId?: string;
  copilotEngineSerial?: string;
  copilotExpanded?: boolean;
  scrollable?: boolean;
  headerRight?: ReactNode;
}

export function AppShell({ breadcrumb, children, copilotEngineId, copilotEngineSerial, copilotExpanded, scrollable = true, headerRight }: AppShellProps) {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-bg font-sans text-text">
      <Sidebar />
      <div className="relative flex min-w-0 flex-grow">
        <div className="flex min-w-0 flex-grow flex-col">
          <Topbar breadcrumb={breadcrumb} headerRight={headerRight} />
          <div className={scrollable ? "scrollbar-thin min-w-0 flex-grow overflow-y-auto overflow-x-hidden" : "flex flex-grow flex-col overflow-hidden"}>
            {children}
          </div>
        </div>
        <CopilotPanel engineId={copilotEngineId} engineSerial={copilotEngineSerial} defaultExpanded={copilotExpanded} />
      </div>
    </div>
  );
}
