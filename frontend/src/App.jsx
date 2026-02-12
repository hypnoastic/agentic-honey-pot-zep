import { useState, useEffect } from 'react';
import Dashboard from './components/Dashboard';
import LoginPage from './components/LoginPage';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if session is valid? For now just rely on local state 
    // or maybe check a cookie if we had one.
    // The requirement is simple password check.
    setLoading(false);
  }, []);

  const handleLogin = () => {
    setIsAuthenticated(true);
  };

  if (loading) return <div className="bg-black text-white h-screen flex items-center justify-center">Loading...</div>;

  return (
    <>
      {isAuthenticated ? <Dashboard /> : <LoginPage onLogin={handleLogin} />}
    </>
  );
}

export default App;
