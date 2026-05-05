"use client";

import {
  useRef,
  useEffect,
  KeyboardEvent,
  FormEvent,
  ChangeEvent,
} from "react";

interface ChatInputProps {
  input: string;
  isLoading: boolean;
  onChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
}

export default function ChatInput({
  input,
  isLoading,
  onChange,
  onSubmit,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow textarea up to 200px, then scroll
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !isLoading) {
      e.preventDefault();
      e.currentTarget.form?.requestSubmit();
    }
  };

  return (
    <div className="border-t border-[#2f2f2f] bg-[#212121] px-4 py-4">
      <form
        onSubmit={onSubmit}
        className="max-w-3xl mx-auto flex items-end gap-2 bg-[#2f2f2f] rounded-2xl px-4 py-3"
      >
        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={onChange}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          placeholder="Preguntame sobre precios en MercadoLibre…"
          className="flex-1 bg-transparent resize-none outline-none text-sm text-white placeholder:text-gray-500 max-h-[200px] overflow-y-auto disabled:opacity-50"
        />

        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          aria-label="Enviar"
          className="shrink-0 w-8 h-8 rounded-full bg-white text-black flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-200 transition-colors"
        >
          {isLoading ? (
            // Spinner while loading
            <svg
              className="w-4 h-4 animate-spin"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
                strokeDasharray="31.4"
                strokeDashoffset="10"
              />
            </svg>
          ) : (
            // Arrow-up icon
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
              <path d="M12 4l8 8h-5v8H9v-8H4l8-8z" />
            </svg>
          )}
        </button>
      </form>

      <p className="text-center text-xs text-gray-600 mt-2">
        Enter para enviar · Shift+Enter para nueva línea
      </p>
    </div>
  );
}
