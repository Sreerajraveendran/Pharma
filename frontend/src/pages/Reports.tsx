import { useState, useEffect, useRef } from 'react';
import { apiFetch, errorMessage } from '../api';
import { formatDate, formatINR, formatTime } from '../lib/format';
import { notify } from '../lib/notify';
import ChartsGrid from '../components/reports/ChartsGrid';
import InvoiceDrawer from '../components/reports/InvoiceDrawer';
import KpiRibbon from '../components/reports/KpiRibbon';
import { canCancel, canRefund } from '../components/reports/rules';
import {
  Search,
  Download,
  Printer,
  RefreshCw,
  Eye,
  FileText,
  Copy,
  RotateCcw,
  Ban,
  Trash2,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

// YYYY-MM-DD of a date in the viewer's local calendar
function toLocalDateString(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function localDayStart(day: string) {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d, 0, 0, 0, 0);
}

function localDayEnd(day: string) {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d, 23, 59, 59, 999);
}

// [start, end] local calendar days (YYYY-MM-DD) for a date preset. toISOString() is
// avoided because it converts to UTC and shifts days east of Greenwich.
function presetRange(preset: string): [string, string] {
  const now = new Date();
  const y = now.getFullYear(), m = now.getMonth(), d = now.getDate();
  let start: Date | null = null;
  let end: Date = now;
  if (preset === 'Today') {
    start = now;
  } else if (preset === 'Yesterday') {
    start = new Date(y, m, d - 1);
    end = new Date(y, m, d - 1);
  } else if (preset === 'Last 7 Days') {
    start = new Date(y, m, d - 6);
  } else if (preset === 'Last 30 Days') {
    start = new Date(y, m, d - 29);
  } else if (preset === 'This Month') {
    start = new Date(y, m, 1);
  } else if (preset === 'Previous Month') {
    start = new Date(y, m - 1, 1);
    end = new Date(y, m, 0);
  } else if (preset === 'This Quarter') {
    start = new Date(y, Math.floor(m / 3) * 3, 1);
  }
  return start ? [toLocalDateString(start), toLocalDateString(end)] : ['', ''];
}

