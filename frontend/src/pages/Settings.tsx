import { useState, useEffect } from 'react';
import { apiFetch, errorMessage } from '../api';
import { useAuth, ROLE_LABELS } from '../auth';
import {
  Database,
  Settings as SettingsIcon,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Terminal,
  Cpu
} from 'lucide-react';

export default function Settings() {
  const { user, hasRole } = useAuth();
  const [dbStatus, setDbStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [seedMessage, setSeedMessage] = useState('');

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const res = await apiFetch('/api/settings/status');
      if (res.ok) {
        const data = await res.json();
        setDbStatus(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleSeedDatabase = async () => {
    const phrase = dbStatus?.demo_reset_confirmation || 'RESET DEMO DATA';
    const typed = window.prompt(
      `This permanently DELETES all patients, prescriptions, stock, invoices and audit logs, ` +
      `then loads demo data. User accounts are kept.\n\nType ${phrase} to continue:`
    );
    if (typed === null) return;
    if (typed.trim() !== phrase) {
      setSeedMessage('Reset cancelled: the confirmation text did not match.');
      return;
    }
    try {
      setSeeding(true);
      setSeedMessage('Deleting data and loading demo data...');
      const res = await apiFetch('/api/settings/seed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: typed.trim() }),
      });
      if (res.ok) {
        setSeedMessage('All business data was deleted and demo data reloaded.');
        fetchStatus();
      } else {
        setSeedMessage('Reset failed: ' + await errorMessage(res, 'unknown error'));
      }
    } catch (err) {
      console.error(err);
      setSeedMessage('Seeding network request failed.');
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 max-h-[calc(100vh-64px)]">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-on-surface tracking-tight flex items-center gap-2">
          <SettingsIcon className="w-6 h-6 text-primary" /> System Settings
        </h2>
        <p className="text-sm text-on-surface-variant">Manage database environments, execute testing simulations, and audit system status</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* DB Connection Status Card */}
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5 space-y-4">
          <h3 className="font-semibold text-on-surface flex items-center gap-2 text-sm uppercase tracking-wider">
            <Database className="w-4 h-4 text-primary" /> Database Connectivity
          </h3>
          
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-on-surface-variant">
              <RefreshCw className="w-4 h-4 animate-spin text-primary" /> Loading connection status...
            </div>
          ) : dbStatus ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                {dbStatus.status === 'online' ? (
                  <span className="flex items-center gap-1.5 px-2 py-0.5 text-xs rounded bg-secondary-container text-secondary font-bold border border-secondary/20">
                    <CheckCircle className="w-3.5 h-3.5" /> Database Online
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 px-2 py-0.5 text-xs rounded bg-error-container text-error font-bold border border-error/20">
                    <AlertCircle className="w-3.5 h-3.5" /> Offline
                  </span>
                )}

                <span className="px-2 py-0.5 text-xs rounded bg-primary-container/20 text-primary font-bold border border-primary/20">
                  MongoDB Client Connection Active
                </span>
              </div>

              <div className="bg-surface-container-low p-4 rounded-lg text-xs space-y-2 text-on-surface-variant font-semibold">
                <div className="flex justify-between">
                  <span className="font-normal">Connection Type:</span>
                  <span className="text-on-surface font-mono">MongoDB Server Driver</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-normal">Server Address:</span>
                  <span className="text-on-surface font-mono">{dbStatus.database_url}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-error font-bold">
              <AlertCircle className="w-4 h-4" /> Failed to connect to local FastAPI server. Ensure Uvicorn is running.
            </div>
          )}
        </div>

        {/* Reset / Seeding Simulator Card */}
        {hasRole('admin') && dbStatus?.demo_reset_enabled && (
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5 space-y-4">
          <h3 className="font-semibold text-on-surface flex items-center gap-2 text-sm uppercase tracking-wider">
            <Cpu className="w-4 h-4 text-error" /> Reset to Demo Data
          </h3>
          <p className="text-xs text-on-surface-variant font-medium leading-relaxed">
            <strong className="text-error">Deletes all business data</strong>: patients, prescriptions, medicines, stock, invoices and audit logs. It then loads demo data with 30 days of sales history. User accounts are kept. Use this only on demo or test systems; it is disabled when <code>ALLOW_DEMO_RESET=false</code>.
          </p>
          {dbStatus?.demo_data?.status && (
            <p className="text-[11px] text-outline">
              Demo data: {dbStatus.demo_data.status}
              {dbStatus.demo_data.completed_at ? ` (loaded ${new Date(dbStatus.demo_data.completed_at).toLocaleString()})` : ''}
            </p>
          )}

          <div className="flex items-center gap-4">
            <button 
              className="h-10 px-4 bg-primary text-white rounded-lg text-sm font-bold flex items-center gap-2 hover:bg-primary-container shadow-sm active:scale-95 transition-all disabled:opacity-50"
              onClick={handleSeedDatabase}
              disabled={seeding}
            >
              <RefreshCw className={`w-4 h-4 ${seeding ? 'animate-spin' : ''}`} /> Reset to Demo Data
            </button>
            <button 
              className="h-10 px-4 border border-outline-variant text-on-surface rounded-lg text-sm font-bold flex items-center gap-2 hover:bg-surface-container transition-all"
              onClick={fetchStatus}
            >
              Check Connection
            </button>
          </div>

          {seedMessage && (
            <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg text-xs font-bold text-primary animate-pulse">
              {seedMessage}
            </div>
          )}
        </div>
        )}

        {/* Terminal Configuration Card */}
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5 space-y-4">
          <h3 className="font-semibold text-on-surface flex items-center gap-2 text-sm uppercase tracking-wider">
            <Terminal className="w-4 h-4 text-primary" /> Active Terminal Parameters
          </h3>
          <div className="bg-[#091E42] text-white p-4 rounded-lg font-mono text-[11px] leading-relaxed space-y-1">
            <p className="text-outline-variant"># MediFlow Terminal Audit Log</p>
            <p><span className="text-secondary font-bold">TERMINAL_ID:</span> TERMINAL_042</p>
            <p><span className="text-secondary font-bold">OPERATOR:</span> {user?.full_name} ({user ? ROLE_LABELS[user.role] : ''})</p>
            <p><span className="text-secondary font-bold">WORKSPACE:</span> PharmaCore Enterprise</p>
            <p><span className="text-secondary font-bold">VERSION:</span> Enterprise v2.4 (React + FastAPI + MongoDB)</p>
            <p><span className="text-secondary font-bold">SYSTEM_LOCALE:</span> IN (Schedule H Drug Regulations Enabled)</p>
          </div>
        </div>
      </div>
    </div>
  );
}
