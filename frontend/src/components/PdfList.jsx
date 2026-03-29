import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Search, Filter, FileText, Calendar, HardDrive, ArrowRight } from 'lucide-react';


function PdfList() {
  const { source, section } = useParams();
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('newest');

  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchDocuments = async () => {
      setIsLoading(true);
      try {
        const res = await fetch(`/api/v1/sources/${source}/sections/${section}/documents?sort=${sortBy}`);
        if (res.ok) {
          const data = await res.json();
          setDocuments(data.documents || []);
        } else {
          console.error('Failed to fetch documents');
        }
      } catch (err) {
        console.error('Error fetching documents:', err);
      } finally {
        setIsLoading(false);
      }
    };
    if (source && section) {
      fetchDocuments();
    }
  }, [source, section, sortBy]);

  // Utility to format source/section nicely
  const formatName = (str) => {
    if (!str) return '';
    if (str.toLowerCase() === 'fda' || str.toLowerCase() === 'ema' || str.toLowerCase() === 'cdsco') return str.toUpperCase();
    return str.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  };

  return (
    <div className="flex-1 w-full h-full overflow-y-auto px-6 py-8 hide-scrollbar">
      <div className="max-w-6xl mx-auto animate-fade-up">

        {/* Breadcrumb & Navigation */}
        <div className="flex items-center space-x-2 text-sm font-bold tracking-widest uppercase text-[#0f766e] mb-8">
          <Link to={`/explore/${source}`} className="hover:text-[#0f172a] transition-colors flex items-center group">
            <ArrowLeft className="w-4 h-4 mr-2 group-hover:-translate-x-1 transition-transform" />
            {formatName(source)}
          </Link>
          <span className="text-[#0f766e]/30">/</span>
          <span className="text-[#0f766e]/80">{formatName(section)}</span>
        </div>

        <header className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-[#0f172a] mb-2">
            {formatName(section)} <span className="font-serif italic text-[#0f766e] font-medium">Documents</span>
          </h1>
          <p className="text-[#334155] font-medium">Explore official releases and guidelines.</p>
        </header>

        {/* Search and Filter Controls */}
        <div className="flex flex-col sm:flex-row gap-4 mb-8">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#0f766e]" />
            <input 
              type="text" 
              placeholder={`Filter ${isLoading ? '...' : documents.length} documents...`} 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-white/60 border border-[#0f766e]/20 rounded-xl py-3 pl-12 pr-4 text-[#0f172a] placeholder-[#0f766e]/60 focus:outline-none focus:border-[#0f766e]/50 transition-colors shadow-sm"
            />
          </div>
          <div className="relative">
            <Filter className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#0f766e] pointer-events-none" />
            <select 
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="appearance-none bg-white/60 border border-[#0f766e]/20 rounded-xl py-3 pl-10 pr-10 text-[#0f172a] font-medium focus:outline-none focus:border-[#0f766e]/50 transition-colors hover:bg-white/80 cursor-pointer min-w-[160px] shadow-sm"
            >
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
              <option value="az">Name A-Z</option>
              <option value="za">Name Z-A</option>
            </select>
            <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none border-l-4 border-r-4 border-t-4 border-transparent border-t-[#0f766e] w-0 h-0"></div>
          </div>
        </div>

        {/* PDF Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {isLoading ? (
            <div className="col-span-full py-20 flex justify-center items-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#0f766e]"></div>
            </div>
          ) : documents.filter(p => (p.doc_name || '').toLowerCase().includes(searchQuery.toLowerCase())).length === 0 ? (
            <div className="col-span-full py-20 text-center text-[#334155] font-medium border border-dashed border-[#0f766e]/20 rounded-2xl bg-white/40">
              No documents matched your search criteria.
            </div>
          ) : documents.filter(p => (p.doc_name || '').toLowerCase().includes(searchQuery.toLowerCase())).map((doc) => (
            <Link 
              key={doc.doc_id}
              to={`/explore/${source}/${section}/${doc.doc_id}`}
              className="glass-card flex flex-col sm:flex-row sm:items-center justify-between p-5 hover:bg-white/80 transition-colors border-[#0f766e]/10 group shadow-sm hover:shadow-md"
            >
              <div className="flex items-start sm:items-center mb-4 sm:mb-0">
                <div className="w-12 h-12 rounded-xl bg-red-100 flex items-center justify-center mr-4 border border-red-200 flex-shrink-0 group-hover:bg-red-200 transition-colors">
                  <FileText className="w-6 h-6 text-red-600" />
                </div>
                <div>
                  <h4 className="text-base font-bold text-[#0f172a] group-hover:text-[#0f766e] transition-colors leading-snug line-clamp-2 md:line-clamp-1 mb-1.5">{doc.doc_name}</h4>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-[#334155] font-semibold tracking-wide">
                    <span className="flex items-center"><Calendar className="w-3.5 h-3.5 mr-1 pt-[1px]" /> {new Date(doc.created_at || Date.now()).toLocaleDateString()}</span>
                    <span className="w-1 h-1 rounded-full bg-[#0f766e]/30"></span>
                    <span className="flex items-center"><HardDrive className="w-3.5 h-3.5 mr-1 pt-[1px]" /> {doc.file_size ? `${Math.round(doc.file_size)} KB` : 'Unknown Size'}</span>
                    <span className="w-1 h-1 rounded-full bg-[#0f766e]/30"></span>
                    <span className="px-1.5 py-0.5 rounded bg-white border border-[#0f766e]/20 text-[10px] uppercase font-bold text-[#0f766e]">{formatName(source)}</span>
                  </div>
                </div>
              </div>
              
              <div className="flex-shrink-0 w-full sm:w-auto mt-2 sm:mt-0">
                <div className="flex items-center justify-center sm:justify-start px-4 py-2 rounded-lg bg-[#0f766e]/10 border border-[#0f766e]/20 text-sm font-bold text-[#0f766e] group-hover:bg-[#0f766e] group-hover:text-white transition-all w-full sm:w-auto text-center shadow-sm">
                  View Document
                  <ArrowRight className="w-4 h-4 ml-2 opacity-70 group-hover:translate-x-1 group-hover:opacity-100 transition-all" />
                </div>
              </div>
            </Link>
          ))}
        </div>

      </div>
    </div>
  );
}

export default PdfList;
