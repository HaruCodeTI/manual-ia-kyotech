"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { useMediaQuery } from "@/lib/hooks";
import { ChatProvider, useChatContext } from "@/lib/chat-context";

function AppShellInner({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const pathname = usePathname();
  const { activeSessionId, setActiveSessionId } = useChatContext();

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
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ChatProvider>
      <AppShellInner>{children}</AppShellInner>
    </ChatProvider>
  );
}
