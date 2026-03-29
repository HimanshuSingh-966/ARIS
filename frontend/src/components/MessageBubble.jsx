import React from 'react';
import ReactMarkdown from 'react-markdown';
import SourceCitations from './SourceCitations';
import FormCard from './FormCard';
import clsx from 'clsx';

function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={clsx("flex w-full animate-fade-up", isUser ? "justify-end" : "justify-start")}>
      {/* Standard LLM styling: user messages max 70% flex right, AI max 100% flex left */}
      <div 
        className={clsx(
          "rounded-2xl flex flex-col gap-4",
          isUser 
            ? "max-w-[85%] sm:max-w-[75%] glass-card bg-white/5 !border-white/10 px-5 py-4" 
            : "w-full px-2 py-4"
        )}
      >
        {isUser ? (
          <p className="text-white/90 text-sm sm:text-base leading-relaxed whitespace-pre-wrap">
            {message.text}
          </p>
        ) : (
          <div className="flex flex-col gap-6">
            <div className="prose-dark w-full max-w-none text-sm sm:text-base">
              <ReactMarkdown>{message.text}</ReactMarkdown>
            </div>

            {/* Render Forms exactly like Landio feature cards */}
            {message.forms && message.forms.length > 0 && (
              <div className="flex flex-col gap-3 mt-4">
                <h4 className="text-xs uppercase tracking-widest text-muted/80 font-semibold mb-1">Relevant Forms</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {message.forms.map((form, i) => (
                    <FormCard key={i} form={form} />
                  ))}
                </div>
              </div>
            )}

            {/* Render sources at the bottom as tags */}
            {message.sources && message.sources.length > 0 && (
              <div className="mt-2 border-t border-white/10 pt-4">
                <SourceCitations sources={message.sources} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default MessageBubble;
