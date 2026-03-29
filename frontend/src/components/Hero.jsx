import React from 'react';
import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

function Hero() {
  return (
    <div className="flex flex-col items-center justify-center w-full h-full min-h-screen px-4 animate-fade-up bg-mesh relative">
      
      {/* Landio branding top-left for the hero */}
      <div className="absolute top-6 left-8 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center border border-white/20 shadow-[0_0_15px_rgba(255,255,255,0.1)]">
          <div className="w-3 h-3 bg-white rounded-full"></div>
        </div>
        <h1 className="text-2xl font-bold tracking-wide text-[#0f172a]">
          ARIS
        </h1>
      </div>

      <div className="flex flex-col items-center max-w-3xl w-full text-center mt-[-10vh]">
        <div className="px-5 py-2 rounded-full border border-white/40 bg-white/20 text-sm font-bold tracking-widest uppercase text-[#0f766e] mb-8 backdrop-blur-md shadow-sm">
          Automated Regulatory Intelligence System
        </div>
        
        <h1 className="text-5xl sm:text-7xl font-bold tracking-tight text-[#0f172a] mb-6 leading-tight">
          Automate Smarter. <br />
          <span className="font-serif italic text-[#0f766e] font-medium">Compliance With AI.</span>
        </h1>
        
        <p className="text-lg text-muted mb-12 max-w-xl leading-relaxed">
          Instantly search and analyze guidelines, regulations, and forms across the US FDA, EMA, and India CDSCO.
        </p>

        <Link 
          to="/explore"
          className="btn-primary text-lg !px-8 !py-4 group"
        >
          Try Now 
          <ArrowRight className="w-5 h-5 ml-3 opacity-70 group-hover:translate-x-1 group-hover:opacity-100 transition-all" />
        </Link>
      </div>
      
      {/* Subtle floor glow reflection */}
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[80%] h-[30vh] bg-gradient-to-t from-white/5 to-transparent blur-3xl -z-10 rounded-[100%]" />
    </div>
  );
}

export default Hero;
