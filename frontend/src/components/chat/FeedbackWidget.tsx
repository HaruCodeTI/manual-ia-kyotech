"use client";

import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { submitFeedback } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { FeedbackRating } from "@/types";

type FeedbackState = "idle" | "loading" | "done" | "error";

interface FeedbackWidgetProps {
  messageId: string;
}

export function FeedbackWidget({ messageId }: FeedbackWidgetProps) {
  const [feedbackState, setFeedbackState] = useState<FeedbackState>("idle");
  const [selected, setSelected] = useState<FeedbackRating | null>(null);

  async function handleFeedback(rating: FeedbackRating) {
    if (feedbackState !== "idle") return;
    setFeedbackState("loading");
    setSelected(rating);
    try {
      await submitFeedback(messageId, rating);
      setFeedbackState("done");
    } catch {
      setFeedbackState("error");
      setSelected(null);
    }
  }

  if (feedbackState === "done") {
    return (
      <div className="flex items-center gap-1 text-xs text-muted-foreground/60">
        {selected === "thumbs_up" ? (
          <ThumbsUp className="h-3.5 w-3.5 text-green-500" />
        ) : (
          <ThumbsDown className="h-3.5 w-3.5 text-red-400" />
        )}
        <span>Obrigado pelo feedback</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => handleFeedback("thumbs_up")}
        disabled={feedbackState === "loading"}
        title="Resposta útil"
        className={cn(
          "rounded p-1 transition-colors hover:bg-green-500/10 hover:text-green-500",
          "text-muted-foreground/40 disabled:cursor-not-allowed",
          feedbackState === "error" && "text-muted-foreground/20",
        )}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button
        onClick={() => handleFeedback("thumbs_down")}
        disabled={feedbackState === "loading"}
        title="Resposta incorreta ou incompleta"
        className={cn(
          "rounded p-1 transition-colors hover:bg-red-500/10 hover:text-red-400",
          "text-muted-foreground/40 disabled:cursor-not-allowed",
          feedbackState === "error" && "text-muted-foreground/20",
        )}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>
      {feedbackState === "error" && (
        <span className="text-xs text-destructive">Erro ao registrar</span>
      )}
    </div>
  );
}
