import React, { useState, useRef, useEffect } from 'react';
import ChatWindow from './ChatWindow';
import InputArea from './InputArea';
import { Bot, X, Maximize2 } from 'lucide-react';

function ChatPanel({ docId, onClose, isOpen }) {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content: docId === 'Global Mode' 
        ? "Hello! I'm your Regulatory AI Assistant. I can help you search and analyze documents across the FDA, EMA, and CDSCO. How can I assist you today?"
        : `Hello! I'm your Regulatory AI Assistant. I am currently analyzing **${docId}**. What would you like to know about it?`,
      sources: []
    }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Auto-scroll logic
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isOpen]);

  const handleSendMessage = async (text, country = null, source = null) => {
    if (!text.trim()) return;
    
    const newUserMsg = { id: Date.now().toString(), role: 'user', content: text };
    setMessages(prev => [...prev, newUserMsg]);
    setIsLoading(true);

    try {
      const response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: text,
          doc_id: docId || null,
          country: country,
          source: source,
          top_k: 5
        })
      });

      if (!response.ok) throw new Error('API request failed');
      
      const data = await response.json();
      
      const aiResponse = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.answer,
        sources: data.sources || [],
        forms: data.forms || []
      };
      setMessages(prev => [...prev, aiResponse]);
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: "⚠️ **Error:** Unable to reach the AI service. Please ensure the backend is running.",
        sources: []
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div 
      className={`fixed top-0 right-0 h-full w-full sm:w-[500px] xl:w-[600px] bg-white border-l border-slate-200 shadow-2xl transition-transform duration-500 z-50 flex flex-col ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}
    >
      {/* Panel Header */}
      <div className="h-16 border-b border-slate-100 flex items-center justify-between px-6 shrink-0 bg-white/80 backdrop-blur-md relative z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-[#0f766e]/10 flex items-center justify-center border border-[#0f766e]/20">
            <Bot className="w-4 h-4 text-[#0f766e]" />
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-wide text-slate-900">Regulatory AI</h3>
            <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">
              {docId === 'Global Mode' ? 'Universal Knowledge' : `Context: ${docId}`}
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <button className="p-2 text-slate-400 hover:text-slate-900 transition-colors rounded-lg hover:bg-slate-100">
            <Maximize2 className="w-4 h-4" />
          </button>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-900 transition-colors rounded-lg hover:bg-slate-100">
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Embedded Chat Interface */}
      <div className="flex-1 flex flex-col relative overflow-hidden bg-slate-50/50">
        <div className="absolute top-0 w-full h-12 bg-gradient-to-b from-white to-transparent pointer-events-none z-10" />
        
        {/* Messages Auto-Scroll Container */}
        <div className="flex-1 overflow-y-auto w-full relative z-0 hide-scrollbar pt-6 px-4">
          <ChatWindow messages={messages} isLoading={isLoading} messagesEndRef={messagesEndRef} />
        </div>

        {/* Input Dock */}
        <div className="w-full shrink-0 pb-6 pt-4 px-4 bg-gradient-to-t from-white via-white to-transparent z-20">
          <InputArea onSend={handleSendMessage} isLoading={isLoading} />
        </div>
      </div>
    </div>
  );
}

export default ChatPanel;
