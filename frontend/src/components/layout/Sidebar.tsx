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
  }, [status, activeSessionId]);

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
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex flex-col border-r bg-background transition-all md:static",
          open ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          collapsed ? "md:w-16" : "w-56"
        )}
      >
        <div
          className={cn(
            "flex h-14 shrink-0 items-center gap-2 border-b px-4",
            collapsed && "md:justify-center md:px-0"
          )}
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary">
            <MessageSquare className="h-4 w-4 text-primary-foreground" />
          </div>
          {!collapsed && <span className="font-semibold">Kyotech AI</span>}
        </div>

        <nav className={cn("space-y-1 p-3", collapsed && "md:px-2")}>
          {filteredNav.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            const linkContent = (
              <Link
                key={href}
                href={href}
                onClick={onClose}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  collapsed && "md:justify-center md:px-0",
                  active
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
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

        {!collapsed && pathname === "/" && (
          <div className="flex flex-1 flex-col overflow-hidden border-t">
            <div className="flex items-center justify-between px-4 py-2">
              <span className="text-xs font-medium text-muted-foreground">
                Conversas
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => onSelectSession?.(null)}
                title="Nova conversa"
              >
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto px-2 pb-2">
              {loadingSessions ? (
                <div className="flex justify-center py-4">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : sessions.length === 0 ? (
                <p className="px-2 py-4 text-center text-xs text-muted-foreground">
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
                      "group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors",
                      activeSessionId === s.id
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                    )}
                  >
                    <span className="flex-1 truncate">
                      {s.title || "Nova conversa"}
                    </span>
                    <span className="shrink-0 text-[10px] opacity-60">
                      {timeAgo(s.updated_at)}
                    </span>
                    <button
                      onClick={(e) => handleDelete(e, s.id)}
                      className="hidden shrink-0 rounded p-0.5 hover:bg-destructive/10 hover:text-destructive group-hover:block"
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
