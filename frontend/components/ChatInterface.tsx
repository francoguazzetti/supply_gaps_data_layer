"use client";

import { useChat } from "ai/react";
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import ChatInput from "./ChatInput";

// Shopping bag icon — no icon library dependency
const BotIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    className="w-5 h-5"
    stroke="currentColor"
    strokeWidth={1.5}
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007z"
    />
  </svg>
);

const WELCOME_PROMPTS = [
  "¿Cuál es el mejor precio de un iPhone 15 en MercadoLibre?",
  "Busca notebooks Lenovo por menos de $500.000",
  "¿Qué auriculares Sony tienen mejor descuento hoy?",
  "Compara zapatillas Nike Air Max disponibles",
];

export default function ChatInterface() {
  const { messages, input, handleInputChange, handleSubmit, isLoading, error } =
    useChat({ api: "/api/chat" });

  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom whenever messages update or tokens stream in
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // True while the scraper is running (LLM hasn't started streaming yet)
  const lastMsg = messages[messages.length - 1];
  const isThinking = isLoading && lastMsg?.role === "user";

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-64 bg-[#171717] border-r border-[#2f2f2f] p-4 shrink-0">
        <div className="flex items-center gap-2 mb-6">
          <BotIcon />
          <span className="font-semibold text-sm">MercadoLibre AI</span>
        </div>
        <button
          className="w-full text-left px-3 py-2 text-sm text-gray-400 hover:bg-[#2f2f2f] rounded-lg transition-colors"
          onClick={() => window.location.reload()}
        >
          + Nueva conversación
        </button>
        <p className="mt-4 text-xs text-gray-600 px-3">
          Precios actualizados en tiempo real desde MercadoLibre Argentina.
        </p>
      </aside>

      {/* Main area */}
      <main className="flex flex-col flex-1 min-w-0">
        {/* Message list */}
        <div className="flex-1 overflow-y-auto chat-scrollbar">
          {messages.length === 0 ? (
            /* Welcome screen */
            <div className="flex flex-col items-center justify-center h-full px-4 text-center">
              <div className="w-12 h-12 rounded-full bg-[#2f2f2f] flex items-center justify-center mb-4">
                <BotIcon />
              </div>
              <h1 className="text-2xl font-semibold mb-2">MercadoLibre AI</h1>
              <p className="text-gray-400 mb-8 max-w-md">
                Tu asistente de compras inteligente. Preguntame sobre precios,
                descuentos y disponibilidad de productos.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl w-full">
                {WELCOME_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() =>
                      handleInputChange({
                        target: { value: prompt },
                      } as React.ChangeEvent<HTMLTextAreaElement>)
                    }
                    className="text-left p-3 text-sm bg-[#2f2f2f] hover:bg-[#3a3a3a] rounded-xl border border-[#3a3a3a] transition-colors text-gray-300"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto w-full px-4 py-6 space-y-6">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${
                    msg.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <div className="w-8 h-8 rounded-full bg-[#2f2f2f] flex items-center justify-center shrink-0 mt-1">
                      <BotIcon />
                    </div>
                  )}
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-[#2f2f2f] text-white rounded-br-sm"
                        : "bg-transparent text-gray-100"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <div className="prose prose-invert prose-sm max-w-none">
                      <ReactMarkdown
                        components={{
                          a: ({ children, href }) => (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-400 hover:underline"
                            >
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    )}
                  </div>
                </div>
              ))}

              {/* Thinking indicator — shown while the scraper runs before first token */}
              {isThinking && (
                <div className="flex gap-3 justify-start">
                  <div className="w-8 h-8 rounded-full bg-[#2f2f2f] flex items-center justify-center shrink-0">
                    <BotIcon />
                  </div>
                  <div className="px-4 py-3 rounded-2xl">
                    <div className="flex gap-1 items-center h-5">
                      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      Buscando en MercadoLibre…
                    </p>
                  </div>
                </div>
              )}

              {error && (
                <div className="text-center text-sm text-red-400 bg-red-900/20 rounded-lg py-2 px-4">
                  Error: {error.message}
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input bar */}
        <ChatInput
          input={input}
          isLoading={isLoading}
          onChange={handleInputChange}
          onSubmit={handleSubmit}
        />
      </main>
    </div>
  );
}
