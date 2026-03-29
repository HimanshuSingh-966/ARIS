import React, { useState, useEffect } from 'react';
import { Search, Filter, Download, MessageSquarePlus, FileText } from 'lucide-react';

function FormsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCountry, setFilterCountry] = useState('All');
  
  const [forms, setForms] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchForms = async () => {
      setIsLoading(true);
      try {
        const res = await fetch('/api/v1/forms');
        if (res.ok) {
          const data = await res.json();
          setForms(data.forms || []);
        } else {
          console.error('Failed to fetch forms');
        }
      } catch (err) {
        console.error('Error fetching forms:', err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchForms();
  }, []);

  const handleDownload = async (formId) => {
    try {
      const res = await fetch(`/api/v1/forms/${formId}/download`);
      if (res.ok) {
        const data = await res.json();
        window.open(data.download_url, '_blank');
      } else {
        alert('Failed to generate download link.');
      }
    } catch (err) {
      console.error('Download error:', err);
    }
  };

  const filteredForms = forms.filter(f => {
    if (filterCountry !== 'All' && f.country !== filterCountry) return false;
    if (searchQuery && !(f.form_name || '').toLowerCase().includes(searchQuery.toLowerCase()) && !(f.form_number || '').toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="flex-1 w-full h-full overflow-y-auto px-6 py-12 hide-scrollbar">
      <div className="max-w-6xl mx-auto animate-fade-right">
        
        {/* Header Section */}
        <header className="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <div className="px-3 py-1 rounded-full border border-[#0f766e]/20 bg-[#0f766e]/5 text-xs font-semibold tracking-widest uppercase text-[#0f766e] mb-6 backdrop-blur-sm inline-block">
              Global Directory
            </div>
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-[#0f172a] mb-4">
              Regulatory <span className="font-serif italic text-[#0f766e] font-medium">Forms</span>
            </h1>
            <p className="text-[#334155] font-medium text-lg max-w-2xl">
              Browse, filter, and instantly download official submission forms across major regulatory agencies.
            </p>
          </div>
          
          <button className="flex items-center justify-center gap-3 px-6 py-4 rounded-xl font-medium text-[#0f766e] bg-white/60 hover:bg-white border border-[#0f766e]/20 transition-all shadow-sm hover:shadow-md group whitespace-nowrap">
            <MessageSquarePlus className="w-5 h-5 text-[#0f766e] group-hover:scale-110 transition-transform" />
            <div className="text-left leading-tight">
              <span className="block text-xs uppercase tracking-wider text-[#334155] font-bold">Need Help?</span>
              <span className="font-bold tracking-wide text-[#0f172a]">Ask AI Assistant</span>
            </div>
          </button>
        </header>

        {/* Global Search and Filters */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-4 mb-8">
          <div className="relative md:col-span-6">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#0f766e] pointer-events-none" />
            <input 
              type="text" 
              placeholder="Search by form number or name..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-white/60 border border-[#0f766e]/20 rounded-xl py-3 pl-12 pr-4 text-[#0f172a] placeholder-[#0f766e]/60 focus:outline-none focus:border-[#0f766e]/50 transition-colors shadow-sm"
            />
          </div>
          
          <div className="relative md:col-span-6">
            <Filter className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#0f766e] pointer-events-none" />
            <select 
              value={filterCountry}
              onChange={(e) => setFilterCountry(e.target.value)}
              className="w-full appearance-none bg-white/60 border border-[#0f766e]/20 rounded-xl py-3 pl-10 pr-10 text-[#0f172a] font-medium focus:outline-none focus:border-[#0f766e]/50 transition-colors hover:bg-white/80 cursor-pointer shadow-sm"
            >
              <option value="All">All Countries</option>
              <option value="India">India</option>
              <option value="USA">USA</option>
              <option value="Europe">Europe</option>
            </select>
            <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none border-l-4 border-r-4 border-t-4 border-transparent border-t-[#0f766e] w-0 h-0"></div>
          </div>
        </div>

        {/* Form Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {isLoading ? (
            <div className="col-span-full py-20 flex justify-center items-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#0f766e]"></div>
            </div>
          ) : filteredForms.map((form) => (
            <div key={form.id} className="glass-card flex flex-col p-6 hover:bg-white/80 transition-colors border-[#0f766e]/10 group shadow-sm hover:shadow-md">
              <div className="flex items-start justify-between mb-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center mr-4 border border-indigo-200">
                    <FileText className="w-6 h-6 text-indigo-600" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold tracking-tight text-[#0f172a]">{form.form_number || 'FORM'}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="px-2 py-0.5 rounded border border-[#0f766e]/20 bg-white/80 text-[10px] font-bold uppercase tracking-wider text-[#0f766e]">
                        {form.country || form.source}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <p className="text-[#334155] font-semibold text-sm leading-relaxed mb-auto line-clamp-2" title={form.form_name}>
                {form.form_name}
              </p>

              <div className="mt-8 pt-4 border-t border-[#0f766e]/10">
                <button 
                  onClick={() => handleDownload(form.id)}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-[#0f766e]/10 hover:bg-[#0f766e] border border-[#0f766e]/20 text-sm font-bold text-[#0f766e] hover:text-white transition-all shadow-sm group-hover:bg-[#0f766e] group-hover:text-white"
                >
                  <Download className="w-4 h-4 opacity-70 group-hover:-translate-y-0.5 transition-all" />
                  Download Form PDF
                </button>
              </div>
            </div>
          ))}
        </div>

        {!isLoading && filteredForms.length === 0 && (
          <div className="py-20 flex flex-col items-center justify-center text-center">
            <div className="w-16 h-16 rounded-full bg-white/60 flex items-center justify-center mb-4 border border-[#0f766e]/10 shadow-sm">
              <Search className="w-6 h-6 text-[#0f766e]/50" />
            </div>
            <h3 className="text-lg font-bold text-[#0f172a] mb-2">No forms found</h3>
            <p className="text-[#334155] font-medium max-w-sm">No forms strictly matched your current search and filter criteria.</p>
          </div>
        )}

      </div>
    </div>
  );
}

export default FormsPage;
