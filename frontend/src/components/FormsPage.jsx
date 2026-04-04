import React, { useState, useEffect } from 'react';
import { Search, Filter, Download, FileText, Loader2, AlertCircle, X } from 'lucide-react';
import FormCard from './FormCard';
import axios from 'axios';

const CATEGORIES = [
  'All', 'Manufacturing', 'Import / Export', 'Clinical Trial', 
  'Wholesale / Retail', 'Testing / Analysis', 'Blood Bank / Biologics',
  'Traditional Medicine', 'Cosmetics', 'Registration'
];

function FormsPage() {
  const [query, setQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [forms, setForms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    fetchForms();
  }, [selectedCategory]);

  const fetchForms = async (searchQuery = '') => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (searchQuery) params.q = searchQuery;
      if (selectedCategory !== 'All') params.type = selectedCategory;
      
      const response = await axios.get('/api/v1/forms', { params });
      setForms(response.data.forms || []);
    } catch (err) {
      console.error('Fetch error:', err);
      setError('Unable to load forms. Please try again.');
    } finally {
      setLoading(false);
      setIsSearching(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    setIsSearching(true);
    fetchForms(query);
  };

  const handleDownload = async (formId) => {
    try {
      const res = await axios.get(`/api/v1/forms/${formId}/download`);
      window.open(res.data.download_url, '_blank');
    } catch (err) {
      alert('Failed to generate download link. Please try later.');
    }
  };

  return (
    <div className="flex-1 w-full h-full overflow-y-auto bg-[#f8fafc] hide-scrollbar">
      {/* Search Header */}
      <div className="bg-[#0f766e] py-16 px-6 relative overflow-hidden">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-0 left-0 w-96 h-96 bg-white rounded-full blur-[100px] -translate-x-1/2 -translate-y-1/2" />
          <div className="absolute bottom-0 right-0 w-96 h-96 bg-white rounded-full blur-[100px] translate-x-1/2 translate-y-1/2" />
        </div>
        
        <div className="max-w-4xl mx-auto relative z-10 text-center">
          <h1 className="text-fluid-hero font-extrabold text-white mb-4 tracking-tight">
            Regulatory Forms Intelligence
          </h1>
          <p className="text-fluid-subhero text-[#ccfbf1] font-medium mb-10 opacity-90 max-w-2xl mx-auto leading-tight">
            Search 80+ official forms across India's Drug Rules with natural language intent.
          </p>

          <form onSubmit={handleSearch} className="relative group max-w-2xl mx-auto">
            <div className="absolute inset-y-0 left-5 flex items-center pointer-events-none">
              <Search className="w-6 h-6 text-[#94a3b8] group-focus-within:text-[#0f766e] transition-colors" />
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Finding a blood bank licence...?"
              className="w-full pl-14 pr-32 py-5 bg-white rounded-2xl shadow-xl shadow-[#0f766e]/20 text-[#1e293b] text-base md:text-lg font-medium border-0 focus:ring-4 focus:ring-[#5eead4]/30 transition-all placeholder:text-[#94a3b8]"
            />
            <button 
              type="submit"
              disabled={isSearching}
              className="absolute right-3 top-2.5 bottom-2.5 px-4 md:px-8 bg-[#0f766e] text-white font-bold rounded-xl hover:bg-[#115e59] transition-all shadow-md active:scale-95 disabled:opacity-70 flex items-center justify-center gap-2 min-w-[54px] md:min-w-0"
            >
              {isSearching ? <Loader2 className="w-5 h-5 animate-spin" /> : 
                <>
                  <Search className="w-5 h-5 md:hidden" />
                  <span className="hidden md:block">Search</span>
                </>
              }
            </button>
          </form>
        </div>
      </div>

      {/* Filters & Results */}
      <div className="max-w-[1400px] mx-auto px-4 md:px-8 -mt-8 relative z-20 pb-20">
        {/* Category Scroll */}
        <div className="bg-white p-2 rounded-2xl shadow-lg border border-slate-100 mb-10">
          <div className="flex items-center gap-4 overflow-x-auto pb-1 hide-scrollbar mask-fade-right">
            <div className="flex items-center px-4 border-r border-slate-100 text-slate-400">
              <Filter className="w-4 h-4 mr-2" />
              <span className="text-[10px] font-bold uppercase tracking-widest whitespace-nowrap">Filter</span>
            </div>
            {CATEGORIES.map(cat => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-6 py-3 rounded-xl text-sm font-bold whitespace-nowrap transition-all ${
                  selectedCategory === cat 
                  ? 'bg-[#0f766e] text-white shadow-md scale-105' 
                  : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Results Info */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 px-2">
          <div>
            <h2 className="text-xl md:text-2xl font-extrabold text-[#0f172a] flex items-center">
              {selectedCategory === 'All' ? 'Official Forms' : selectedCategory}
              <span className="ml-3 text-[10px] font-bold text-teal-700 bg-teal-50 border border-teal-100 px-3 py-1 rounded-full uppercase tracking-tighter">
                {forms.length} Results
              </span>
            </h2>
          </div>
          {query && (
            <button 
              onClick={() => { setQuery(''); fetchForms(''); }}
              className="text-sm font-bold text-[#0f766e] flex items-center justify-center hover:underline bg-white px-4 py-2 rounded-lg border border-slate-100 md:border-0 md:bg-transparent"
            >
              Clear Search <X className="ml-1 w-4 h-4" />
            </button>
          )}
        </div>

        {/* Grid */}
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} className="bg-white rounded-2xl h-80 animate-pulse border border-slate-100 shadow-sm" />
            ))}
          </div>
        ) : error ? (
          <div className="bg-red-50 border border-red-100 rounded-2xl p-12 text-center shadow-inner">
            <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
            <p className="text-red-700 font-bold text-lg">{error}</p>
            <button onClick={() => fetchForms(query)} className="mt-4 text-[#0f766e] font-bold hover:underline">
              Retry Selection
            </button>
          </div>
        ) : forms.length === 0 ? (
          <div className="bg-slate-50 rounded-3xl p-20 text-center border-2 border-dashed border-slate-200">
            <FileText className="w-16 h-16 text-slate-300 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-slate-900 mb-2">No matching forms found</h3>
            <p className="text-slate-500 max-w-sm mx-auto">
              We couldn't find any forms matching your current search or filter. Try using broader keywords like "licence" or "manufacturing".
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 animate-fade-in">
            {forms.map(form => (
              <FormCard 
                key={`${form.id}-${form.form_number}`} 
                form={form} 
                onDownload={handleDownload} 
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default FormsPage;
