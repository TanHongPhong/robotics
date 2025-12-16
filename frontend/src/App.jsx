import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { InventoryProvider } from './context/InventoryContext';
import Sidebar from './components/Sidebar';
import InventoryPage from './pages/InventoryPage';
import ChatPage from './pages/ChatPage';
import SettingsPage from './pages/SettingsPage';
import VoiceToggleSTT from './components/VoiceToggleSTT';
import './styles/globals.css';

function App() {
  return (
    <ThemeProvider>
      <InventoryProvider>
        <Router>
          <Sidebar />
          <main className="main-content">
            <Routes>
              <Route path="/" element={<InventoryPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              {/* Voice test route */}
              <Route path="/voice" element={<VoiceToggleSTT backendUrl="http://127.0.0.1:5000" />} />
            </Routes>
          </main>
        </Router>
      </InventoryProvider>
    </ThemeProvider>
  );
}

export default App;
