"use client";

import { Menu, Sun, Moon, Monitor } from "lucide-react";
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
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background/80 px-4 backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleSidebar}
          className="text-muted-foreground hover:text-foreground"
        >
          <Menu className="h-5 w-5" />
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={cycleTheme}
          title={`Tema: ${THEME_LABEL[theme]}`}
          className="text-muted-foreground hover:text-foreground"
        >
          <ThemeIcon className="h-4 w-4" />
        </Button>
        <div className="mx-1 h-6 w-px bg-border" />
        <UserMenu />
      </div>
    </header>
  );
}
