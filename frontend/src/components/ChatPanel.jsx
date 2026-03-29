import React, { useState, useRef, useEffect } from 'react';
import ChatWindow from './ChatWindow';
import InputArea from './InputArea';
import { Bot, X, Maximize2 } from 'lucide-react';

function ChatPanel({ docId, onClose, isOpen }) {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content: `Hello! I'm your Regulatory AI Assistant. I am currently analyzing **${docId || 'this document'}**. What would you like to know about it?`,
      sources: []
    }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Auto-scroll logic
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isOpen]);

  const handleSendMessage = async (text) => {
    if (!text.trim()) return;
    
    const newUserMsg = { id: Date.now().toString(), role: 'user', content: text };
    setMessages(prev => [...prev, newUserMsg]);
    setIsLoading(true);

    try {
      // MOCK API CALL - This will be replaced by the actual FastAPI integeration
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const aiResponse = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `This is a simulated AI response regarding the document **${docId}**. The actual FastAPI integration will be hooked up shortly via the \`/api/chat\` endpoint.`,
        sources: [
          { page: 12, text: "Mocked citation from the text." }
        ]
      };
      setMessages(prev => [...prev, aiResponse]);
    } catch (error) {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: "⚠️ **Error:** Unable to reach the AI service.",
        sources: []
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div 
      className={`fixed top-0 right-0 h-full w-full sm:w-[500px] xl:w-[600px] bg-[#020303] border-l border-white/5 shadow-2xl shadow-black transition-transform duration-500 z-50 flex flex-col ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}
    >
      {/* Panel Header */}
      <div className="h-16 border-b border-white/[0.04] flex items-center justify-between px-6 shrink-0 bg-[#040707] relative z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
            <Bot className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-wide text-white">Document Assistant</h3>
            <p className="text-[10px] text-muted/70 uppercase tracking-widest font-bold">Context: {docId}</p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <button className="p-2 text-muted hover:text-white transition-colors rounded-lg hover:bg-white/5">
            <Maximize2 className="w-4 h-4" />
          </button>
          <button onClick={onClose} className="p-2 text-muted hover:text-white transition-colors rounded-lg hover:bg-white/5">
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Embedded Chat Interface */}
      <div className="flex-1 flex flex-col relative overflow-hidden bg-mesh">
        <div className="absolute top-0 w-full h-12 bg-gradient-to-b from-[#020303] to-transparent pointer-events-none z-10" />
        
        {/* Messages Auto-Scroll Container */}
        <div className="flex-1 overflow-y-auto w-full relative z-0 hide-scrollbar pt-6 px-4">
          <ChatWindow messages={messages} isLoading={isLoading} messagesEndRef={messagesEndRef} />
        </div>

        {/* Input Dock */}
        <div className="w-full shrink-0 pb-6 pt-4 px-4 bg-gradient-to-t from-[#020303] via-[#020303] to-transparent z-20">
          <InputArea onSend={handleSendMessage} isLoading={isLoading} />
        </div>
      </div>
    </div>
  );
}

export default ChatPanel;
