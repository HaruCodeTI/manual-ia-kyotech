"use client";

import { UserButton } from "@clerk/nextjs";
import { useAppSession } from "@/lib/session";
import { Shield, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function UserMenu() {
  const { user, status, isAdmin } = useAppSession();

  if (status !== "authenticated") return null;

  return (
    <div className="flex items-center gap-2">
      <div className="hidden items-center gap-1.5 sm:flex">
        <Badge variant="secondary" className="gap-1 text-xs font-normal">
          {isAdmin ? (
            <Shield className="h-3 w-3" />
          ) : (
            <User className="h-3 w-3" />
          )}
          {isAdmin ? "Admin" : "Técnico"}
        </Badge>
        {(user?.name || user?.email) && (
          <span className="max-w-[120px] truncate text-xs text-muted-foreground">
            {user.name || user.email}
          </span>
        )}
      </div>
      <UserButton afterSignOutUrl="/" />
    </div>
  );
}
