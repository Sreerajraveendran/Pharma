import { Suspense, lazy, useState } from 'react';
import {
  LayoutDashboard,
  CircleDollarSign,
  Package,
  Users,
  Settings as SettingsIcon,
  PlusCircle,
  Bell,
  HelpCircle,
  Search,
  BarChart2,
  LogOut,
  KeyRound,
  UserCog
} from 'lucide-react';
import { useAuth, ROLE_LABELS } from './auth';

// Each screen is its own chunk, downloaded the first time it's opened (charts code only
// loads with Dashboard or Reports)
const Dashboard = lazy(() => import('./pages/Dashboard'));
const POSBilling = lazy(() => import('./pages/POSBilling'));
const InventoryList = lazy(() => import('./pages/InventoryList'));
const PatientsList = lazy(() => import('./pages/PatientsList'));
const Settings = lazy(() => import('./pages/Settings'));
const NewPrescriptionModal = lazy(() => import('./components/patients/NewPrescriptionModal'));
const Reports = lazy(() => import('./pages/Reports'));
const Login = lazy(() => import('./pages/Login'));
const ChangePassword = lazy(() => import('./pages/ChangePassword'));
const UsersAdmin = lazy(() => import('./pages/UsersAdmin'));

function ScreenLoading() {
  return (
    <div className="flex-1 flex items-center justify-center text-on-surface-variant text-sm font-semibold">
      Loading…
    </div>
  );
}
export default function App() {
  const { status, user } = useAuth();

  if (status === 'loading') {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-[#091E42] text-outline-variant text-sm font-semibold">
        Loading…
      </div>
    );
  }
  return (
    <Suspense fallback={<div className="min-h-screen w-full bg-[#091E42]" />}>
      {status === 'anonymous' || !user ? <Login />
        : user.must_change_password ? <ChangePassword forced />
        : <Workspace />}
    </Suspense>
  );
}

function Workspace() {
  const { user, logout, hasRole } = useAuth();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isRxModalOpen, setIsRxModalOpen] = useState(false);

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'pos', label: 'POS Billing', icon: CircleDollarSign },
    { id: 'inventory', label: 'Inventory', icon: Package },
    { id: 'patients', label: 'Patients', icon: Users },
    { id: 'reports', label: 'Reports', icon: BarChart2 },
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
    ...(hasRole('admin') ? [{ id: 'users', label: 'Users', icon: UserCog }] : []),
  ];

  const initials = (user?.full_name || '?').split(/\s+/).map(p => p[0]).slice(0, 2).join('').toUpperCase();

  return (
    <div className="flex h-screen w-full select-none overflow-hidden bg-background text-on-background">
      {/* Persistent Left Sidebar Navigation */}
      <aside className="h-screen w-[240px] bg-[#091E42] border-r border-outline-variant flex flex-col py-4 px-3 shrink-0 z-20">
        <div className="mb-8 px-4">
          <div className="text-xl font-black text-white tracking-tight">MediFlow</div>
          <div className="text-outline-variant opacity-75 font-semibold text-[10px] uppercase tracking-wider mt-0.5">Terminal 042</div>
        </div>
        <nav className="flex-1 space-y-1">
          {navItems.map(item => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button 
                key={item.id}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 ${isActive ? 'bg-primary-container text-white shadow-sm' : 'text-outline-variant hover:bg-white/10 hover:text-white'}`}
                onClick={() => setActiveTab(item.id)}
              >
                <Icon className="h-4.5 w-4.5 shrink-0" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        
        {/* Global Action: New Prescription */}
        {hasRole('admin', 'pharmacist') && <div className="mt-auto px-2">
          <button 
            className="w-full py-2.5 px-4 bg-primary text-white font-bold text-sm rounded-lg flex items-center justify-center gap-2 hover:bg-primary-container shadow-md hover:shadow-lg active:scale-95 transition-all"
            onClick={() => setIsRxModalOpen(true)}
          >
            <PlusCircle className="h-4.5 w-4.5" />
            <span>New Prescription</span>
          </button>
        </div>}
      </aside>

      {/* Main Workspace Frame */}
      <div className="flex-1 flex flex-col min-w-0">
        
        {/* Top Navbar */}
        <header className="h-16 w-full border-b border-outline-variant bg-surface-container-lowest flex justify-between items-center px-6 shrink-0 z-10">
          <div className="flex items-center gap-4 flex-1">
            <span className="font-extrabold text-sm text-primary uppercase tracking-wider hidden sm:inline">PharmaCore PMS</span>
            <div className="relative w-full max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-outline h-4 w-4" />
              <input 
                type="text" 
                className="w-full pl-10 pr-4 h-9 bg-surface-container border border-outline-variant rounded-lg text-xs focus:ring-2 focus:ring-primary focus:outline-none"
                placeholder="Global search medications, transactions, or patient directories..."
              />
            </div>
          </div>
          
          <div className="flex items-center gap-4 ml-6">
            <button className="p-2 text-on-surface-variant hover:bg-surface-container rounded-full relative">
              <Bell className="h-4.5 w-4.5" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-error rounded-full border border-white"></span>
            </button>
            <button className="p-2 text-on-surface-variant hover:bg-surface-container rounded-full">
              <HelpCircle className="h-4.5 w-4.5" />
            </button>
            <div className="h-6 w-[1px] bg-outline-variant"></div>
            
            {/* Signed-in user */}
            <div className="flex items-center gap-3">
              <div className="text-right hidden md:block">
                <p className="text-xs font-bold text-on-surface">{user?.full_name}</p>
                <p className="text-[9px] text-outline font-extrabold uppercase tracking-wider">{user ? ROLE_LABELS[user.role] : ''}</p>
              </div>
              <div
                className="w-8 h-8 rounded-full border border-outline-variant bg-primary-container text-white text-[11px] font-bold flex items-center justify-center"
                title={user?.email}
              >
                {initials}
              </div>
              <button
                className="p-2 text-on-surface-variant hover:bg-surface-container rounded-full"
                title="Change password"
                onClick={() => setActiveTab('account')}
              >
                <KeyRound className="h-4.5 w-4.5" />
              </button>
              <button
                className="p-2 text-on-surface-variant hover:bg-surface-container hover:text-error rounded-full"
                title="Sign out"
                onClick={logout}
              >
                <LogOut className="h-4.5 w-4.5" />
              </button>
            </div>
          </div>
        </header>

        {/* Tab Canvas Content */}
        <div className="flex-1 flex overflow-hidden">
          <Suspense fallback={<ScreenLoading />}>
            {activeTab === 'dashboard' && <Dashboard />}
            {activeTab === 'pos' && <POSBilling />}
            {activeTab === 'inventory' && <InventoryList />}
            {activeTab === 'patients' && <PatientsList />}
            {activeTab === 'reports' && <Reports />}
            {activeTab === 'settings' && <Settings />}
            {activeTab === 'users' && hasRole('admin') && <UsersAdmin />}
            {activeTab === 'account' && <ChangePassword />}
          </Suspense>
        </div>
      </div>

      {/* Global New Prescription Wizard Modal (loaded the first time it opens) */}
      {isRxModalOpen && (
        <Suspense fallback={null}>
          <NewPrescriptionModal isOpen onClose={() => setIsRxModalOpen(false)} />
        </Suspense>
      )}
    </div>
  );
}
