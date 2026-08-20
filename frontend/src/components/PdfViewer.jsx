import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, MessageSquarePlus, Download } from 'lucide-react';
import ChatPanel from './ChatPanel';
import { api, documentStreamUrl } from '../lib/api';

function PdfViewer() {
  const { source, section, docId } = useParams();
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState('');
  const [docName, setDocName] = useState('');

  // Format display strings
  const formattedSource = source?.toUpperCase();
  const formattedSection = section?.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  // The route param is an md5 doc_id, so the old `docId.replace('.pdf', '')` never
  // matched anything and the breadcrumb showed a 32-character hash. /url returns
  // the real name; the hash stays as the fallback until that resolves.
  const displayName = docName || docId || 'Document';

  // The iframe points directly at the FastAPI streaming proxy — no CORS issues!
  const streamUrl = docId ? documentStreamUrl(docId) : '';

  // Presigned URL for the download button, plus the document's display name.
  useEffect(() => {
    // Clear first: without this, navigating between documents left the previous
    // one's name in the breadcrumb and its presigned URL on the download button.
    setDownloadUrl('');
    setDocName('');
    if (!docId) return;

    let active = true;
    api.get(`/documents/${encodeURIComponent(docId)}/url`)
      .then(({ data }) => {
        if (!active) return;
        if (data?.url) setDownloadUrl(data.url);
        if (data?.doc_name) setDocName(data.doc_name);
      })
      .catch(() => {});

    return () => { active = false; };
  }, [docId]);

  return (
    <div className="flex flex-col w-full h-full relative overflow-hidden bg-transparent">

      {/* Viewer Header */}
      <header className="h-16 shrink-0 border-b border-white/[0.04] bg-[#020303]/90 backdrop-blur-xl flex items-center justify-between px-6 z-20">

        <div className="flex items-center gap-4">
          <Link to={`/explore/${source}/${section}`} className="p-2 -ml-2 text-muted hover:text-white transition-colors rounded-lg hover:bg-white/5">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="h-4 w-[1px] bg-white/10 hidden sm:block"></div>

          <div className="hidden sm:flex items-center gap-2 text-xs font-semibold tracking-wide text-muted uppercase">
            <span>{formattedSource}</span>
            <span className="text-white/20">/</span>
            <span>{formattedSection}</span>
            <span className="text-white/20">/</span>
            <span className="text-white truncate max-w-[200px]" title={displayName}>{displayName}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            // Disabled until the presigned URL resolves: the click used to be a
            // silent no-op while the button still looked active.
            onClick={() => window.open(downloadUrl, '_blank', 'noopener,noreferrer')}
            disabled={!downloadUrl}
            title={downloadUrl ? 'Download PDF' : 'Preparing download…'}
            className="hidden sm:flex items-center justify-center p-2.5 rounded-lg text-muted hover:text-white hover:bg-white/5 transition-colors border border-transparent hover:border-white/10 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-muted"
          >
            <Download className="w-4 h-4" />
          </button>
          <div className="h-4 w-[1px] bg-white/10 hidden sm:block"></div>
          <button
            onClick={() => setIsChatOpen(true)}
            className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl font-medium text-white bg-white/10 hover:bg-white/15 border border-white/20 hover:border-white/30 transition-all shadow-md group"
          >
            <MessageSquarePlus className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
            <span className="text-sm">Ask AI Assistant</span>
          </button>
        </div>
      </header>

      {/* Main Layout containing PDF and optionally Chat */}
      <div className="flex-1 w-full relative overflow-hidden flex">

        {/* PDF Iframe — loads from same-origin FastAPI stream endpoint, no CORS issues */}
        {streamUrl ? (
          <div className="flex-1 w-full relative bg-white/5">
            <iframe
              src={streamUrl}
              className="w-full h-full border-0 absolute inset-0"
              title={displayName}
            />
          </div>
        ) : (
          // text-white/50 here was unreadable: bg-white/5 is near-transparent, so
          // this sits on the mint page background, not on the header's dark chrome.
          <div className="flex-1 w-full relative bg-white/5 flex items-center justify-center text-slate-700 font-medium px-4 text-center">
            No document selected.
          </div>
        )}

        {/* Global Dark Overlay when Chat is Open on Mobile */}
        {isChatOpen && (
          <div
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 sm:hidden"
            onClick={() => setIsChatOpen(false)}
          />
        )}

        {/* Slide-in Chat Panel — docId is the raw route param because it is the
            doc_metadata key the API filters on; docLabel carries the human-readable
            name so the panel never has to display the hash. */}
        <ChatPanel
          docId={docId}
          docLabel={docName}
          isOpen={isChatOpen}
          onClose={() => setIsChatOpen(false)}
        />

      </div>
    </div>
  );
}

export default PdfViewer;
