import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Layout from './components/Layout';
import { Spinner } from './components/ui';
import { HOME_BY_ROLE, useAuth } from './lib/auth';
import Login from './pages/Login';
import Register from './pages/Register';
import Profile from './pages/Profile';
import RequestDetail from './pages/RequestDetail';
import NewRequest from './pages/reporter/NewRequest';
import MyRequests from './pages/reporter/MyRequests';
import TaskQueue from './pages/technician/TaskQueue';
import TechProfile from './pages/technician/TechProfile';
import Overview from './pages/manager/Overview';
import AllRequests from './pages/manager/AllRequests';
import SlaCenter from './pages/manager/SlaCenter';
import Technicians from './pages/manager/Technicians';
import Assets from './pages/manager/Assets';
import RiskScores from './pages/manager/RiskScores';
import Reports from './pages/manager/Reports';
import UsersAdmin from './pages/admin/Users';
import Catalog from './pages/admin/Catalog';
import SettingsAdmin from './pages/admin/Settings';
import ModelCenter from './pages/admin/ModelCenter';
import Logs from './pages/admin/Logs';
import Backups from './pages/admin/Backups';

function RequireAuth({ roles, children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="px-8"><Spinner /></div>;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={HOME_BY_ROLE[user.role]} replace />;
  return children;
}

function Home() {
  const { user } = useAuth();
  return <Navigate to={HOME_BY_ROLE[user.role] || '/my-requests'} replace />;
}

const STAFF = ['Manager', 'Admin'];

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Home />} />
        <Route path="profile" element={<Profile />} />
        <Route path="report" element={<NewRequest />} />
        <Route path="my-requests" element={<MyRequests />} />
        <Route path="requests/:id" element={<RequestDetail />} />

        <Route path="tasks" element={<RequireAuth roles={['Technician']}><TaskQueue /></RequireAuth>} />
        <Route path="tech/profile" element={<RequireAuth roles={['Technician']}><TechProfile /></RequireAuth>} />

        <Route path="manager" element={<RequireAuth roles={STAFF}><Overview /></RequireAuth>} />
        <Route path="manager/requests" element={<RequireAuth roles={STAFF}><AllRequests /></RequireAuth>} />
        <Route path="manager/sla" element={<RequireAuth roles={STAFF}><SlaCenter /></RequireAuth>} />
        <Route path="manager/technicians" element={<RequireAuth roles={STAFF}><Technicians /></RequireAuth>} />
        <Route path="manager/assets" element={<RequireAuth roles={STAFF}><Assets /></RequireAuth>} />
        <Route path="manager/risk" element={<RequireAuth roles={STAFF}><RiskScores /></RequireAuth>} />
        <Route path="manager/reports" element={<RequireAuth roles={STAFF}><Reports /></RequireAuth>} />

        <Route path="admin/users" element={<RequireAuth roles={['Admin']}><UsersAdmin /></RequireAuth>} />
        <Route path="admin/catalog" element={<RequireAuth roles={['Admin']}><Catalog /></RequireAuth>} />
        <Route path="admin/settings" element={<RequireAuth roles={['Admin']}><SettingsAdmin /></RequireAuth>} />
        <Route path="admin/model" element={<RequireAuth roles={['Admin']}><ModelCenter /></RequireAuth>} />
        <Route path="admin/logs" element={<RequireAuth roles={['Admin']}><Logs /></RequireAuth>} />
        <Route path="admin/backups" element={<RequireAuth roles={['Admin']}><Backups /></RequireAuth>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
