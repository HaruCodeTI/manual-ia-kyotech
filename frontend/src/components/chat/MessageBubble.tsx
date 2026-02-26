"use client";

import ReactMarkdown from "react-markdown";
import type { Message, Citation } from "@/types";
import { CitationBadge } from "./CitationBadge";
import { cn } from "@/lib/utils";
import { User, Bot, Loader2 } from "lucide-react";
import { type ReactNode } from "react";

interface MessageBubbleProps {
  message: Message;
}

function InlineCitation({ index, citations }: { index: number; citations: Citation[] }) {
  const citation = citations.find((c) => c.source_index === index);
  if (!citation) return <span>[Fonte {index}]</span>;
  return <CitationBadge citation={citation} />;
}

function processTextNode(text: string, citations: Citation[]): ReactNode[] {
  const parts = text.split(/(\[Fonte \d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/\[Fonte (\d+)\]/);
    if (match) {
      return <InlineCitation key={i} index={parseInt(match[1], 10)} citations={citations} />;
    }
    return part || null;
  });
}

function MarkdownWithCitations({ content, citations }: { content: string; citations: Citation[] }) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => {
          const processed = processChildren(children, citations);
          return <p className="mb-2 last:mb-0">{processed}</p>;
        },
        li: ({ children }) => {
          const processed = processChildren(children, citations);
          return <li>{processed}</li>;
        },
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>,
        h3: ({ children }) => <h3 className="mb-1 mt-3 font-semibold">{children}</h3>,
        h4: ({ children }) => <h4 className="mb-1 mt-2 font-medium">{children}</h4>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function processChildren(children: ReactNode, citations: Citation[]): ReactNode {
  if (!Array.isArray(children)) {
    if (typeof children === "string") {
      return processTextNode(children, citations);
    }
    return children;
  }
  return children.map((child, i) => {
    if (typeof child === "string") {
      return <span key={i}>{processTextNode(child, citations)}</span>;
    }
    return child;
  });
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      <div
        className={cn(
          "rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "max-w-[75%] bg-primary text-primary-foreground"
            : "max-w-full bg-muted sm:max-w-[85%]"
        )}
      >
        {message.isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Buscando nos manuais…
          </div>
        ) : isUser ? (
          <p>{message.content}</p>
        ) : (
          <div className="max-w-none">
            {message.citations && message.citations.length > 0 ? (
              <MarkdownWithCitations
                content={message.content}
                citations={message.citations}
              />
            ) : (
              <ReactMarkdown>{message.content}</ReactMarkdown>
            )}
          </div>
        )}

        {!message.isLoading &&
          message.citations &&
          message.citations.length > 0 && (
            <div className="mt-3 border-t pt-2">
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">
                Fontes referenciadas:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {message.citations.map((c) => (
                  <CitationBadge key={c.source_index} citation={c} />
                ))}
              </div>
            </div>
          )}
      </div>
    </div>
  );
}
