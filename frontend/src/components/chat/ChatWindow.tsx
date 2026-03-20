"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { askQuestion, getSessionMessages } from "@/lib/api";
import { useChatContext } from "@/lib/chat-context";
import type { Message, ChatSessionDetail } from "@/types";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { Loader2 } from "lucide-react";
import { Bot } from "lucide-react";
import { useUser } from "@clerk/nextjs";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";

export function ChatWindow() {
  const { activeSessionId, setActiveSessionId } = useChatContext();
  const { user } = useUser();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [hasStarted, setHasStarted] = useState(false);
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
      setHasStarted(false);
      sessionIdRef.current = null;
      return;
    }

    if (activeSessionId === sessionIdRef.current) return;

    setLoadingSession(true);
    getSessionMessages(activeSessionId)
      .then((data: ChatSessionDetail) => {
        sessionIdRef.current = activeSessionId;
        const mapped = data.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          citations: m.citations ?? undefined,
        }));
        setMessages(mapped);
        setHasStarted(mapped.length > 0);
      })
      .catch(() => {
        setMessages([]);
        setHasStarted(false);
        setActiveSessionId(null);
      })
      .finally(() => setLoadingSession(false));
  }, [activeSessionId, setActiveSessionId]);

  async function handleSend(question: string, equipmentFilter?: string | null) {
    setHasStarted(true);

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
        message_id: data.message_id,
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

  const firstName = user?.firstName ?? "";
  const greeting = firstName ? `Olá, ${firstName}` : "Olá!";

  return (
    <LayoutGroup>
      {loadingSession ? (
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="flex h-full flex-col bg-background">
          <AnimatePresence mode="wait">
            {!hasStarted ? (
              /* Welcome state */
              <motion.div
                key="welcome"
                className="flex flex-1 flex-col justify-center gap-4 px-4"
                initial={{ opacity: 1 }}
                exit={{ opacity: 0, transition: { duration: 0.2 } }}
              >
                <div className="mx-auto w-full max-w-[600px]">
                  <div className="mb-1 flex items-center gap-2">
                    <Bot className="h-5 w-5 text-primary" />
                    <span className="text-sm text-muted-foreground">{greeting}</span>
                  </div>
                  <h2 className="text-xl font-bold sm:text-2xl">
                    Por onde começamos?
                  </h2>
                </div>

                <motion.div
                  layoutId="chat-input"
                  className="mx-auto w-full max-w-[600px] rounded-2xl shadow-lg"
                  style={{ zIndex: 10 }}
                  transition={{ duration: 0.4, ease: "easeInOut" }}
                >
                  <ChatInput
                    onSend={handleSend}
                    disabled={isLoading}
                    variant="welcome"
                  />
                </motion.div>
              </motion.div>
            ) : (
              /* Chat state */
              <motion.div
                key="chat"
                className="flex flex-1 flex-col overflow-hidden"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: 0.2 } }}
              >
                <div ref={scrollRef} className="flex-1 overflow-y-auto px-4">
                  <div className="mx-auto max-w-3xl space-y-5 py-6">
                    {messages.map((msg) => (
                      <MessageBubble key={msg.id} message={msg} />
                    ))}
                    <div ref={bottomRef} />
                  </div>
                </div>

                <motion.div
                  layoutId="chat-input"
                  className="mx-auto w-full max-w-3xl"
                  style={{ zIndex: 10 }}
                  transition={{ duration: 0.4, ease: "easeInOut" }}
                >
                  <ChatInput
                    onSend={handleSend}
                    disabled={isLoading}
                    variant="bottom"
                  />
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </LayoutGroup>
  );
}
