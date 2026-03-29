import React from 'react';
import { Database, FileText } from 'lucide-react';

function SourceCitations({ sources }) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 text-xs">
      <span className="flex items-center text-muted/60 mr-2 uppercase tracking-widest font-semibold text-[10px]">
        Sources ({(sources.length)})
      </span>
      {sources.map((src, idx) => (
        <a 
          key={idx}
          href={src.b2_key ? `https://f004.backblazeb2.com/file/pharma-rag-docs/${src.b2_key}` : '#'}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-white/10 bg-white/5 hover:bg-white/10 transition-colors text-muted hover:text-white"
          title={`Similarity Score: ${(src.similarity * 100).toFixed(1)}%`}
        >
          <Database className="w-3 h-3 opacity-70" />
          <span className="max-w-[150px] truncate">{src.doc_name}</span>
          <span className="opacity-50 mx-1">•</span>
          <span className="uppercase text-[10px] font-bold tracking-wider">{src.source}</span>
        </a>
      ))}
    </div>
  );
}

export default SourceCitations;
