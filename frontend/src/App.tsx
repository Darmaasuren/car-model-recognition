import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import { Sidebar } from "./components/sidebar/Sidebar";
import { FileRecognitionPage } from "./pages/fileRecognition/FileRecognitionPage";
import { LivePage } from "./pages/live/LivePage";

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Sidebar />

        <div className="app__content">
          <Routes>
            <Route
              path="/"
              element={<Navigate to="/live" replace />}
            />

            <Route
              path="/live"
              element={<LivePage />}
            />

            <Route
              path="/files"
              element={<FileRecognitionPage />}
            />

            <Route
              path="*"
              element={<Navigate to="/live" replace />}
            />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
