"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

interface ChatContextValue {
  activeSessionId: string | null;
  setActiveSessionId: (id: string | null) => void;
}

const ChatContext = createContext<ChatContextValue>({
  activeSessionId: null,
  setActiveSessionId: () => {},
});

export function ChatProvider({ children }: { children: ReactNode }) {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  return (
    <ChatContext.Provider value={{ activeSessionId, setActiveSessionId }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext() {
  return useContext(ChatContext);
}
