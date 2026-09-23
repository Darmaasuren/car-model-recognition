import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { Sidebar } from './components/sidebar/Sidebar';
import { FileRecognitionPage } from './pages/fileRecognition/FileRecognitionPage';
import { LivePage } from './pages/live/LivePage';
import { LoginPage } from './pages/login/LoginPage';
import { ServiceComparisonPage } from './pages/serviceComparison/ServiceComparisonPage';
import { AuthProvider } from './auth/AuthProvider';
import { useAuth } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';

function Layout() {
  return <div className='app'><Sidebar /><div className='app__content'><Outlet /></div></div>;
}

function AppRoutes() {
  const { loading, error, refresh } = useAuth();
  if (loading) return <main className='login-page'>Нэвтрэлтийг шалгаж байна…</main>;
  if (error) return <main className='login-page'><div role='alert'>{error}
    <button onClick={() => void refresh()}>Дахин оролдох</button></div></main>;
  return <Routes>
    <Route path='/login' element={<LoginPage />} />
    <Route element={<RequireAuth />}>
      <Route element={<Layout />}>
        <Route path='/live' element={<LivePage />} />
        <Route path='/files' element={<FileRecognitionPage />} />
        <Route path='/service' element={<ServiceComparisonPage />} />
        <Route path='*' element={<Navigate to='/files' replace />} />
      </Route>
    </Route>
  </Routes>;
}

export default function App() {
  return <BrowserRouter><AuthProvider><AppRoutes /></AuthProvider></BrowserRouter>;
}
