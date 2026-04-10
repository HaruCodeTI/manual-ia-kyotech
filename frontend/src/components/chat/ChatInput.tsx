"use client";

import {
  useRef,
  useState,
  useEffect,
  forwardRef,
  useImperativeHandle,
  type KeyboardEvent,
} from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { SendHorizontal } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string, equipmentFilter?: string | null) => void;
  disabled?: boolean;
  variant?: "welcome" | "bottom";
}

export interface ChatInputHandle {
  focus: () => void;
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  function ChatInput({ onSend, disabled, variant = "bottom" }, ref) {
    const [value, setValue] = useState("");
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useImperativeHandle(ref, () => ({
      focus: () => textareaRef.current?.focus(),
    }));

    useEffect(() => {
      textareaRef.current?.focus();
    }, []);

    function handleSubmit() {
      const trimmed = value.trim();
      if (!trimmed || disabled) return;
      onSend(trimmed, null);
      setValue("");
      textareaRef.current?.focus();
    }

    function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    }

    const containerClass =
      variant === "welcome"
        ? "space-y-2 p-4"
        : "space-y-2 border-t bg-background/80 p-4 backdrop-blur-sm";

    return (
      <div className={containerClass}>
        <div className="flex items-end gap-2">
          <Textarea
            ref={textareaRef}
            placeholder="Faça uma pergunta sobre os manuais…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            rows={1}
            className="max-h-32 min-h-[2.5rem] resize-none rounded-xl border-border/50 bg-card shadow-sm focus-visible:ring-primary/30"
          />
          <Button
            size="icon"
            onClick={handleSubmit}
            disabled={disabled || !value.trim()}
            className="shrink-0 rounded-xl shadow-sm"
          >
            <SendHorizontal className="h-4 w-4" />
          </Button>
        </div>
      </div>
    );
  }
);
