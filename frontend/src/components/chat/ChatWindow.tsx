"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { askQuestion, getSessionMessages } from "@/lib/api";
import { useChatContext } from "@/lib/chat-context";
import type { Message, ChatSessionDetail } from "@/types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { Bot, Loader2 } from "lucide-react";

export function ChatWindow() {
  const { activeSessionId, setActiveSessionId } = useChatContext();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sessionIdRef = useRef<string | null>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      sessionIdRef.current = null;
      return;
    }

    if (activeSessionId === sessionIdRef.current) return;

    setLoadingSession(true);
    getSessionMessages(activeSessionId)
      .then((data: ChatSessionDetail) => {
        sessionIdRef.current = activeSessionId;
        setMessages(
          data.messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            citations: m.citations ?? undefined,
          }))
        );
      })
      .catch(() => {
        setMessages([]);
        setActiveSessionId(null);
      })
      .finally(() => setLoadingSession(false));
  }, [activeSessionId, setActiveSessionId]);

  async function handleSend(question: string, equipmentFilter?: string | null) {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
    };

    const loadingMsg: Message = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setIsLoading(true);

    try {
      const data = await askQuestion(
        question,
        equipmentFilter,
        sessionIdRef.current,
      );

      if (!sessionIdRef.current && data.session_id) {
        sessionIdRef.current = data.session_id;
        setActiveSessionId(data.session_id);
      }

      const assistantMsg: Message = {
        id: loadingMsg.id,
        role: "assistant",
        content: data.answer,
        citations: data.citations,
      };

      setMessages((prev) =>
        prev.map((m) => (m.id === loadingMsg.id ? assistantMsg : m))
      );
    } catch (err) {
      const errorMsg: Message = {
        id: loadingMsg.id,
        role: "assistant",
        content: `Erro ao buscar resposta: ${err instanceof Error ? err.message : "Erro desconhecido"}`,
      };
      setMessages((prev) =>
        prev.map((m) => (m.id === loadingMsg.id ? errorMsg : m))
      );
    } finally {
      setIsLoading(false);
    }
  }

  if (loadingSession) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
              <Bot className="h-8 w-8 text-primary" />
            </div>
            <div className="space-y-2">
              <h2 className="text-lg font-semibold tracking-tight text-foreground">
                Como posso ajudar?
              </h2>
              <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
                Pergunte sobre manuais e informativos Fujifilm.
                As respostas incluem citações com links para o PDF na página exata.
              </p>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-5 py-6">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
      <div className="mx-auto w-full max-w-3xl">
        <ChatInput onSend={handleSend} disabled={isLoading} />
      </div>
    </div>
  );
}
