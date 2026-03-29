import React, { useState } from 'react';
import { Download, File, Loader2 } from 'lucide-react';

function FormCard({ form }) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState(null);

  const handleDownload = async () => {
    try {
      setIsDownloading(true);
      setError(null);
      
      const res = await fetch(`/api/v1/forms/${form.id}/download`);
      if (!res.ok) throw new Error('Form download failed');
      
      const data = await res.json();
      
      // Trigger download via invisible link
      const a = document.createElement('a');
      a.href = data.download_url;
      a.target = '_blank';
      a.download = data.form_name || form.form_number;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      
    } catch (err) {
      console.error(err);
      setError('Download failed');
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="glass-card p-4 flex flex-col gap-3 group transition-all hover:bg-white/[0.08] hover:border-white/20">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 text-white/90 font-medium">
          <div className="w-8 h-8 rounded-lg bg-black/50 border border-white/10 flex items-center justify-center">
            <File className="w-4 h-4 text-muted" />
          </div>
          <div>
            <div className="text-sm font-semibold">{form.form_number}</div>
            <div className="text-xs text-muted font-normal uppercase tracking-wider">{form.country} • {form.source}</div>
          </div>
        </div>
      </div>
      
      <div className="text-xs text-muted line-clamp-2 min-h-[32px]">
        {form.form_name || form.description || 'Regulatory application form.'}
      </div>
      
      <button 
        onClick={handleDownload}
        disabled={isDownloading}
        className="mt-2 w-full py-2 px-4 rounded-lg bg-white text-black font-semibold text-sm hover:bg-gray-200 transition-colors flex items-center justify-center gap-2 disabled:opacity-70"
      >
        {isDownloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
        {isDownloading ? 'Fetching...' : 'Download Form'}
      </button>

      {error && <span className="text-[10px] text-red-400 text-center">{error}</span>}
    </div>
  );
}

export default FormCard;
