"use client";

import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SendHorizontal, Filter } from "lucide-react";
import { getEquipments, type Equipment } from "@/lib/api";

interface ChatInputProps {
  onSend: (message: string, equipmentFilter?: string | null) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [equipments, setEquipments] = useState<Equipment[]>([]);
  const [selectedEquipment, setSelectedEquipment] = useState<string>("all");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    getEquipments().then(setEquipments).catch(() => {});
  }, []);

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    const filter = selectedEquipment === "all" ? null : selectedEquipment;
    onSend(trimmed, filter);
    setValue("");
    textareaRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="space-y-2 border-t bg-background p-4">
      {equipments.length > 0 && (
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          <Select value={selectedEquipment} onValueChange={setSelectedEquipment}>
            <SelectTrigger className="h-8 w-auto min-w-[180px] text-xs">
              <SelectValue placeholder="Filtrar equipamento" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os equipamentos</SelectItem>
              {equipments.map((eq) => (
                <SelectItem key={eq.key} value={eq.key}>
                  {eq.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <div className="flex items-end gap-2">
        <Textarea
          ref={textareaRef}
          placeholder="Faça uma pergunta sobre os manuais…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          className="max-h-32 min-h-[2.5rem] resize-none"
        />
        <Button
          size="icon"
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
        >
          <SendHorizontal className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
