"use client";

import { createContext, useContext, useState, useCallback } from "react";

interface ViewerState {
  versionId: string;
  pageNumber: number;
  sourceFilename: string;
  equipmentKey: string;
  docType: string;
  publishedDate: string;
}

interface ViewerContextType {
  viewer: ViewerState | null;
  isOpen: boolean;
  openViewer: (state: ViewerState) => void;
  closeViewer: () => void;
  goToPage: (page: number) => void;
}

const ViewerContext = createContext<ViewerContextType | null>(null);

export function ViewerProvider({ children }: { children: React.ReactNode }) {
  const [viewer, setViewer] = useState<ViewerState | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const openViewer = useCallback((state: ViewerState) => {
    setViewer(state);
    setIsOpen(true);
  }, []);

  const closeViewer = useCallback(() => {
    setIsOpen(false);
  }, []);

  const goToPage = useCallback((page: number) => {
    setViewer((prev) => (prev ? { ...prev, pageNumber: page } : null));
  }, []);

  return (
    <ViewerContext.Provider
      value={{ viewer, isOpen, openViewer, closeViewer, goToPage }}
    >
      {children}
    </ViewerContext.Provider>
  );
}

export function useViewer() {
  const ctx = useContext(ViewerContext);
  if (!ctx) throw new Error("useViewer must be used within ViewerProvider");
  return ctx;
}
