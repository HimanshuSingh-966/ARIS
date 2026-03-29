import React, { useState, useEffect } from 'react';
import { ArrowLeft, Search, FileText, Download, ChevronRight } from 'lucide-react';
import { useParams, Link } from 'react-router-dom';

function AgencyDetail() {
  const { source } = useParams();
  const [sections, setSections] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  // Formatting strings
  const formatName = (str) => {
    if (!str) return '';
    return str.replace('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  const agencyName = source ? (['fda', 'ema', 'cdsco'].includes(source.toLowerCase()) ? source.toUpperCase() : formatName(source)) : '';

  useEffect(() => {
    const fetchSections = async () => {
      setIsLoading(true);
      try {
        const res = await fetch(`/api/v1/sources/${source}/sections`);
        if (res.ok) {
          const data = await res.json();
          setSections(data.sections || []);
        }
      } catch (err) {
        console.error("Error fetching sections:", err);
      } finally {
        setIsLoading(false);
      }
    };
    if (source) fetchSections();
  }, [source]);

  return (
    <div className="flex-1 w-full h-full overflow-y-auto px-6 py-8 hide-scrollbar">
      <div className="max-w-4xl mx-auto animate-fade-right">
        
        <Link 
          to="/explore"
          className="inline-flex items-center text-sm font-semibold tracking-widest uppercase text-[#0f766e] hover:text-[#0f172a] mb-8 transition-colors group"
        >
          <ArrowLeft className="w-4 h-4 mr-2 group-hover:-translate-x-1 transition-transform" />
          Back to Dashboard
        </Link>

        <header className="mb-10">
          <h1 className="text-4xl font-bold tracking-tight text-[#0f172a] mb-2">
            {agencyName} <span className="font-serif italic text-[#0f766e] font-medium">Directory</span>
          </h1>
          <p className="text-[#334155] font-medium">Browse official documentation and forms.</p>
        </header>

        <div className="relative mb-8">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#0f766e]" />
          <input 
            type="text" 
            placeholder={`Search ${agencyName} documents...`} 
            className="w-full bg-white/60 border border-[#0f766e]/20 rounded-2xl py-4 pl-12 pr-4 text-[#0f172a] placeholder-[#0f766e]/60 focus:outline-none focus:border-[#0f766e]/50 transition-colors shadow-sm"
          />
        </div>

        <div className="space-y-4">
          <h3 className="text-xs font-bold text-[#0f766e] uppercase tracking-widest pl-2 mb-4">Document Categories</h3>
          
          {isLoading ? (
            <div className="py-20 flex justify-center items-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#0f766e]"></div>
            </div>
          ) : sections.length === 0 ? (
            <div className="py-10 text-center text-[#334155] font-medium border border-dashed border-[#0f766e]/20 rounded-2xl bg-white/40">
              No categories found for this agency.
            </div>
          ) : sections.map((sec, idx) => (
            <Link 
              key={idx} 
              to={`/explore/${source}/${sec}`}
              className="glass-card flex items-center justify-between p-5 hover:bg-white/80 transition-colors cursor-pointer group border-[#0f766e]/10 shadow-sm hover:shadow-md"
            >
              <div className="flex items-center">
                <div className="w-10 h-10 rounded-xl bg-white/80 flex items-center justify-center mr-4 border border-[#0f766e]/20">
                  <FileText className="w-5 h-5 text-[#0f766e] group-hover:text-[#0f172a] transition-colors" />
                </div>
                <div>
                  <h4 className="text-lg font-bold text-[#0f172a] group-hover:text-[#0f766e] transition-colors">{formatName(sec)}</h4>
                  <p className="text-sm font-medium text-[#334155]">Explore documents</p>
                </div>
              </div>
              <ChevronRight className="w-5 h-5 text-[#0f766e]/50 group-hover:text-[#0f766e] group-hover:translate-x-1 transition-all" />
            </Link>
          ))}
        </div>

      </div>
    </div>
  );
}

export default AgencyDetail;
