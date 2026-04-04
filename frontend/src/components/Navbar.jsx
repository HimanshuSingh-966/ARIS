import { Compass, FileText, Search, Download, Info, MessageSquare, Menu, X } from 'lucide-react';
import clsx from 'clsx';
import { Link, useLocation } from 'react-router-dom';
import { useState } from 'react';

function Navbar({ onOpenAI }) {
  const location = useLocation();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const navLinks = [
    { name: 'Ask the AI', path: '/explore', icon: MessageSquare, isAction: true },
    { name: 'Forms Directory', path: '/forms', icon: Download },
    { name: 'About Us', path: '/about', icon: Info },
  ];

  const handleAction = (link) => {
    if (link.isAction) {
      onOpenAI();
    }
    setIsMenuOpen(false);
  };

  return (
    <header className="w-full h-16 border-b border-white/[0.04] bg-[#020303]/90 backdrop-blur-xl flex items-center justify-between px-6 z-50 sticky top-0">
      
      {/* Brand */}
      <Link to="/" className="flex items-center gap-3 group">
        <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center border border-white/20 shadow-[0_0_15px_rgba(255,255,255,0.05)] transition-transform group-hover:scale-105">
          <div className="w-3 h-3 bg-white rounded-full"></div>
        </div>
        <h1 className="text-[18px] font-bold tracking-wide text-white transition-opacity group-hover:opacity-80 uppercase">
          ARIS
        </h1>
      </Link>

      <div className="flex-1" />
      
      {/* Desktop Links */}
      <nav className="hidden md:flex items-center gap-10">
        {navLinks.map((link) => {
          const Icon = link.icon;
          if (link.isAction) {
            return (
              <button
                key={link.name}
                onClick={onOpenAI}
                className="flex items-center gap-2 text-sm font-medium transition-colors text-muted hover:text-white cursor-pointer"
              >
                <Icon className="w-4 h-4 text-muted/70" />
                {link.name}
              </button>
            );
          }

          const isActive = location.pathname.startsWith(link.path);
          return (
            <Link
              key={link.path}
              to={link.path}
              className={clsx(
                "flex items-center gap-2 text-sm font-medium transition-colors",
                isActive ? "text-white" : "text-muted hover:text-white"
              )}
            >
              <Icon className={clsx("w-4 h-4", isActive ? "text-white" : "text-muted/70")} />
              {link.name}
            </Link>
          );
        })}
      </nav>

      {/* Mobile Menu Toggle */}
      <button 
        className="md:hidden p-2 text-white/70 hover:text-white transition-colors"
        onClick={() => setIsMenuOpen(!isMenuOpen)}
      >
        {isMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
      </button>

      {/* Mobile Dropdown */}
      {isMenuOpen && (
        <div className="absolute top-16 left-0 w-full bg-[#020303]/95 backdrop-blur-2xl border-b border-white/[0.04] p-6 flex flex-col gap-6 md:hidden z-50 shadow-2xl">
          {navLinks.map((link) => {
            const Icon = link.icon;
            const isActive = location.pathname.startsWith(link.path);

            if (link.isAction) {
              return (
                <button
                  key={link.name}
                  onClick={() => handleAction(link)}
                  className="flex items-center gap-4 text-lg font-semibold text-muted hover:text-white"
                >
                  <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-emerald-400" />
                  </div>
                  {link.name}
                </button>
              );
            }

            return (
              <Link
                key={link.path}
                to={link.path}
                onClick={() => setIsMenuOpen(false)}
                className={clsx(
                  "flex items-center gap-4 text-lg font-semibold transition-colors",
                  isActive ? "text-white" : "text-muted hover:text-white"
                )}
              >
                <div className={clsx("w-10 h-10 rounded-xl flex items-center justify-center", isActive ? "bg-[#0f766e]/20 border border-[#0f766e]/30" : "bg-white/5")}>
                  <Icon className={clsx("w-5 h-5", isActive ? "text-[#5eead4]" : "text-muted/70")} />
                </div>
                {link.name}
              </Link>
            );
          })}
        </div>
      )}
      
    </header>
  );
}

export default Navbar;
