import { formatINR } from '../lib/format';
import { useAuditLogs, useDashboard } from '../queries';
import {
  FileText,
  Layers,
  AlertTriangle,
  Calendar,
  DollarSign,
  Clock
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  BarChart, 
  Bar, 
  Cell 
} from 'recharts';

export default function Dashboard() {
  // Both requests run in parallel and are cached across tab switches
  const { data: metrics, isLoading } = useDashboard();
  const { data: logs = [] } = useAuditLogs(5);
  const loading = isLoading;
  if (loading || !metrics) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary"></div>
          <p className="text-on-surface-variant font-medium text-sm">Loading analytics summary...</p>
        </div>
      </div>
    );
  }

  const formatCurrency = formatINR;


  const statCards = [
    {
      title: "Total Sales Revenue",
      value: formatCurrency(metrics.total_revenue),
      sub: "Collected, net of refunds (30 days)",
      icon: DollarSign,
      color: "text-secondary bg-secondary-container/20 border border-secondary/20",
    },
    {
      title: "Prescriptions Dispensed",
      value: metrics.prescriptions_dispensed,
      sub: "Prescriptions with items dispensed",
      icon: FileText,
      color: "text-primary bg-primary-container/20 border border-primary/20",
    },
    {
      title: "Active Stock Valuation",
      value: formatCurrency(metrics.active_inventory_value),
      sub: "Total MRP worth on hand",
      icon: Layers,
      color: "text-tertiary bg-tertiary/10 border border-tertiary/20",
    },
    {
      title: "Low Stock Items",
      value: metrics.low_stock_alerts,
      sub: "Requires replenishment",
      icon: AlertTriangle,
      color: metrics.low_stock_alerts > 0 
        ? "text-error bg-error-container/20 border border-error/20 animate-pulse" 
        : "text-on-surface-variant bg-surface-container border border-outline-variant",
    },
    {
      title: "Critical Batch Expiries",
      value: metrics.critical_expiry_alerts,
      sub: "Expiring in < 30 days",
      icon: Calendar,
      color: metrics.critical_expiry_alerts > 0
        ? "text-error bg-error-container/20 border border-error/20 animate-pulse"
        : "text-on-surface-variant bg-surface-container border border-outline-variant",
    }
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 max-h-[calc(100vh-64px)]">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-on-surface tracking-tight">Reports &amp; Analytics</h2>
        <p className="text-sm text-on-surface-variant">Real-time clinical performance and inventory metrics</p>
      </div>

      {/* Grid KPI Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        {statCards.map((card, idx) => (
          <div key={idx} className="bg-surface-container-lowest border border-outline-variant p-4 rounded-xl flex flex-col justify-between hover:shadow-sm transition-all">
            <div className="flex justify-between items-start">
              <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">{card.title}</span>
              <div className={`p-2 rounded-lg ${card.color}`}>
                <card.icon className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-4">
              <span className="text-xl font-bold text-on-surface tracking-tight">{card.value}</span>
              <p className="text-xs text-on-surface-variant mt-1">{card.sub}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Visual Analytics Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Sales Chart */}
        <div className="lg:col-span-2 bg-surface-container-lowest border border-outline-variant rounded-xl p-5 flex flex-col justify-between h-[380px]">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h3 className="font-semibold text-on-surface">Revenue &amp; Prescriptions Trend</h3>
              <p className="text-xs text-on-surface-variant">Daily sales breakdown over the last 7 days</p>
            </div>
            <div className="flex items-center gap-4 text-xs font-medium">
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-primary inline-block"></span>Revenue</span>
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-secondary inline-block"></span>Prescriptions</span>
            </div>
          </div>
          <div className="flex-1 w-full min-h-0">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={metrics.sales_chart} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f1f1" vertical={false} />
                <XAxis dataKey="name" stroke="#737685" fontSize={11} tickLine={false} />
                <YAxis yAxisId="left" stroke="#737685" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis yAxisId="right" orientation="right" stroke="#737685" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip />
                <Line yAxisId="left" type="monotone" dataKey="revenue" stroke="#003d9b" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} name="Sales (₹)" />
                <Line yAxisId="right" type="monotone" dataKey="prescriptions" stroke="#006c47" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} name="Rx Dispensed" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Category Value Distribution Chart */}
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5 flex flex-col justify-between h-[380px]">
          <div>
            <h3 className="font-semibold text-on-surface">Stock Value by Category</h3>
            <p className="text-xs text-on-surface-variant">MRP inventory valuation distribution</p>
          </div>
          <div className="flex-1 w-full min-h-0 my-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={metrics.categories_chart} layout="vertical" margin={{ top: 5, right: 5, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f1f1" horizontal={false} />
                <XAxis type="number" stroke="#737685" fontSize={10} tickLine={false} />
                <YAxis dataKey="name" type="category" stroke="#737685" fontSize={11} tickLine={false} width={80} />
                <Tooltip formatter={(value: any) => formatCurrency(value)} />
                <Bar dataKey="stock_value" radius={[0, 4, 4, 0]} name="Value (₹)">
                  {metrics.categories_chart.map((entry: any, index: number) => (
                    <Cell key={`cell-${index}`} fill={entry.color || "#003d9b"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Recent Transactions list */}
      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h3 className="font-semibold text-on-surface">Recent Dispensed Logs</h3>
            <p className="text-xs text-on-surface-variant">Real-time prescription checkout tracking</p>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-primary font-semibold cursor-pointer hover:underline">
            <Clock className="w-3.5 h-3.5" /> Live feed active
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-outline-variant text-xs text-on-surface-variant font-semibold bg-surface-container-low">
                <th className="p-3">Timestamp</th>
                <th className="p-3">Medicine Name</th>
                <th className="p-3">Batch ID</th>
                <th className="p-3">Action</th>
                <th className="p-3 text-right">Quantity</th>
                <th className="p-3">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant text-sm font-medium text-on-surface zebra-table">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-6 text-center text-on-surface-variant">No transaction logs available.</td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-surface-container/20">
                    <td className="p-3 text-xs text-on-surface-variant">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="p-3 text-primary">{log.medicine_name}</td>
                    <td className="p-3 font-mono text-xs text-on-surface-variant">{log.batch_number}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 text-xs rounded bg-secondary-container text-secondary font-bold">
                        {log.action_type}
                      </span>
                    </td>
                    <td className="p-3 text-right font-semibold text-error">
                      {log.quantity_changed}
                    </td>
                    <td className="p-3 text-xs text-on-surface-variant">{log.notes}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
