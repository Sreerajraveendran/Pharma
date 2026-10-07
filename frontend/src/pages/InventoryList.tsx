import React, { useMemo, useState } from 'react';
import { ChevronRight, Plus, Search, Warehouse } from 'lucide-react';
import { useBatches, useCategories, useMedicines } from '../queries';
import AddBatchModal from '../components/inventory/AddBatchModal';
import AddMedicineModal from '../components/inventory/AddMedicineModal';
import MedicineDetailsModal from '../components/inventory/MedicineDetailsModal';
import { ExpiryBadge, StockBadge } from '../components/ui/StatusBadge';

const PAGE = 100;

export default function InventoryList() {
  const { data: medicines = [] } = useMedicines();
  const { data: categories = [] } = useCategories();
  const { data: batches = [] } = useBatches();

  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [stockFilter, setStockFilter] = useState('');
  const [expiryFilter, setExpiryFilter] = useState('');
  const [visible, setVisible] = useState(PAGE);

  const [selectedMedId, setSelectedMedId] = useState<string | null>(null);
  const [isAddMedOpen, setIsAddMedOpen] = useState(false);
  const [isAddBatchOpen, setIsAddBatchOpen] = useState(false);

  // Always read the selected medicine from the latest data, so it refreshes after a restock
  const selectedMed = useMemo(() => medicines.find((m: any) => m.id === selectedMedId) || null,
    [medicines, selectedMedId]);

  const batchesByMedicine = useMemo(() => {
    const map = new Map<string, any[]>();
    for (const b of batches) {
      const list = map.get(b.medicine_id);
      if (list) list.push(b); else map.set(b.medicine_id, [b]);
    }
    return map;
  }, [batches]);

  const filteredMeds = useMemo(() => {
    const q = search.toLowerCase();
    return medicines.filter((med: any) =>
      (med.name.toLowerCase().includes(q) || med.generic_name.toLowerCase().includes(q)) &&
      (!categoryFilter || med.category_id === categoryFilter) &&
      (!stockFilter || med.stock_level_status === stockFilter) &&
      (!expiryFilter || med.expiry_status === expiryFilter));
  }, [medicines, search, categoryFilter, stockFilter, expiryFilter]);

  const filterChange = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setter(e.target.value);
    setVisible(PAGE);
  };

  return (
    <div className="flex-1 flex overflow-hidden max-h-[calc(100vh-64px)]">
      <div className="flex-1 flex flex-col min-w-0 bg-background p-6 space-y-4">
        {/* Header Action Bar */}
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-2xl font-bold text-on-surface tracking-tight">Intelligent Medicine Listing</h2>
            <p className="text-sm text-on-surface-variant">Manage enterprise-wide pharmaceutical stock and regulatory compliance.</p>
          </div>
          <div className="flex gap-2">
            <button
              className="h-10 px-4 bg-primary text-white rounded-lg text-sm font-bold flex items-center gap-2 hover:bg-primary-container shadow-sm active:scale-95 transition-all"
              onClick={() => setIsAddMedOpen(true)}
            >
              <Plus className="w-4 h-4" /> Add Medication
            </button>
            <button
              className="h-10 px-4 bg-secondary text-white rounded-lg text-sm font-bold flex items-center gap-2 hover:opacity-90 shadow-sm active:scale-95 transition-all"
              onClick={() => setIsAddBatchOpen(true)}
            >
              <Warehouse className="w-4 h-4" /> Add Batch (Restock)
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="bg-surface-container-lowest border border-outline-variant p-4 rounded-xl flex flex-wrap gap-4 items-center">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-outline h-4 w-4" />
            <input
              type="text"
              className="w-full pl-10 pr-4 h-9 bg-surface-container-low border border-outline-variant rounded-lg text-xs focus:ring-2 focus:ring-primary focus:outline-none"
              placeholder="Search by brand name or generic active salt..."
              value={search}
              onChange={filterChange(setSearch)}
            />
          </div>
          <div className="flex gap-2 flex-wrap text-xs">
            <select
              className="h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary"
              value={categoryFilter}
              onChange={filterChange(setCategoryFilter)}
            >
              <option value="">All Categories</option>
              {categories.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select
              className="h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary"
              value={stockFilter}
              onChange={filterChange(setStockFilter)}
            >
              <option value="">All Stock Levels</option>
              <option value="OPTIMAL">Optimal</option>
              <option value="LOW">Low Stock</option>
              <option value="OUT_OF_STOCK">Out of Stock</option>
            </select>
            <select
              className="h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary"
              value={expiryFilter}
              onChange={filterChange(setExpiryFilter)}
            >
              <option value="">All Expiry Statuses</option>
              <option value="HEALTHY">Healthy</option>
              <option value="WARNING">Warning (&lt; 180d)</option>
              <option value="CRITICAL">Critical (&lt; 30d)</option>
            </select>
          </div>
        </div>

        {/* High Density Table */}
        <div className="flex-1 border border-outline-variant rounded-xl overflow-hidden bg-surface-container-lowest flex flex-col">
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="sticky top-0 bg-surface-container-high border-b border-outline-variant text-[11px] font-bold text-on-surface-variant uppercase tracking-wider select-none z-10">
                  <th className="p-3">Medication Details</th>
                  <th className="p-3">Generic Salt</th>
                  <th className="p-3">Category</th>
                  <th className="p-3 text-right">Total Stock</th>
                  <th className="p-3">Stock Level</th>
                  <th className="p-3">Expiry Warning</th>
                  <th className="p-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant text-xs text-on-surface font-medium zebra-table">
                {filteredMeds.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-6 text-center text-on-surface-variant font-semibold">No medicines match current search.</td>
                  </tr>
                ) : (
                  filteredMeds.slice(0, visible).map((med: any) => (
                    <tr
                      key={med.id}
                      className="hover:bg-primary/5 cursor-pointer transition-colors"
                      onClick={() => setSelectedMedId(med.id)}
                    >
                      <td className="p-3">
                        <div className="font-bold text-primary">{med.name}</div>
                        <div className="text-[10px] text-on-surface-variant mt-0.5">{med.form} • {med.dosage}</div>
                      </td>
                      <td className="p-3 font-mono text-[11px] text-on-surface-variant max-w-[200px] truncate" title={med.generic_name}>
                        {med.generic_name}
                      </td>
                      <td className="p-3">
                        <span
                          className="px-2 py-0.5 rounded text-[10px] font-bold border"
                          style={{
                            borderColor: med.category?.color_code + '40',
                            backgroundColor: med.category?.color_code + '15',
                            color: med.category?.color_code
                          }}
                        >
                          {med.category?.name || "Uncategorized"}
                        </span>
                      </td>
                      <td className="p-3 text-right font-mono text-[13px] font-bold select-all">
                        {med.total_stock} <span className="text-[9px] text-on-surface-variant font-normal">{med.base_uom}s</span>
                      </td>
                      <td className="p-3"><StockBadge status={med.stock_level_status} /></td>
                      <td className="p-3"><ExpiryBadge status={med.expiry_status} /></td>
                      <td className="p-3 text-center">
                        <button className="p-1 rounded hover:bg-surface-container-high border border-outline-variant text-on-surface" aria-label={`Open ${med.name}`}>
                          <ChevronRight className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            {filteredMeds.length > visible && (
              <button
                className="w-full p-3 text-xs font-bold text-primary hover:bg-surface-container-low border-t border-outline-variant"
                onClick={() => setVisible(v => v + PAGE)}
              >
                Show more ({filteredMeds.length - visible} remaining)
              </button>
            )}
          </div>
        </div>
      </div>

      {selectedMed && (
        <MedicineDetailsModal
          medicine={selectedMed}
          medicines={medicines}
          batchesByMedicine={batchesByMedicine}
          onClose={() => setSelectedMedId(null)}
        />
      )}
      {isAddMedOpen && <AddMedicineModal categories={categories} onClose={() => setIsAddMedOpen(false)} />}
      {isAddBatchOpen && (
        <AddBatchModal
          medicines={medicines}
          initialMedicineId={selectedMed?.id}
          onClose={() => setIsAddBatchOpen(false)}
        />
      )}
    </div>
  );
}
