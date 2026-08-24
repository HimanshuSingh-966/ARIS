import ReactMarkdown from 'react-markdown';
import SourceCitations from './SourceCitations';
import FormCard from './FormCard';
import clsx from 'clsx';
import { downloadForm } from '../lib/api';

function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  // "Give me the form" is one of the flows this app exists for, and the cards
  // attached to an answer were rendered without a download handler — so clicking
  // one threw instead of downloading. Same helper FormsPage uses.
  const handleDownload = async (formId) => {
    try {
      await downloadForm(formId);
    } catch (err) {
      console.error('Download error:', err);
      alert('Failed to generate download link. Please try later.');
    }
  };

  return (
    <div className={clsx("flex w-full animate-fade-up", isUser ? "justify-end" : "justify-start")}>
      <div 
        className={clsx(
          "rounded-2xl flex flex-col gap-4",
          isUser 
            ? "max-w-[85%] sm:max-w-[75%] glass-card bg-white/20 border-[#0f766e]/20 px-5 py-4 shadow-sm" 
            : "w-full px-2 py-4"
        )}
      >
        {isUser ? (
          <p className="text-[#0f172a] text-sm sm:text-base font-medium leading-relaxed whitespace-pre-wrap">
            {message.content}
          </p>
        ) : (
          <div className="flex flex-col gap-6">
            <div className="prose-light w-full max-w-none text-sm sm:text-base">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>

            {/* Relevant Forms */}
            {message.forms && message.forms.length > 0 && (
              <div className="flex flex-col gap-3 mt-4">
                <h4 className="text-[10px] uppercase tracking-[0.2em] text-[#0f766e] font-bold mb-1 opacity-80">Relevant Forms</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {message.forms.map((form, i) => (
                    <FormCard
                      key={form.id ?? i}
                      form={form}
                      onDownload={handleDownload}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Sources */}
            {message.sources && message.sources.length > 0 && (
              <div className="mt-2 border-t border-[#0f766e]/10 pt-4">
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
