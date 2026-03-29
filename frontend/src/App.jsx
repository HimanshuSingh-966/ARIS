import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar.jsx';
import Hero from './components/Hero.jsx';
import Dashboard from './components/Dashboard.jsx';
import AgencyDetail from './components/AgencyDetail.jsx';

// Placeholders for the remaining V2 pages
import PdfList from './components/PdfList.jsx';
import PdfViewer from './components/PdfViewer.jsx';
import FormsPage from './components/FormsPage.jsx';
import AboutUs from './components/AboutUs.jsx';

function App() {
  return (
    <div className="flex flex-col h-screen bg-background text-white overflow-hidden bg-mesh relative">
      <Navbar />
      <div className="flex-1 overflow-y-auto hide-scrollbar relative z-0">
        <Routes>
          <Route path="/" element={<Hero />} />
          <Route path="/explore" element={<Dashboard />} />
          <Route path="/about" element={<AboutUs />} />
          <Route path="/explore/:source" element={<AgencyDetail />} />
          <Route path="/explore/:source/:section" element={<PdfList />} />
          <Route path="/explore/:source/:section/:docId" element={<PdfViewer />} />
          <Route path="/forms" element={<FormsPage />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;
