import { Compass, FileText, Search, Download, Info, MessageSquare } from 'lucide-react';
import clsx from 'clsx';
import { Link, useLocation } from 'react-router-dom';

function Navbar() {
  const location = useLocation();

  const navLinks = [
    { name: 'Ask the AI', path: '/explore', icon: MessageSquare },
    { name: 'Forms Directory', path: '/forms', icon: Download },
    { name: 'About Us', path: '/about', icon: Info },
  ];

  return (
    <header className="w-full h-16 border-b border-white/[0.04] bg-[#020303]/90 backdrop-blur-xl flex items-center justify-between px-6 z-50 sticky top-0">
      
      {/* Brand */}
      <Link to="/" className="flex items-center gap-3 group">
        <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center border border-white/20 shadow-[0_0_15px_rgba(255,255,255,0.05)] transition-transform group-hover:scale-105">
          <div className="w-3 h-3 bg-white rounded-full"></div>
        </div>
        <h1 className="text-[18px] font-bold tracking-wide text-white transition-opacity group-hover:opacity-80">
          ARIS
        </h1>
      </Link>

      <div className="flex-1" />
      
      {/* Primary Links */}
      <nav className="hidden md:flex items-center gap-10">
        {navLinks.map((link) => {
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
              <link.icon className={clsx("w-4 h-4", isActive ? "text-white" : "text-muted/70")} />
              {link.name}
            </Link>
          );
        })}
      </nav>
      
    </header>
  );
}

export default Navbar;
