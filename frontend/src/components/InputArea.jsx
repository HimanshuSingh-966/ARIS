import React, { useState } from 'react';
import { Send, Globe2, FileText, Loader2 } from 'lucide-react';

function InputArea({ onSend, isLoading }) {
  const [text, setText] = useState('');
  const [country, setCountry] = useState('');
  const [source, setSource] = useState('');

  const handleSend = () => {
    if (text.trim() && !isLoading) {
      onSend(text, country || null, source || null);
      setText('');
    }
  };

  const currentFilters = [country, source].filter(Boolean).join(' • ');

  return (
    <div className="w-full relative mt-auto px-4 md:px-0 z-30 animate-fade-up">
      <div className="bg-white p-2 sm:p-3 flex flex-row gap-3 items-center border border-slate-100 shadow-xl rounded-2xl mx-1 mb-1">
        
        {/* Input field */}
        <div className="flex-1 w-full relative">
          <textarea
            className="w-full bg-transparent text-slate-900 placeholder-slate-400 focus:outline-none resize-none pt-2 sm:pt-3 px-3 min-h-[44px] sm:min-h-[52px] max-h-32 text-sm sm:text-base leading-relaxed"
            rows={1}
            placeholder="Ask about regulatory processes..."
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
        </div>

        {/* Controls and Send Button */}
        <div className="flex items-center gap-2 pl-3 border-l border-slate-100 ml-2">
          
          {/* Filters */}
          <div className="hidden sm:flex flex-col gap-1 items-end pr-2">
            <select 
              value={country} 
              onChange={e => setCountry(e.target.value)}
              className="appearance-none bg-transparent hover:bg-slate-50 text-slate-500 hover:text-slate-900 rounded px-2 py-1 text-[10px] uppercase font-bold cursor-pointer focus:outline-none transition-colors"
            >
              <option value="">Any Country</option>
              <option value="India">India</option>
              <option value="USA">USA</option>
              <option value="Europe">Europe</option>
            </select>
            
            <select 
              value={source} 
              onChange={e => setSource(e.target.value)}
              className="appearance-none bg-transparent hover:bg-slate-50 text-slate-500 hover:text-slate-900 rounded px-2 py-1 text-[10px] uppercase font-bold cursor-pointer focus:outline-none transition-colors"
            >
              <option value="">Any Source</option>
              <option value="cdsco">CDSCO</option>
              <option value="fda">FDA</option>
              <option value="ema">EMA</option>
            </select>
          </div>

          <button
            onClick={handleSend}
            disabled={isLoading || !text.trim()}
            className="btn-primary w-[44px] h-[44px] sm:w-[52px] sm:h-[52px] !p-0 flex-shrink-0 ml-auto shadow-md hover:shadow-lg active:scale-95 transition-all"
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin text-white/70" />
            ) : (
              <Send className="w-5 h-5 text-white" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default InputArea;
