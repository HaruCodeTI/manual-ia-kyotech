"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { useMediaQuery } from "@/lib/hooks";
import { ChatProvider, useChatContext } from "@/lib/chat-context";
import { ViewerProvider, useViewer } from "@/lib/viewer-context";
import { DocumentViewer } from "@/components/viewer/DocumentViewer";

function AppShellInner({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const pathname = usePathname();
  const { activeSessionId, setActiveSessionId } = useChatContext();
  const { isOpen: viewerOpen } = useViewer();

  if (pathname.startsWith("/sign-in")) {
    return <>{children}</>;
  }

  function handleToggle() {
    if (isDesktop) {
      setCollapsed((v) => !v);
    } else {
      setMobileOpen((v) => !v);
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        open={mobileOpen}
        collapsed={collapsed}
        onClose={() => setMobileOpen(false)}
        activeSessionId={activeSessionId}
        onSelectSession={setActiveSessionId}
      />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header onToggleSidebar={handleToggle} />
        <div className="flex flex-1 overflow-hidden">
          <main
            className={`overflow-hidden transition-all duration-200 ${
              viewerOpen && isDesktop ? "w-1/2" : "flex-1"
            }`}
          >
            {children}
          </main>
          {viewerOpen && (
            <aside
              className={`overflow-hidden transition-all duration-200 ${
                isDesktop
                  ? "w-1/2"
                  : "fixed inset-0 z-50 w-full bg-background"
              }`}
            >
              <DocumentViewer />
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ChatProvider>
      <ViewerProvider>
        <AppShellInner>{children}</AppShellInner>
      </ViewerProvider>
    </ChatProvider>
  );
}
