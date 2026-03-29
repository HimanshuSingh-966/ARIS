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
      <div className="glass-card p-2 sm:p-3 flex flex-col sm:flex-row gap-3 items-end sm:items-center">
        
        {/* Input field */}
        <div className="flex-1 w-full relative">
          <textarea
            className="w-full bg-transparent text-white placeholder-muted focus:outline-none resize-none pt-2 sm:pt-3 px-3 min-h-[44px] sm:min-h-[52px] max-h-32 text-sm sm:text-base leading-relaxed"
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
        <div className="flex w-full sm:w-auto justify-between sm:justify-end items-center gap-2 pl-3 sm:pl-0 sm:border-l border-white/10 sm:ml-2">
          
          {/* Filters (Landio style subtle pills) */}
          <div className="flex flex-col gap-1 items-start sm:items-end w-full sm:w-auto pr-2">
            <select 
              value={country} 
              onChange={e => setCountry(e.target.value)}
              className="appearance-none bg-transparent hover:bg-white/5 text-muted hover:text-white rounded px-2 py-1 text-xs cursor-pointer focus:outline-none transition-colors"
            >
              <option value="" className="bg-surface">Any Country</option>
              <option value="India" className="bg-surface">India</option>
              <option value="USA" className="bg-surface">USA</option>
              <option value="Europe" className="bg-surface">Europe</option>
            </select>
            
            <select 
              value={source} 
              onChange={e => setSource(e.target.value)}
              className="appearance-none bg-transparent hover:bg-white/5 text-muted hover:text-white rounded px-2 py-1 text-xs cursor-pointer focus:outline-none transition-colors"
            >
              <option value="" className="bg-surface">Any Source</option>
              <option value="cdsco" className="bg-surface">CDSCO</option>
              <option value="fda" className="bg-surface">FDA</option>
              <option value="ema" className="bg-surface">EMA</option>
            </select>
          </div>

          <button
            onClick={handleSend}
            disabled={isLoading || !text.trim()}
            className="btn-primary w-[44px] h-[44px] sm:w-[52px] sm:h-[52px] !p-0 flex-shrink-0 ml-auto"
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin text-white/70" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>
      
      {/* Glow effect at the bottom */}
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[80%] h-4 bg-white/5 blur-xl -z-10 rounded-[100%]" />
    </div>
  );
}

export default InputArea;
