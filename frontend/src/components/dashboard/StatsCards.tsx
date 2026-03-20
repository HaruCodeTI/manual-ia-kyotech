"use client";

import { useEffect, useState } from "react";
import { getStats, getUsageStats } from "@/lib/api";
import type { StatsResponse, UsageStatsResponse } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  FileText,
  Layers,
  AlertTriangle,
  MessageSquare,
  MessagesSquare,
  ThumbsUp,
  ThumbsDown,
  TrendingUp,
  Loader2,
  AlertCircle,
} from "lucide-react";

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold">{value}</p>
      </CardContent>
    </Card>
  );
}

function SectionLoading() {
  return (
    <div className="flex items-center justify-center py-10 text-muted-foreground">
      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
      Carregando…
    </div>
  );
}

function SectionError({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-destructive">
      <AlertCircle className="h-5 w-5" />
      {message}
    </div>
  );
}

export function StatsCards() {
  const [base, setBase] = useState<StatsResponse | null>(null);
  const [usage, setUsage] = useState<UsageStatsResponse | null>(null);
  const [baseError, setBaseError] = useState("");
  const [usageError, setUsageError] = useState("");
  const [baseLoading, setBaseLoading] = useState(true);
  const [usageLoading, setUsageLoading] = useState(true);

  useEffect(() => {
    getStats()
      .then(setBase)
      .catch((e) => setBaseError(e instanceof Error ? e.message : "Erro ao carregar"))
      .finally(() => setBaseLoading(false));

    getUsageStats()
      .then(setUsage)
      .catch((e) => setUsageError(e instanceof Error ? e.message : "Erro ao carregar"))
      .finally(() => setUsageLoading(false));
  }, []);

  const satisfactionRate = (() => {
    if (!usage) return "—";
    const total = usage.thumbs_up + usage.thumbs_down;
    if (total === 0) return "—";
    return `${Math.round((usage.thumbs_up / total) * 100)}%`;
  })();

  return (
    <div className="space-y-8">
      {/* Seção: Base de Conhecimento */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Base de Conhecimento</h2>
        <Separator className="mb-4" />
        {baseLoading ? (
          <SectionLoading />
        ) : baseError ? (
          <SectionError message={baseError} />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Documentos"
              value={base?.documents?.toLocaleString("pt-BR") ?? "—"}
              icon={FileText}
            />
            <StatCard
              label="Versões de Documentos"
              value={base?.versions?.toLocaleString("pt-BR") ?? "—"}
              icon={Layers}
            />
            <StatCard
              label="Documentos sem Indexação"
              value={base?.docs_without_chunks?.toLocaleString("pt-BR") ?? "—"}
              icon={AlertTriangle}
            />
          </div>
        )}
      </div>

      {/* Seção: Uso & Qualidade */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Uso & Qualidade</h2>
        <Separator className="mb-4" />
        {usageLoading ? (
          <SectionLoading />
        ) : usageError ? (
          <SectionError message={usageError} />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Total de Conversas"
              value={usage?.total_sessions?.toLocaleString("pt-BR") ?? "—"}
              icon={MessageSquare}
            />
            <StatCard
              label="Total de Mensagens"
              value={usage?.total_messages?.toLocaleString("pt-BR") ?? "—"}
              icon={MessagesSquare}
            />
            <StatCard
              label="Feedbacks Positivos"
              value={usage?.thumbs_up?.toLocaleString("pt-BR") ?? "—"}
              icon={ThumbsUp}
            />
            <StatCard
              label="Feedbacks Negativos"
              value={usage?.thumbs_down?.toLocaleString("pt-BR") ?? "—"}
              icon={ThumbsDown}
            />
            <StatCard
              label="Taxa de Satisfação"
              value={satisfactionRate}
              icon={TrendingUp}
            />
          </div>
        )}
      </div>
    </div>
  );
}
