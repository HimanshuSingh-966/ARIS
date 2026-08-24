import { useState, useRef, useEffect } from 'react';
import ChatWindow from './ChatWindow';
import InputArea from './InputArea';
import { Bot, X } from 'lucide-react';
import { API_BASE } from '../lib/api';

// The backend now answers with real status codes instead of embedding the error
// text in a 200 response, so the user can be told which failure happened.
function errorMessage(status) {
  switch (status) {
    case 429:
      return "⚠️ **Slow down a little.** You've sent too many questions in a short time — please wait a moment and try again.";
    case 401:
    case 403:
    case 503:
      return "⚠️ **The assistant isn't configured correctly.** Please contact the administrator.";
    case 502:
    case 504:
      return '⚠️ **The assistant is temporarily unavailable.** Please try again in a moment.';
    default:
      return status
        ? `⚠️ **Something went wrong** (error ${status}). Please try again.`
        : '⚠️ **Unable to reach the AI service.** Check your connection and try again.';
  }
}

function ChatPanel({ docId, docLabel, onClose, isOpen }) {
  // The absence of a docId *is* global mode. docId is a database key that gets
  // sent to the API as a filter, so it must never carry a display label.
  const isGlobal = !docId;
  const label = docLabel || docId;

  const welcomeText = isGlobal
    ? "Hello! I'm your Regulatory AI Assistant. I can help you search and analyze documents across the FDA, EMA, and CDSCO. How can I assist you today?"
    : `Hello! I'm your Regulatory AI Assistant. I am currently analyzing **${label}**. What would you like to know about it?`;

  const [messages, setMessages] = useState([
    { id: 'welcome', role: 'assistant', content: welcomeText, sources: [] }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // The panel is mounted for the whole page lifetime, so docLabel resolves from its
  // async lookup *after* this greeting was first rendered. Rewrite it in place
  // rather than remounting, which would discard the conversation.
  useEffect(() => {
    setMessages(prev =>
      prev.map(m => (m.id === 'welcome' ? { ...m, content: welcomeText } : m))
    );
  }, [welcomeText]);

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
      const response = await fetch(`${API_BASE}/chat`, {
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

      if (!response.ok) {
        // Carry the status so the message can name the actual failure. This branch
        // was unreachable until the API stopped returning 200 for its own errors.
        const err = new Error(`Chat request failed with ${response.status}`);
        err.status = response.status;
        throw err;
      }

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
        content: errorMessage(error.status),
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
              {isGlobal ? 'Universal Knowledge' : `Context: ${label}`}
            </p>
          </div>
        </div>

        {/* The Maximize2 button that used to sit here had no onClick — it rendered
            as an interactive control and did nothing at all when clicked. */}
        <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-900 transition-colors rounded-lg hover:bg-slate-100">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Embedded Chat Interface */}
      <div className="flex-1 flex flex-col relative overflow-hidden bg-slate-50/50">
        <div className="absolute top-0 w-full h-12 bg-gradient-to-b from-white to-transparent pointer-events-none z-10" />
        
        {/* Messages Auto-Scroll Container
            `overflow-y-auto` used to be here as well as on ChatWindow's own root,
            giving the message list two nested scrollers. scrollIntoView then acted
            on the inner one while the outer kept its own offset, so auto-scroll
            landed short of the newest message. ChatWindow owns messagesEndRef, so
            it keeps the scroll; this stays a plain flex column to give its
            `flex-1` a height to resolve against. */}
        <div className="flex-1 flex flex-col w-full relative z-0 min-h-0 pt-6 px-4">
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
