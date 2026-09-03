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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
    };

    const thinkingMessage: Message = {
      id: "thinking-" + Date.now(),
      role: "assistant",
      content: "Thinking...",
      isThinking: true,
    };

    setMessages((prev) => [...prev, userMessage, thinkingMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await api.askQA(userMessage.content);
      
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

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] bg-fintrix-surface/50 border border-fintrix-border rounded-2xl overflow-hidden backdrop-blur-sm animate-fadeIn">
      {/* Header */}
      <div className="p-4 border-b border-fintrix-border/50 bg-fintrix-surface-2/80 flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-fintrix-primary to-fintrix-accent flex items-center justify-center text-xl shadow-lg shadow-fintrix-primary/20">
          🤖
        </div>
        <div>
          <h2 className="text-lg font-bold gradient-text">Settlement Q&A Agent</h2>
          <p className="text-xs text-fintrix-text-dimmed">Powered by Gemini 2.0 Flash</p>
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}>
            
            {/* Message Bubble */}
            <div className={`max-w-[80%] rounded-2xl p-4 ${
              msg.role === "user" 
                ? "bg-fintrix-primary/10 text-fintrix-primary border border-fintrix-primary/20 rounded-tr-none shadow-sm shadow-fintrix-primary/5" 
                : "bg-fintrix-surface-2 border border-fintrix-border/50 text-fintrix-text rounded-tl-none shadow-sm"
            }`}>
              
              {msg.isThinking ? (
                <div className="flex items-center gap-2 text-fintrix-text-muted">
                  <div className="w-4 h-4 border-2 border-fintrix-text-dimmed border-t-fintrix-text-muted rounded-full animate-spin" />
                  <span className="text-sm">{msg.content}</span>
                </div>
              ) : (
                <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
              )}
            </div>

            {/* SQL Query Collapsible */}
            {msg.sql && (
              <div className="mt-2 ml-4 max-w-[80%] text-xs animate-fadeIn">
                <details className="group cursor-pointer">
                  <summary className="text-fintrix-text-dimmed hover:text-fintrix-text-muted transition-colors font-medium select-none">
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
              <div className="mt-3 w-full animate-fadeIn">
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
                            <td key={j} className="px-4 py-2.5 text-fintrix-text-dimmed">
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
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-fintrix-border/50 bg-fintrix-surface-2/30">
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about your settlements..."
            disabled={isLoading}
            className="w-full bg-fintrix-surface-2 border border-fintrix-border rounded-xl py-3 pl-4 pr-12 text-sm text-fintrix-text placeholder:text-fintrix-text-dimmed focus:outline-none focus:border-fintrix-primary/50 focus:ring-1 focus:ring-fintrix-primary/50 transition-all disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="absolute right-2 p-2 rounded-lg text-fintrix-primary hover:bg-fintrix-primary/10 transition-colors disabled:opacity-50 disabled:hover:bg-transparent"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
