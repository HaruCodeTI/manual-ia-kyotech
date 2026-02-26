"use client";

import { useEffect, useState } from "react";
import { getStats } from "@/lib/api";
import type { StatsResponse } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Cpu,
  FileText,
  Layers,
  PuzzleIcon,
  Loader2,
  AlertCircle,
} from "lucide-react";

const STAT_CONFIG = [
  { key: "equipments" as const, label: "Equipamentos", icon: Cpu },
  { key: "documents" as const, label: "Documentos", icon: FileText },
  { key: "versions" as const, label: "Versões", icon: Layers },
  { key: "chunks" as const, label: "Chunks", icon: PuzzleIcon },
];

export function StatsCards() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Erro ao carregar estatísticas")
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        Carregando estatísticas…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center gap-2 py-20 text-destructive">
        <AlertCircle className="h-5 w-5" />
        {error}
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {STAT_CONFIG.map(({ key, label, icon: Icon }) => (
        <Card key={key}>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {label}
            </CardTitle>
            <Icon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {stats?.[key]?.toLocaleString("pt-BR") ?? "—"}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
