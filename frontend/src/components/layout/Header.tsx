"use client";

import { MessageSquare, Menu, Sun, Moon, Monitor } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "./ThemeProvider";
import { UserMenu } from "./UserMenu";

interface HeaderProps {
  onToggleSidebar: () => void;
}

const THEME_CYCLE = ["light", "dark", "system"] as const;
const THEME_ICON = { light: Sun, dark: Moon, system: Monitor } as const;
const THEME_LABEL = { light: "Claro", dark: "Escuro", system: "Sistema" } as const;

export function Header({ onToggleSidebar }: HeaderProps) {
  const { theme, setTheme } = useTheme();

  function cycleTheme() {
    const idx = THEME_CYCLE.indexOf(theme);
    setTheme(THEME_CYCLE[(idx + 1) % THEME_CYCLE.length]);
  }

  const ThemeIcon = THEME_ICON[theme];

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background px-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={onToggleSidebar}>
          <Menu className="h-5 w-5" />
        </Button>
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <MessageSquare className="h-4 w-4 text-primary-foreground" />
          </div>
          <span className="text-lg font-semibold tracking-tight">
            Kyotech AI
          </span>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          onClick={cycleTheme}
          title={`Tema: ${THEME_LABEL[theme]}`}
        >
          <ThemeIcon className="h-4 w-4" />
        </Button>
        <UserMenu />
      </div>
    </header>
  );
}
