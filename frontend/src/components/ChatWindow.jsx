import React from 'react';
import MessageBubble from './MessageBubble';
import { Microscope } from 'lucide-react';

function ChatWindow({ messages, isLoading, messagesEndRef }) {
  return (
    <div className="flex-1 overflow-y-auto w-full pt-8 pb-4 space-y-6 scroll-smooth pr-2">
      
      {messages.length === 0 && (
        <div className="flex flex-col items-center justify-center h-full text-center space-y-4 opacity-50 animate-fade-up">
          <div className="w-12 h-12 rounded-full border border-white/10 flex items-center justify-center mb-2">
            <Microscope className="w-5 h-5 text-muted" />
          </div>
          <p className="text-muted text-sm max-w-sm">
            Start a new regulatory search. Type a drug name, active ingredient, or regulatory question below.
          </p>
        </div>
      )}

      {messages.map((msg, idx) => (
        <MessageBubble key={msg.id || idx} message={msg} />
      ))}

      {isLoading && (
        <div className="flex justify-start w-full opacity-60">
          <div className="flex gap-2 items-center p-4">
            <div className="w-2 h-2 rounded-full bg-white/40 animate-pulse"></div>
            <div className="w-2 h-2 rounded-full bg-white/40 animate-pulse delay-150"></div>
            <div className="w-2 h-2 rounded-full bg-white/40 animate-pulse delay-300"></div>
          </div>
        </div>
      )}
      
      {/* Invisible element to scroll to */}
      <div ref={messagesEndRef} className="h-4" />
    </div>
  );
}

export default ChatWindow;