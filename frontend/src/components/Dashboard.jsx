import { useState, useEffect } from 'react';
import { ArrowRight, Globe, FileText, Database } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';

// Presentation only. The agency names used to live here too, as a third copy
// alongside api/routes/explore.SOURCES and pipeline/ingestor.COUNTRY_MAP; they now
// come from GET /sources so adding an agency is a backend-only change. Anything not
// listed here still renders, with the neutral fallback below.
const PRESENTATION = {
  cdsco: { color: 'from-orange-500/20 to-transparent', borderColor: 'hover:border-orange-500/50', Icon: FileText, iconClass: 'text-orange-400' },
  fda:   { color: 'from-blue-500/20 to-transparent',   borderColor: 'hover:border-blue-500/50',   Icon: Globe,    iconClass: 'text-blue-400' },
  ema:   { color: 'from-yellow-500/20 to-transparent', borderColor: 'hover:border-yellow-500/50', Icon: Database, iconClass: 'text-yellow-400' },
};

const FALLBACK_PRESENTATION = {
  color: 'from-teal-500/20 to-transparent',
  borderColor: 'hover:border-[#0f766e]/50',
  Icon: Database,
  iconClass: 'text-[#0f766e]',
};

function Dashboard() {
  const [agencies, setAgencies] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.get('/sources')
      .then(({ data }) => {
        if (!active) return;
        setAgencies(data.sources || []);
      })
      .catch(err => {
        if (!active) return;
        console.error('Error fetching sources:', err);
        setError('Could not load agencies. Please try again.');
      })
      .finally(() => { if (active) setIsLoading(false); });

    return () => { active = false; };
  }, []);

  return (
    <div className="flex-1 w-full h-full overflow-y-auto px-6 py-12 hide-scrollbar">
      <div className="max-w-5xl mx-auto animate-fade-up">

        <header className="mb-12">
          <div className="px-3 py-1 rounded-full border border-[#0f766e]/20 bg-[#0f766e]/5 text-xs font-semibold tracking-widest uppercase text-[#0f766e] mb-6 backdrop-blur-sm inline-block">
            Global Hub
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-[#0f172a] mb-4">
            Regulatory Intelligence <br />
            <span className="font-serif italic text-[#0f766e] font-medium">Agencies Overview</span>
          </h1>
          <p className="text-[#334155] font-medium text-lg max-w-2xl">
            Select a regulatory agency below to instantly browse their official guidelines, regulations, and downloadable forms.
          </p>
        </header>

        {error && (
          <div className="mb-6 py-10 text-center text-red-700 font-medium border border-dashed border-red-300 rounded-2xl bg-red-50/60">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {isLoading
            ? // Same card footprint as the real thing, so the grid doesn't reflow
              // once the names arrive.
              [0, 1, 2].map(i => (
                <div key={i} className="glass-card border border-[#0f766e]/10 p-8 h-[320px] animate-pulse">
                  <div className="w-16 h-16 rounded-2xl bg-white/60" />
                </div>
              ))
            : agencies.map(agency => {
                const { color, borderColor, Icon, iconClass } = PRESENTATION[agency.id] || FALLBACK_PRESENTATION;
                return (
                  <Link
                    key={agency.id}
                    to={`/explore/${agency.id}`}
                    className={`glass-card relative overflow-hidden group cursor-pointer border border-[#0f766e]/10 transition-all duration-300 ${borderColor} hover:-translate-y-1 hover:shadow-2xl hover:shadow-[#0f766e]/20 p-8 flex flex-col items-start h-[320px]`}
                  >
                    {/* Background Glow */}
                    <div className={`absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl ${color} blur-[80px] opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-full pointer-events-none -mr-10 -mt-10`} />

                    <div className="w-16 h-16 rounded-2xl bg-white/60 border border-[#0f766e]/10 flex items-center justify-center mb-auto shadow-sm">
                      <Icon className={`w-8 h-8 ${iconClass}`} />
                    </div>

                    <div className="w-full">
                      <h2 className="text-2xl font-bold tracking-tight text-[#0f172a] mb-2">{agency.full_name || agency.name}</h2>
                      <p className="text-[#334155] text-sm font-semibold mb-6 line-clamp-2">{agency.description}</p>
                      <div className="flex items-center text-sm font-bold tracking-wide text-[#0f766e] group-hover:pl-2 transition-all duration-300">
                        <span className="opacity-80 group-hover:opacity-100">Browse Documents</span>
                        <ArrowRight className="w-4 h-4 ml-2 opacity-70 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                      </div>
                    </div>
                  </Link>
                );
              })}
        </div>

      </div>
    </div>
  );
}

export default Dashboard;
