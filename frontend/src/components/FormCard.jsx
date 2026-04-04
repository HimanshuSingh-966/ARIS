import React from 'react';
import { Download, FileText, ShieldCheck } from 'lucide-react';

function FormCard({ form, onDownload }) {
  return (
    <div className="glass-card flex flex-col p-6 hover:bg-white/80 transition-all border-[#0f766e]/10 group shadow-sm hover:shadow-lg rounded-2xl relative overflow-hidden">
      {/* Decorative background accent */}
      <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-[#0f766e]/5 to-transparent -mr-8 -mt-8 rounded-full blur-2xl group-hover:bg-[#0f766e]/10 transition-colors" />
      
      <div className="flex items-start justify-between mb-6 relative z-10">
        <div className="flex items-center">
          <div className="w-12 h-12 rounded-xl bg-[#0f766e]/10 flex items-center justify-center mr-4 border border-[#0f766e]/20 group-hover:scale-110 transition-transform">
            <FileText className="w-6 h-6 text-[#0f766e]" />
          </div>
          <div>
            <h3 className="text-lg md:text-xl font-bold tracking-tight text-[#0f172a] group-hover:text-[#0f766e] transition-colors line-clamp-1">
              {form.form_number || 'FORM'}
            </h3>
            <div className="flex items-center gap-2 mt-1">
              <span className="px-2 py-0.5 rounded border border-[#0f766e]/20 bg-white/80 text-[9px] md:text-[10px] font-bold uppercase tracking-wider text-[#0f766e]">
                {form.country}
              </span>
              {form.source_pdf_year && (
                <span className="px-2 py-0.5 rounded border border-amber-200 bg-amber-50 text-[9px] md:text-[10px] font-bold uppercase tracking-wider text-amber-700">
                  {form.source_pdf_year} v
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="mb-4 md:mb-6 flex-1 min-h-[4.5rem]">
        <p className="text-[#334155] font-bold text-xs md:text-sm leading-relaxed line-clamp-3 mb-2" title={form.form_name}>
          {form.form_name}
        </p>
        {form.description && (
          <div className="flex items-center gap-1.5 text-[#0f766e] font-semibold text-[10px] md:text-[11px] bg-[#0f766e]/5 px-2 py-1 rounded w-fit italic">
            <ShieldCheck className="w-3.5 h-3.5" />
            {form.description}
          </div>
        )}
      </div>

      <div className="mt-auto pt-4 border-t border-[#0f766e]/10">
        <button 
          onClick={() => onDownload(form.id)}
          className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl bg-white border border-[#0f766e]/20 text-sm font-bold text-[#0f766e] hover:bg-[#0f766e] hover:text-white hover:border-[#0f766e] transition-all shadow-sm group-hover:shadow-md active:scale-[0.98]"
        >
          <Download className="w-4 h-4 opacity-70 group-hover:-translate-y-0.5 transition-transform" />
          Download PDF
        </button>
      </div>
    </div>
  );
}

export default FormCard;
