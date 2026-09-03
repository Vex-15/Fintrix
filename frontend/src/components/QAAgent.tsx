import { useState, useRef, useEffect } from "react";
import { api } from "../api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sql?: string;
  results?: any[];
  isThinking?: boolean;
}

const SUGGESTIONS = [
  "Show unresolved exceptions",
  "Total GST deducted today",
  "Top 5 fee discrepancies",
  "How many auto-resolved?",
  "Settlement summary",
];

export default function QAAgent() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Hello! I'm your Settlement Q&A Agent. Ask me questions about your settlements, exceptions, fees, or taxes. For example, 'What was the total GST deducted yesterday?' or 'How many exceptions are currently escalated?'",
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const submitQuestion = async (question: string) => {
    if (!question.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: question,
    };

    const thinkingMessage: Message = {
      id: "thinking-" + Date.now(),
      role: "assistant",
      content: "",
      isThinking: true,
    };

    setMessages((prev) => [...prev, userMessage, thinkingMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await api.askQA(question);
      
      setMessages((prev) => 
        prev.map(msg => msg.id === thinkingMessage.id ? {
          ...msg,
          id: Date.now().toString(),
          role: "assistant",
          content: response.answer || "I found some results but couldn't generate a summary.",
          sql: response.sql,
          results: response.data,
          isThinking: false,
        } : msg)
      );
    } catch (err: any) {
      setMessages((prev) => 
        prev.map(msg => msg.id === thinkingMessage.id ? {
          ...msg,
          id: Date.now().toString(),
          role: "assistant",
          content: `Error: ${err.message || "Failed to get an answer"}`,
          isThinking: false,
        } : msg)
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    submitQuestion(input);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-12rem)] bg-fintrix-surface/50 border border-fintrix-border rounded-2xl overflow-hidden backdrop-blur-sm">
      {/* Header */}
      <div className="p-4 border-b border-fintrix-border/50 bg-fintrix-surface-2/80 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-fintrix-primary to-fintrix-accent flex items-center justify-center shadow-lg shadow-fintrix-primary/20">
          <span className="material-symbols-outlined icon-filled text-white" style={{ fontSize: "20px" }}>smart_toy</span>
        </div>
        <div>
          <h2 className="text-base font-semibold text-fintrix-text">Settlement Q&A Agent</h2>
          <p className="text-[11px] text-fintrix-text-dimmed">Powered by Gemini 2.0 Flash</p>
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
            {/* Avatar */}
            {msg.role === "assistant" && (
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-fintrix-primary/20 to-fintrix-accent/20 flex items-center justify-center shrink-0 mt-0.5">
                <span className="material-symbols-outlined text-fintrix-primary" style={{ fontSize: "14px" }}>smart_toy</span>
              </div>
            )}

            <div className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"} max-w-[80%]`}>
              {/* Message Bubble */}
              <div className={`rounded-2xl p-4 ${
                msg.role === "user" 
                  ? "bg-fintrix-primary/10 text-fintrix-text border border-fintrix-primary/20 rounded-tr-md" 
                  : "bg-fintrix-surface-2 border border-fintrix-border/50 text-fintrix-text rounded-tl-md"
              }`}>
                
                {msg.isThinking ? (
                  <div className="flex items-center gap-2 text-fintrix-text-muted py-1 px-1">
                    <div className="typing-dots">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                )}
              </div>

              {/* SQL Query Collapsible */}
              {msg.sql && (
                <div className="mt-2 w-full text-xs">
                  <details className="group cursor-pointer">
                    <summary className="text-fintrix-text-dimmed hover:text-fintrix-text-muted transition-colors font-medium select-none flex items-center gap-1.5">
                      <span className="material-symbols-outlined icon-sm">code</span>
                      View generated SQL
                    </summary>
                    <div className="mt-2 p-3 bg-black/40 rounded-lg border border-fintrix-border/50 overflow-x-auto shadow-inner">
                      <code className="text-fintrix-primary font-mono whitespace-pre">{msg.sql}</code>
                    </div>
                  </details>
                </div>
              )}

              {/* Data Results Table */}
              {msg.results && msg.results.length > 0 && (
                <div className="mt-3 w-full">
                  <div className="overflow-x-auto rounded-lg border border-fintrix-border/50 shadow-sm">
                    <table className="w-full text-xs text-left border-collapse bg-fintrix-surface-2/30">
                      <thead className="bg-fintrix-surface-2/80">
                        <tr>
                          {Object.keys(msg.results[0]).map((key) => (
                            <th key={key} className="px-4 py-2.5 font-medium text-fintrix-text-muted border-b border-fintrix-border/50 uppercase tracking-wider">{key}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {msg.results.map((row, i) => (
                          <tr key={i} className="border-b border-fintrix-border/30 last:border-b-0 hover:bg-fintrix-surface-2/50 transition-colors">
                            {Object.values(row).map((val: any, j) => (
                              <td key={j} className="px-4 py-2.5 text-fintrix-text-dimmed font-mono">
                                {typeof val === 'number' 
                                  ? val.toLocaleString() 
                                  : val === null 
                                    ? '—' 
                                    : String(val)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestion Chips */}
      {messages.length <= 1 && (
        <div className="px-5 pb-3 flex gap-2 flex-wrap">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => submitQuestion(s)}
              className="suggestion-chip"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input Area */}
      <div className="p-4 border-t border-fintrix-border/50 bg-fintrix-surface-2/30">
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about your settlements..."
            disabled={isLoading}
            className="w-full bg-fintrix-surface-2 border border-fintrix-border rounded-xl py-3 pl-4 pr-12 text-sm text-fintrix-text placeholder:text-fintrix-text-dimmed input-glow disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="absolute right-2 p-2 rounded-lg text-fintrix-primary hover:bg-fintrix-primary/10 transition-colors disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "20px" }}>send</span>
          </button>
        </form>
      </div>
    </div>
  );
}
