import React from 'react';
import { Info, Users, Shield, Target } from 'lucide-react';

function AboutUs() {
  return (
    <div className="flex-1 w-full h-full overflow-y-auto px-6 py-12 hide-scrollbar">
      <div className="max-w-4xl mx-auto animate-fade-up">
        
        <header className="mb-12 text-center">
          <div className="px-3 py-1 rounded-full border border-[#0f766e]/20 bg-[#0f766e]/5 text-xs font-semibold tracking-widest uppercase text-[#0f766e] mb-6 backdrop-blur-sm inline-block">
            Our Mission
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-[#0f172a] mb-4">
            About <span className="font-serif italic text-[#0f766e] font-medium">ARIS</span>
          </h1>
          <p className="text-[#334155] font-medium text-lg max-w-2xl mx-auto">
            Automated Regulatory Intelligence System (ARIS) is dedicated to streamlining compliance and accessibility in the pharmaceutical industry.
          </p>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16">
          <div className="glass-card p-8 border border-[#0f766e]/10">
            <div className="w-12 h-12 rounded-xl bg-[#0f766e]/10 flex items-center justify-center mb-6">
              <Target className="w-6 h-6 text-[#0f766e]" />
            </div>
            <h3 className="text-xl font-bold text-[#0f172a] mb-3">Our Vision</h3>
            <p className="text-[#334155] leading-relaxed">
              To become the global standard for regulatory intelligence, empowering organizations to navigate complex pharmaceutical landscapes with ease and precision.
            </p>
          </div>

          <div className="glass-card p-8 border border-[#0f766e]/10">
            <div className="w-12 h-12 rounded-xl bg-[#0f766e]/10 flex items-center justify-center mb-6">
              <Shield className="w-6 h-6 text-[#0f766e]" />
            </div>
            <h3 className="text-xl font-bold text-[#0f172a] mb-3">Reliability</h3>
            <p className="text-[#334155] leading-relaxed">
              We leverage state-of-the-art AI to ensure that the regulatory information provided is accurate, up-to-date, and directly sourced from official agencies like the FDA, EMA, and CDSCO.
            </p>
          </div>
        </div>

        <section className="text-center bg-[#0f766e]/5 rounded-3xl p-12 border border-[#0f766e]/10">
          <h2 className="text-3xl font-bold text-[#0f172a] mb-6">Transforming Compliance</h2>
          <p className="text-[#334155] text-lg mb-8 max-w-2xl mx-auto">
            By integrating RAG (Retrieval-Augmented Generation) technology, we provide an "Ask the AI" interface that understands the context of thousands of regulatory documents.
          </p>
          <div className="flex justify-center gap-4">
            <div className="flex items-center gap-2 text-[#0f766e] font-bold">
              <Users className="w-5 h-5" />
              <span>Built for Professionals</span>
            </div>
          </div>
        </section>

        {/* Team Section */}
        <section className="mt-16">
          <h2 className="text-3xl font-bold text-[#0f172a] mb-10 text-center">Our <span className="font-serif italic text-[#0f766e] font-medium">Team</span></h2>
          
          <div className="space-y-12">
            {/* IDEA Holders */}
            <div>
              <h3 className="text-xl font-bold text-[#0f766e] mb-6 border-l-4 border-[#0f766e] pl-4 uppercase tracking-widest text-sm">Idea Holders</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {[
                  { name: "Nipun Bhalla", email: "nipun0205@gmail.com" },
                  { name: "Manvi Singh", email: "manvi_pharmacy@sgtuniversity.org" },
                  { name: "Subham", email: "subhamsalriwal21@gmail.com" },
                  { name: "Vineet", email: "svineet8799singh@gmail.com" }
                ].map((person, i) => (
                  <div key={i} className="glass-card p-4 border border-[#0f766e]/5 hover:border-[#0f766e]/20 transition-all group">
                    <h4 className="font-bold text-[#0f172a] group-hover:text-[#0f766e] transition-colors">{person.name}</h4>
                    <p className="text-xs text-[#334155] font-medium opacity-70">{person.email}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Developer and Mentor */}
            <div>
              <h3 className="text-xl font-bold text-[#0f766e] mb-6 border-l-4 border-[#0f766e] pl-4 uppercase tracking-widest text-sm">Developer and Mentor</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {[
                  { name: "Himanshu Singh", email: "choudharyhimanshusingh966@gmail.com" },
                  { name: "Mr. Susanta Kundu", email: "susanta_soet@sgtuniversity.org" }
                ].map((person, i) => (
                  <div key={i} className="glass-card p-4 border border-[#0f766e]/5 hover:border-[#0f766e]/20 transition-all group">
                    <h4 className="font-bold text-[#0f172a] group-hover:text-[#0f766e] transition-colors">{person.name}</h4>
                    <p className="text-xs text-[#334155] font-medium opacity-70">{person.email}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

      </div>
    </div>
  );
}

export default AboutUs;
