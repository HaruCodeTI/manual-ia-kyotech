"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquare,
  Upload,
  BarChart3,
  Plus,
  Trash2,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { useAppSession } from "@/lib/session";
import { useEffect, useState } from "react";
import { getSessions, deleteSession } from "@/lib/api";
import type { ChatSession } from "@/types";

const NAV_ITEMS = [
  { href: "/", label: "Chat", icon: MessageSquare, adminOnly: false },
  { href: "/upload", label: "Upload", icon: Upload, adminOnly: true },
  { href: "/stats", label: "Estatísticas", icon: BarChart3, adminOnly: true },
] as const;

interface SidebarProps {
  open: boolean;
  collapsed: boolean;
  onClose: () => void;
  activeSessionId?: string | null;
  onSelectSession?: (id: string | null) => void;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

export function Sidebar({
  open,
  collapsed,
  onClose,
  activeSessionId,
  onSelectSession,
}: SidebarProps) {
  const pathname = usePathname();
  const { isAdmin, status } = useAppSession();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  useEffect(() => {
    if (status !== "authenticated") return;
    setLoadingSessions(true);
    getSessions()
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoadingSessions(false));
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Rebusca a lista quando uma nova sessão é criada (não existe ainda na lista local)
  useEffect(() => {
    if (!activeSessionId) return;
    if (sessions.some((s) => s.id === activeSessionId)) return;
    getSessions().then(setSessions).catch(() => {});
  }, [activeSessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    try {
      await deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeSessionId === id) onSelectSession?.(null);
    } catch {}
  }

  const filteredNav = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-all duration-300 md:static",
          open ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          collapsed ? "md:w-16" : "w-60",
        )}
      >
        {/* Logo */}
        <div
          className={cn(
            "flex h-16 shrink-0 items-center gap-3 border-b border-sidebar-border px-4",
            collapsed && "md:justify-center md:px-0",
          )}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/kyotech-icon-light.png"
            alt="Kyotech"
            className="h-9 w-9 shrink-0 rounded-lg object-contain"
          />
          {!collapsed && (
            <div className="flex flex-col">
              <span className="text-sm font-bold tracking-tight">
                Kyotech AI
              </span>
              <span className="text-[10px] font-medium uppercase tracking-widest text-sidebar-foreground/50">
                Endoscopia
              </span>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className={cn("space-y-0.5 p-3", collapsed && "md:px-2")}>
          {filteredNav.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            const linkContent = (
              <Link
                key={href}
                href={href}
                onClick={onClose}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
                  collapsed && "md:justify-center md:px-0",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/60 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                )}
              >
                <Icon
                  className={cn(
                    "h-[18px] w-[18px] shrink-0",
                    active && "text-sidebar-primary",
                  )}
                />
                {!collapsed && label}
              </Link>
            );

            if (collapsed) {
              return (
                <Tooltip key={href} delayDuration={0}>
                  <TooltipTrigger asChild>{linkContent}</TooltipTrigger>
                  <TooltipContent side="right" className="hidden md:block">
                    {label}
                  </TooltipContent>
                </Tooltip>
              );
            }
            return <div key={href}>{linkContent}</div>;
          })}
        </nav>

        {/* Sessions */}
        {!collapsed && pathname === "/" && (
          <div className="flex flex-1 flex-col overflow-hidden border-t border-sidebar-border">
            <div className="flex items-center justify-between px-4 py-2.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
                Conversas
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-sidebar-foreground/40 hover:text-sidebar-foreground hover:bg-sidebar-accent/50"
                onClick={() => onSelectSession?.(null)}
                title="Nova conversa"
              >
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto px-2 pb-2">
              {loadingSessions ? (
                <div className="flex justify-center py-4">
                  <Loader2 className="h-4 w-4 animate-spin text-sidebar-foreground/30" />
                </div>
              ) : sessions.length === 0 ? (
                <p className="px-2 py-4 text-center text-xs text-sidebar-foreground/30">
                  Nenhuma conversa ainda
                </p>
              ) : (
                sessions.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => {
                      onSelectSession?.(s.id);
                      onClose();
                    }}
                    className={cn(
                      "group flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-all duration-150",
                      activeSessionId === s.id
                        ? "bg-sidebar-accent text-sidebar-accent-foreground"
                        : "text-sidebar-foreground/50 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
                    )}
                  >
                    <span className="flex-1 truncate">
                      {s.title || "Nova conversa"}
                    </span>
                    <span className="shrink-0 text-[10px] opacity-50">
                      {timeAgo(s.updated_at)}
                    </span>
                    <button
                      onClick={(e) => handleDelete(e, s.id)}
                      className="hidden shrink-0 rounded p-0.5 hover:bg-red-500/20 hover:text-red-400 group-hover:block"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </button>
                ))
              )}
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
