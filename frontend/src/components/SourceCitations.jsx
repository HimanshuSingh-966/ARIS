import { Database } from 'lucide-react';
import { documentStreamUrl } from '../lib/api';

function SourceCitations({ sources }) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <span className="flex items-center text-muted/60 mr-2 uppercase tracking-widest font-semibold text-[10px]">
        Sources ({sources.length})
      </span>
      {sources.map((src, idx) => {
        // Was a hardcoded https://f004.backblazeb2.com/file/pharma-rag-docs/<key>,
        // which 403s: the bucket is private, which is why the rest of the app
        // presigns. Route through the API's streaming proxy instead — and render a
        // plain span, not a dead href="#", when there is no doc_id to link to.
        const href = src.doc_id ? documentStreamUrl(src.doc_id) : null;
        const className = "flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 transition-colors text-slate-600";
        const title = `Similarity Score: ${((src.similarity ?? 0) * 100).toFixed(1)}%`;

        const body = (
          <>
            <Database className="w-3 h-3 text-slate-400" />
            <span className="max-w-[150px] truncate">{src.doc_name}</span>
            <span className="opacity-50 mx-1">•</span>
            <span className="uppercase text-[10px] font-bold tracking-wider">{src.source}</span>
          </>
        );

        return href ? (
          <a
            key={src.doc_id || idx}
            href={href}
            target="_blank"
            rel="noreferrer"
            className={`${className} hover:bg-slate-100 hover:text-[#0f766e]`}
            title={title}
          >
            {body}
          </a>
        ) : (
          <span key={idx} className={className} title={title}>
            {body}
          </span>
        );
      })}
    </div>
  );
}

export default SourceCitations;