export default function Reports() {
  // State variables for filter controls
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [datePreset, setDatePreset] = useState('Last 7 Days');
  // Initialised from the preset so the first fetch already uses the right range
  const [startDate, setStartDate] = useState(() => presetRange('Last 7 Days')[0]);
  const [endDate, setEndDate] = useState(() => presetRange('Last 7 Days')[1]);
  const [billType, setBillType] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('');
  const [status, setStatus] = useState('');
  const [cashier, setCashier] = useState('');
  const [store, setStore] = useState('');

  // Table states
  const [invoices, setInvoices] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(25);
  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [pagination, setPagination] = useState<any>({});
  const [summaryTotals, setSummaryTotals] = useState<any>({});

  // Analytics and charts states
  const [kpis, setKpis] = useState<any>(null);
  const [chartsData, setChartsData] = useState<any>(null);

  // UI drawer/preview states
  const [selectedInvoice, setSelectedInvoice] = useState<any>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pre-seed filter options
  // Filter choices come from the invoices themselves, so real cashiers and stores appear
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({});
  useEffect(() => {
    apiFetch('/api/billing/invoices/filter-options')
      .then(res => (res.ok ? res.json() : {}))
      .then(setFilterOptions)
      .catch(err => console.error("Error loading filter options:", err));
  }, []);
  const optionsFor = (key: string, current: string) => {
    const values = filterOptions[key] || [];
    return current && !values.includes(current) ? [...values, current] : values;
  };

  // Keyboard shortcut focus
  const searchInputRef = useRef<HTMLInputElement>(null);
  // Latest fetchData, so the keyboard shortcut never uses stale filters
  const fetchDataRef = useRef<() => void>(() => {});

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsDrawerOpen(false);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
      if (e.key === 'r' && (e.target as HTMLElement).tagName !== 'INPUT' && (e.target as HTMLElement).tagName !== 'SELECT') {
        e.preventDefault();
        fetchDataRef.current();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Sync date ranges based on presets (see presetRange)
  useEffect(() => {
    if (datePreset === 'Custom') return;
    const [start, end] = presetRange(datePreset);
    setStartDate(start);
    setEndDate(end);
  }, [datePreset]);

  // The search box updates `search` (and refetches) only once typing pauses
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (searchInput !== search) {
        setPage(1);
        setSearch(searchInput);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);
  // Every filter, with local calendar days converted to exact UTC instants
  const buildFilterParams = () => {
    const params = new URLSearchParams();
    if (search) params.append('search', search);
    if (startDate) params.append('start_date', localDayStart(startDate).toISOString());
    if (endDate) params.append('end_date', localDayEnd(endDate).toISOString());
    if (billType) params.append('bill_type', billType);
    if (paymentMethod) params.append('payment_method', paymentMethod);
    if (status) params.append('status', status);
    if (cashier) params.append('cashier', cashier);
    if (store) params.append('store', store);
    return params;
  };
  const tzOffset = String(-new Date().getTimezoneOffset());

  // Fetch data hook
  // Only the latest request may update the screen; older ones are cancelled
  const inFlight = useRef<AbortController | null>(null);

  const fetchData = async () => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    const { signal } = controller;
    setLoading(true);
    setError(null);

    const filterParams = buildFilterParams();
    const ledgerParams = new URLSearchParams(filterParams);
    ledgerParams.append('sort_by', sortBy);
    ledgerParams.append('sort_order', sortOrder);
    ledgerParams.append('page', String(page));
    ledgerParams.append('limit', String(limit));
    const chartParams = new URLSearchParams(filterParams);
    chartParams.append('tz_offset', tzOffset);

    try {
      const [res, kpisRes, chartsRes] = await Promise.all([
        apiFetch(`/api/billing/invoices?${ledgerParams.toString()}`, { signal }),
        apiFetch(`/api/billing/invoices/kpis?${filterParams.toString()}`, { signal }),
        apiFetch(`/api/billing/invoices/charts?${chartParams.toString()}`, { signal }),
      ]);
      if (!res.ok) throw new Error(await errorMessage(res, "Failed to fetch billing ledger."));
      const ledger = await res.json();
      setInvoices(ledger.data || []);
      setPagination(ledger.pagination || {});
      setSummaryTotals(ledger.summary_totals || {});
      if (kpisRes.ok) setKpis(await kpisRes.json());
      if (chartsRes.ok) setChartsData(await chartsRes.json());
    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      console.error(err);
      setError(err?.message || "Unable to sync financial database. Please retry.");
    } finally {
      if (inFlight.current === controller) setLoading(false);
    }
  };
  fetchDataRef.current = fetchData;

  useEffect(() => {
    fetchData();
  }, [search, startDate, endDate, billType, paymentMethod, status, cashier, store, sortBy, sortOrder, page, limit]);

  const toggleSort = (field: string) => {
    setPage(1);
    if (sortBy === field) setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc');
    else { setSortBy(field); setSortOrder('desc'); }
  };
  const sortMark = (field: string) => (sortBy === field ? (sortOrder === 'desc' ? ' ↓' : ' ↑') : '');

  // CSV Export Trigger (same filters as the screen)
  const handleExportCSV = () => {
    window.open(`/api/billing/invoices/export/csv?${buildFilterParams().toString()}`, '_blank');
  };

  // Excel (Tab Separated Value download styled as xls)
  const handleExportExcel = () => {
    handleExportCSV(); // Standard CSV exported for simplified platform compatibility
  };

  // PDF Report Export Trigger
  const handleExportPDFReport = () => {
    const params = buildFilterParams();
    params.append('tz_offset', tzOffset);
    window.open(`/api/billing/invoices/export/pdf?${params.toString()}`, '_blank');
  };

  // Refresh
  const handleRefresh = () => {
    fetchData();
  };

  // Reset Filters
  const handleClearFilters = () => {
    setSearch('');
    setSearchInput('');
    setDatePreset('Last 7 Days');
    setBillType('');
    setPaymentMethod('');
    setStatus('');
    setCashier('');
    setStore('');
    setPage(1);
  };

  // Invoice Specific Operations
  const handleViewInvoice = async (invoiceId: string) => {
    try {
      const res = await apiFetch(`/api/billing/invoices/${invoiceId}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedInvoice(data);
        setIsDrawerOpen(true);
      }
    } catch (err) {
      notify.error("Error reading invoice details.");
    }
  };

  const handleCancelInvoice = async (invoiceId: string) => {
    if (window.confirm("Are you sure you want to cancel this invoice? This transaction will be marked as Cancelled.")) {
      try {
        const res = await apiFetch(`/api/billing/invoices/${invoiceId}/cancel`, { method: 'POST' });
        if (res.ok) {
          fetchData();
          setIsDrawerOpen(false);
          notify.error("Invoice cancelled. Any stock from a POS sale has been returned to inventory.");
        } else {
          notify.error("Cancellation failed: " + await errorMessage(res, "unknown error"));
        }
      } catch (err) {
        notify.error("Cancellation failed.");
      }
    }
  };

  const handleRefundInvoice = async (invoiceId: string) => {
    const reason = prompt("Enter Refund Reason:");
    if (reason === null) return;
    if (!reason.trim()) {
      notify.error("Refund reason is required.");
      return;
    }
    const inv = invoices.find(i => i.id === invoiceId) || selectedInvoice;
    const refundable = inv ? (inv.amount_paid - (inv.refunded_amount || 0)) : null;
    const amtStr = prompt(refundable !== null
      ? `Enter refund amount (up to ₹${refundable.toFixed(2)}):`
      : "Enter refund amount:", refundable !== null ? refundable.toFixed(2) : '');
    if (amtStr === null) return;
    const amount = parseFloat(amtStr);
    if (isNaN(amount) || amount <= 0) {
      notify.error("Invalid refund amount.");
      return;
    }

    try {
      const res = await apiFetch(`/api/billing/invoices/${invoiceId}/refund?refund_amount=${amount}&reason=${encodeURIComponent(reason)}`, { method: 'POST' });
      if (res.ok) {
        const updated = await res.json();
        fetchData();
        setIsDrawerOpen(false);
        notify.success(updated.status === 'Partially Refunded'
          ? `Partial refund of ₹${amount.toFixed(2)} recorded.`
          : "Refund processed successfully.");
      } else {
        notify.error("Refund failed: " + await errorMessage(res, "unknown error"));
      }
    } catch (err) {
      notify.error("Refund failed.");
    }
  };

  const handleDuplicateInvoice = async (invoiceId: string) => {
    try {
      const res = await apiFetch(`/api/billing/invoices/${invoiceId}/duplicate`, { method: 'POST' });
      if (res.ok) {
        const copy = await res.json();
        fetchData();
        notify.success(`Created ${copy.id} as an unpaid (Pending) copy of ${invoiceId}.`);
      } else {
        notify.error("Duplication failed: " + await errorMessage(res, "unknown error"));
      }
    } catch (err) {
      notify.error("Duplication failed.");
    }
  };

  const handleDeleteInvoice = async (invoiceId: string) => {
    if (window.confirm("Admin Check: Proceed with deleting this invoice record permanently?")) {
      try {
        const res = await apiFetch(`/api/billing/invoices/${invoiceId}`, { method: 'DELETE' });
        if (res.ok) {
          fetchData();
          setIsDrawerOpen(false);
          notify.error("Invoice deleted.");
        } else {
          notify.error("Deletion failed: " + await errorMessage(res, "unknown error"));
        }
      } catch (err) {
        notify.error("Deletion failed.");
      }
    }
  };

  const handlePrintDrawer = () => {
    if (selectedInvoice) {
      window.open(`/api/billing/invoices/${selectedInvoice.id}/pdf?tz_offset=${tzOffset}`, '_blank');
    }
  };

  // Badge mapping utility
  const getBadgeColors = (value: any) => {
    const v = String(value).toLowerCase();
    if (v.includes('pos') || v.includes('sale') || v === 'prescription sale') {
      return 'bg-blue-50 text-blue-700 border-blue-200';
    }
    if (v.includes('insurance') || v.includes('claim')) {
      return 'bg-purple-50 text-purple-700 border-purple-200';
    }
    if (v.includes('refund') || v.includes('return') || v.includes('credit')) {
      return 'bg-red-50 text-red-700 border-red-200';
    }
    if (v.includes('pending') || v.includes('credit note')) {
      return 'bg-amber-50 text-amber-700 border-amber-200';
    }
    if (v.includes('paid') || v.includes('approved') || v.includes('settled') || v === 'paid') {
      return 'bg-green-50 text-green-700 border-green-200';
    }
    if (v.includes('cancelled') || v.includes('rejected') || v === 'cancelled') {
      return 'bg-gray-50 text-gray-700 border-gray-200';
    }
    if (v.includes('partial') || v.includes('partially paid')) {
      return 'bg-orange-50 text-orange-700 border-orange-200';
    }
    return 'bg-gray-50 text-gray-700 border-gray-200';
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-background">

      {/* ---------------- SECTION 1: FILTER & QUERY BAR ---------------- */}
      <div className="bg-white border-b border-outline-variant p-4 space-y-3 z-10 shrink-0 sticky top-0">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-black text-on-surface">Financial Analytics</h1>
            <p className="text-xs text-on-surface-variant">Real-time billing overview, tax audits, and revenue tracking.</p>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleExportCSV}
              className="h-9 px-3 border border-outline text-on-surface text-xs font-bold rounded-lg hover:bg-surface-container flex items-center gap-1.5 transition-all"
            >
              <Download className="w-3.5 h-3.5" /> CSV
            </button>
            <button
              onClick={handleExportExcel}
              className="h-9 px-3 border border-outline text-on-surface text-xs font-bold rounded-lg hover:bg-surface-container flex items-center gap-1.5 transition-all"
            >
              <FileText className="w-3.5 h-3.5" /> Excel
            </button>
            <button
              onClick={handleExportPDFReport}
              className="h-9 px-3 border border-outline text-on-surface text-xs font-bold rounded-lg hover:bg-surface-container flex items-center gap-1.5 transition-all"
            >
              <Printer className="w-3.5 h-3.5" /> Print Summary
            </button>
            <button
              onClick={handleRefresh}
              className="h-9 w-9 border border-outline text-on-surface hover:bg-surface-container flex items-center justify-center rounded-lg transition-all"
              title="Refresh Data (Keyboard shortcut: R)"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={handleClearFilters}
              className="h-9 px-3 text-error border border-error/20 hover:bg-error/5 text-xs font-bold rounded-lg transition-all"
            >
              Clear All
            </button>
          </div>
        </div>

        {/* Query & preset bars */}
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2.5">
          {/* Search bar */}
          <div className="col-span-2 relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-outline w-3.5 h-3.5" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Search Invoice, Patient, Phone..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="w-full pl-8 pr-2 h-9 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary text-on-surface font-semibold"
            />
          </div>

          {/* Presets */}
          <div>
            <select
              value={datePreset}
              onChange={(e) => setDatePreset(e.target.value)}
              className="w-full px-2 h-9 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary text-on-surface font-bold"
            >
              <option value="Today">Today</option>
              <option value="Yesterday">Yesterday</option>
              <option value="Last 7 Days">Last 7 Days</option>
              <option value="Last 30 Days">Last 30 Days</option>
              <option value="This Month">This Month</option>
              <option value="Previous Month">Previous Month</option>
              <option value="This Quarter">This Quarter</option>
              <option value="Custom">Custom Presets</option>
            </select>
          </div>

          {/* Date range pickers */}
          {datePreset === 'Custom' && (
            <>
              <div>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-2 h-9 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary text-on-surface font-semibold"
                />
              </div>
              <div>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full px-2 h-9 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary text-on-surface font-semibold"
                />
              </div>
            </>
          )}

          {/* Bill type dropdown */}
          <div>
            <select
              value={billType}
              onChange={(e) => { setPage(1); setBillType(e.target.value); }}
              className="w-full px-2 h-9 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary text-on-surface font-semibold"
            >
              <option value="">All Bill Types</option>
              {optionsFor('bill_types', billType).map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>

          {/* Payment Method */}
          <div>
            <select
              value={paymentMethod}
              onChange={(e) => { setPage(1); setPaymentMethod(e.target.value); }}
              className="w-full px-2 h-9 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary text-on-surface font-semibold"
            >
              <option value="">All Payments</option>
              {optionsFor('payment_methods', paymentMethod).map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>

          {/* Status */}
          <div>
            <select
              value={status}
              onChange={(e) => { setPage(1); setStatus(e.target.value); }}
              className="w-full px-2 h-9 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary text-on-surface font-semibold"
            >
              <option value="">All Statuses</option>
              <option value="Paid">Paid</option>
              <option value="Pending">Pending</option>
              <option value="Partially Paid">Partially Paid</option>
              <option value="Partially Refunded">Partially Refunded</option>
              <option value="Refunded">Refunded</option>
              <option value="Cancelled">Cancelled</option>
            </select>
          </div>

          {/* Cashier */}
          <div>
            <select
              value={cashier}
              onChange={(e) => { setPage(1); setCashier(e.target.value); }}
              className="w-full px-2 h-9 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary text-on-surface font-semibold"
            >
              <option value="">All Cashiers</option>
              {optionsFor('cashiers', cashier).map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* Additional Filter: Store */}
          <div>
            <select
              value={store}
              onChange={(e) => { setPage(1); setStore(e.target.value); }}
              className="w-full px-2 h-9 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary text-on-surface font-semibold"
            >
              <option value="">All Stores</option>
              {optionsFor('stores', store).map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* Main content scroll container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {error && (
          <div role="alert" className="p-3 rounded-lg bg-error-container border border-error/20 text-xs font-semibold text-error">{error}</div>
        )}

        {/* ---------------- SECTION 2: FINANCIAL KPI RIBBON ---------------- */}
        {kpis && <KpiRibbon kpis={kpis} />}

        {/* ---------------- SECTION 3: UNIVERSAL LEDGER TABLE ---------------- */}
        <div className="bg-white border border-outline-variant rounded-xl overflow-hidden flex flex-col">

          {/* Table Header Controls */}
          <div className="p-4 border-b border-outline-variant bg-surface-container-low flex flex-col sm:flex-row sm:items-center justify-between gap-3 sticky top-0 z-20">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-on-surface">Ledger Entries</span>
              <span className="bg-primary/10 text-primary text-[10px] font-black px-2 py-0.5 rounded-full">
                {pagination.total_records || 0} Invoices
              </span>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center gap-4 text-xs font-semibold text-on-surface-variant">
              <div className="flex items-center gap-1.5">
                <span>Show</span>
                <select
                  value={limit}
                  onChange={(e) => { setPage(1); setLimit(parseInt(e.target.value)); }}
                  className="bg-white border border-outline rounded p-1 font-bold text-on-surface"
                >
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={250}>250</option>
                </select>
              </div>
            </div>
          </div>

          {/* Sticky-Header Universal Ledger Scroll Canvas */}
          <div className="overflow-x-auto max-h-[500px] relative">
            <table className="w-full text-left border-collapse table-fixed min-w-[1450px]">
              <thead className="sticky top-0 bg-surface-container z-10 border-b border-outline-variant shadow-xs">
                <tr>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase" style={{ width: '130px' }}><button className="uppercase hover:text-primary" onClick={() => toggleSort('date')}>Date & Time{sortMark('date')}</button></th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase" style={{ width: '120px' }}>Invoice ID</th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase" style={{ width: '200px' }}>Customer / Patient</th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase" style={{ width: '130px' }}>Bill Type</th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase" style={{ width: '120px' }}>Payment</th>

                  {/* Financial Columns - Right Aligned Tabular */}
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase text-right" style={{ width: '90px' }}>Gross</th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase text-right" style={{ width: '80px' }}>Discount</th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase text-right" style={{ width: '80px' }}>GST</th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase text-right" style={{ width: '100px' }}><button className="uppercase hover:text-primary" onClick={() => toggleSort('net_payable')}>Net Amount{sortMark('net_payable')}</button></th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase text-right" style={{ width: '100px' }}>Paid</th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase text-right" style={{ width: '100px' }}>Balance</th>

                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase text-center" style={{ width: '120px' }}>Status</th>
                  <th className="p-3 text-[10px] font-bold text-on-surface-variant uppercase" style={{ width: '130px' }}>Cashier</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/40 bg-white">
                {loading ? (
                  Array.from({ length: 5 }).map((_, idx) => (
                    <tr key={idx} className="animate-pulse">
                      <td className="p-3"><div className="h-4 bg-outline-variant/20 rounded"></div></td>
                      <td className="p-3" colSpan={12}><div className="h-8 bg-outline-variant/10 rounded w-full"></div></td>
                    </tr>
                  ))
                ) : invoices.length === 0 ? (
                  <tr>
                    <td colSpan={13} className="p-12 text-center text-xs font-bold text-outline italic">
                      No invoices found matching active filter configurations.
                    </td>
                  </tr>
                ) : (
                  invoices.map((inv) => {
                    const formattedDate = formatDate(inv.date);
                    const formattedTime = formatTime(inv.date);

                    return (
                      <tr
                        key={inv.id}
                        className={`hover:bg-primary-container/10 group transition-all duration-75 cursor-pointer`}
                      >
                        <td className="p-3 text-xs font-semibold text-on-surface" onClick={() => handleViewInvoice(inv.id)}>
                          <span>{formattedDate}</span>
                          <span className="text-[10px] text-outline block mt-0.5">{formattedTime}</span>
                        </td>

                        {/* Clickable invoice link ID */}
                        <td className="p-3 text-xs font-black text-primary hover:underline overflow-hidden" onClick={() => handleViewInvoice(inv.id)}>
                          {inv.id}
                        </td>

                        <td className="p-3 text-xs" onClick={() => handleViewInvoice(inv.id)}>
                          <div className="font-bold text-on-surface truncate">{inv.patient_name}</div>
                          <div className="text-[10px] text-outline truncate font-mono">{inv.patient_id || 'Walk-in'}</div>
                        </td>

                        <td className="p-3 text-xs" onClick={() => handleViewInvoice(inv.id)}>
                          <span className={`px-2 py-0.5 text-[9px] font-black uppercase tracking-wider rounded-md border ${getBadgeColors(inv.bill_type)}`}>
                            {inv.bill_type}
                          </span>
                        </td>

                        <td className="p-3 text-xs font-bold text-on-surface" onClick={() => handleViewInvoice(inv.id)}>
                          {inv.payment_method}
                        </td>

                        {/* Financial Columns - Right Aligned Monospace Tabular Figures */}
                        <td className="p-3 text-xs text-right font-mono font-bold text-on-surface-variant" onClick={() => handleViewInvoice(inv.id)}>
                          {formatINR(inv.gross_amount)}
                        </td>
                        <td className="p-3 text-xs text-right font-mono font-bold text-on-surface-variant" onClick={() => handleViewInvoice(inv.id)}>
                          {formatINR(inv.discount_applied)}
                        </td>
                        <td className="p-3 text-xs text-right font-mono font-bold text-on-surface-variant" onClick={() => handleViewInvoice(inv.id)}>
                          {formatINR(inv.tax_breakdown?.total_gst)}
                        </td>
                        <td className="p-3 text-xs text-right font-mono font-black text-primary" onClick={() => handleViewInvoice(inv.id)}>
                          {formatINR(inv.net_payable)}
                        </td>
                        <td className="p-3 text-xs text-right font-mono font-bold text-secondary" onClick={() => handleViewInvoice(inv.id)}>
                          {formatINR(inv.amount_paid)}
                        </td>
                        <td className="p-3 text-xs text-right font-mono font-bold text-error" onClick={() => handleViewInvoice(inv.id)}>
                          {formatINR(inv.balance_due)}
                        </td>

                        {/* Badge for payment status */}
                        <td className="p-3 text-center" onClick={() => handleViewInvoice(inv.id)}>
                          <span className={`px-2 py-0.5 text-[9px] font-black uppercase tracking-wider rounded-md border ${getBadgeColors(inv.status)}`}>
                            {inv.status}
                          </span>
                        </td>

                        {/* Cashier and Hover Actions */}
                        <td className="p-3 text-xs text-on-surface-variant relative group" onClick={() => handleViewInvoice(inv.id)}>
                          <span className="group-hover:opacity-0 transition-all font-semibold block">{inv.cashier_name}</span>

                          {/* Slide-in Row Actions on Hover */}
                          <div className="absolute inset-0 bg-surface-container-low group-hover:flex items-center justify-end px-2 gap-1.5 hidden animate-fade-in" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => handleViewInvoice(inv.id)}
                              className="p-1 hover:bg-primary/10 text-primary rounded"
                              title="View details"
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => window.open(`/api/billing/invoices/${inv.id}/pdf?tz_offset=${tzOffset}`, '_blank')}
                              className="p-1 hover:bg-primary/10 text-primary rounded"
                              title="Download PDF"
                            >
                              <Download className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleDuplicateInvoice(inv.id)}
                              className="p-1 hover:bg-primary/10 text-primary rounded"
                              title="Duplicate invoice"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </button>
                            {canRefund(inv) && (
                              <button
                                onClick={() => handleRefundInvoice(inv.id)}
                                className="p-1 hover:bg-error/10 text-error rounded"
                                title="Refund invoice"
                              >
                                <RotateCcw className="w-3.5 h-3.5" />
                              </button>
                            )}
                            {canCancel(inv) && (
                              <button
                                onClick={() => handleCancelInvoice(inv.id)}
                                className="p-1 hover:bg-error/10 text-error rounded"
                                title="Cancel invoice"
                              >
                                <Ban className="w-3.5 h-3.5" />
                              </button>
                            )}
                            <button
                              onClick={() => handleDeleteInvoice(inv.id)}
                              className="p-1 hover:bg-error/10 text-error rounded"
                              title="Delete permanently"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Totals over every matching invoice (cancelled ones excluded) */}
          {summaryTotals.net_total !== undefined && (
            <div className="px-4 py-2 border-t border-outline-variant bg-white flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-on-surface-variant font-semibold">
              <span>Net billed: <strong className="text-on-surface font-mono">{formatINR(summaryTotals.net_total)}</strong></span>
              <span>Collected: <strong className="text-on-surface font-mono">{formatINR(summaryTotals.paid_total)}</strong></span>
              <span>Refunded: <strong className="text-error font-mono">{formatINR(summaryTotals.refund_total)}</strong></span>
              <span>Due: <strong className="text-on-surface font-mono">{formatINR(summaryTotals.due_total)}</strong></span>
              {summaryTotals.cancelled_count > 0 && <span>{summaryTotals.cancelled_count} cancelled (excluded)</span>}
            </div>
          )}

          {/* Sticky Ledger Footer Pagination */}
          <div className="p-4 border-t border-outline-variant bg-surface-container-low flex flex-col sm:flex-row items-center justify-between gap-3 text-xs font-semibold text-on-surface-variant">
            <div>
              Showing {invoices.length > 0 ? (page - 1) * limit + 1 : 0} to {Math.min(page * limit, pagination.total_records || 0)} of {pagination.total_records || 0} transactions
            </div>

            <div className="flex items-center gap-1.5">
              <button
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="w-8 h-8 flex items-center justify-center border border-outline rounded-lg bg-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-surface-container transition-all"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <span className="px-3 font-bold text-on-surface">Page {page} of {pagination.total_pages || 1}</span>

              <button
                disabled={page >= (pagination.total_pages || 1)}
                onClick={() => setPage(page + 1)}
                className="w-8 h-8 flex items-center justify-center border border-outline rounded-lg bg-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-surface-container transition-all"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* ---------------- SECTION 4: CHARTS & ANALYTICS WIDGETS ---------------- */}
        {chartsData && <ChartsGrid chartsData={chartsData} />}

      </div>

      {/* ---------------- SLIDE-OUT INVOICE PREVIEW DRAWER ---------------- */}
      {isDrawerOpen && selectedInvoice && (
        <InvoiceDrawer
          invoice={selectedInvoice}
          onClose={() => setIsDrawerOpen(false)}
          onDownload={handlePrintDrawer}
          onRefund={handleRefundInvoice}
          onCancel={handleCancelInvoice}
          onDelete={handleDeleteInvoice}
        />
      )}

    </div>
  );
}
