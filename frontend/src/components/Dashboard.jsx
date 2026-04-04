import React from 'react';
import { ArrowRight, Globe, FileText, Database } from 'lucide-react';
import { Link } from 'react-router-dom';

const AGENCIES = [
  {
    id: 'cdsco',
    name: 'India CDSCO',
    fullName: 'Central Drugs Standard Control Organisation',
    color: 'from-orange-500/20 to-transparent',
    borderColor: 'hover:border-orange-500/50',
    icon: <FileText className="w-8 h-8 text-orange-400" />
  },
  {
    id: 'fda',
    name: 'US FDA',
    fullName: 'Food and Drug Administration',
    color: 'from-blue-500/20 to-transparent',
    borderColor: 'hover:border-blue-500/50',
    icon: <Globe className="w-8 h-8 text-blue-400" />
  },
  {
    id: 'ema',
    name: 'Europe EMA',
    fullName: 'European Medicines Agency',
    color: 'from-yellow-500/20 to-transparent',
    borderColor: 'hover:border-yellow-500/50',
    icon: <Database className="w-8 h-8 text-yellow-400" />
  }
];

function Dashboard() {
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

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {AGENCIES.map(agency => (
            <Link 
              key={agency.id}
              to={`/explore/${agency.id}`}
              className={`glass-card relative overflow-hidden group cursor-pointer border border-[#0f766e]/10 transition-all duration-300 ${agency.borderColor} hover:-translate-y-1 hover:shadow-2xl hover:shadow-[#0f766e]/20 p-8 flex flex-col items-start h-[320px]`}
            >
              {/* Background Glow */}
              <div className={`absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl ${agency.color} blur-[80px] opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-full pointer-events-none -mr-10 -mt-10`} />

              <div className="w-16 h-16 rounded-2xl bg-white/60 border border-[#0f766e]/10 flex items-center justify-center mb-auto shadow-sm">
                {agency.icon}
              </div>

              <div className="w-full">
                <h2 className="text-2xl font-bold tracking-tight text-[#0f172a] mb-2">{agency.name}</h2>
                <p className="text-[#334155] text-sm font-semibold mb-6 line-clamp-2">{agency.fullName}</p>
                <div className="flex items-center text-sm font-bold tracking-wide text-[#0f766e] group-hover:pl-2 transition-all duration-300">
                  <span className="opacity-80 group-hover:opacity-100">Browse Documents</span>
                  <ArrowRight className="w-4 h-4 ml-2 opacity-70 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                </div>
              </div>
            </Link>
          ))}
        </div>

      </div>
    </div>
  );
}

export default Dashboard;
