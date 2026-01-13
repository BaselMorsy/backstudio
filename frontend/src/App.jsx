import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ToastProvider } from './components/common/ToastContainer';
import LandingPage from './pages/LandingPage';
import Dashboard from './pages/Dashboard';
import ProjectPage from './pages/ProjectPage';

function App() {
  return (
    <ToastProvider>
      <Router>
        <div className="min-h-screen bg-gray-50">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/project/:projectId" element={<ProjectPage />} />
          </Routes>
        </div>
      </Router>
    </ToastProvider>
  );
}

export default App;
