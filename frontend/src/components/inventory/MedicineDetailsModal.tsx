import { useMemo } from 'react';
import {
  MapPin,
  ShieldAlert,
  Sparkles
} from 'lucide-react';
import { formatDate } from '../../lib/format';
import { ExpiryBadge } from '../ui/StatusBadge';

interface Props {
  medicine: any;
  medicines: any[];
  batchesByMedicine: Map<string, any[]>;
  onClose: () => void;
}

export default function MedicineDetailsModal({ medicine, medicines, batchesByMedicine, onClose }: Props) {
  const batches = batchesByMedicine.get(medicine.id) || [];
  const substitutes = useMemo(() => {
    const salt = medicine.generic_name.toLowerCase();
    return medicines.filter(m => m.id !== medicine.id && m.generic_name.toLowerCase() === salt);
  }, [medicine, medicines]);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white border border-outline-variant max-w-4xl w-full rounded-xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
        <div className="p-5 border-b border-outline-variant bg-surface flex justify-between items-start">
          <div>
            <span className="text-[10px] font-bold text-primary uppercase tracking-widest">Medication profile</span>
            <h3 className="text-xl font-bold text-on-surface mt-1">{medicine.name}</h3>
            <p className="text-xs text-on-surface-variant font-mono">{medicine.generic_name} • {medicine.dosage}</p>
          </div>
          <button className="text-on-surface-variant hover:text-on-surface font-bold text-lg" onClick={onClose}>✕</button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-4 md:col-span-1 border-r border-outline-variant pr-6">
              <div>
                <h5 className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider mb-1">Clinical Details</h5>
                <div className="bg-surface-container-low p-3 rounded-lg space-y-2 text-xs text-on-surface-variant font-semibold">
                  <div><span className="font-normal block">Manufacturer:</span><span className="text-on-surface">{medicine.manufacturer}</span></div>
                  <div><span className="font-normal block">Dosage Form:</span><span className="text-on-surface">{medicine.form}</span></div>
                  <div><span className="font-normal block">Storage Condition:</span><span className="text-on-surface">{medicine.storage_requirement}</span></div>
                  <div><span className="font-normal block">UOM Packaging:</span><span className="text-on-surface">{medicine.base_uom} unit</span></div>
                </div>
              </div>
              <div>
                <h5 className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider mb-1">Clinical Warnings</h5>
                <div className="bg-error-container/20 border border-error/15 p-3 rounded-lg text-xs font-semibold text-error flex gap-2">
                  <ShieldAlert className="w-4 h-4 shrink-0 text-error" />
                  <p className="leading-tight">{medicine.side_effects}</p>
                </div>
              </div>
            </div>

            <div className="md:col-span-2 space-y-4">
              <h5 className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider">Active Batch Breakdown</h5>
              <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
                {batches.map(batch => (
                  <div key={batch.id} className="border border-outline-variant p-3 rounded-lg bg-surface-container-lowest hover:border-primary/40 transition-colors flex justify-between items-center text-xs">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold font-mono text-on-surface text-sm">Batch #{batch.batch_number}</span>
                        <ExpiryBadge status={batch.expiry_status} />
                      </div>
                      <p className="text-[10px] text-on-surface-variant flex items-center gap-1 font-semibold">
                        <MapPin className="w-3.5 h-3.5 text-outline" /> shelf: {batch.location_code} | Expiry: {formatDate(batch.expiry_date)}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="font-mono text-base font-black text-on-surface block leading-tight">{batch.quantity_on_hand}</span>
                      <span className="text-[9px] text-on-surface-variant uppercase font-bold">In stock</span>
                    </div>
                  </div>
                ))}
                {batches.length === 0 && (
                  <div className="text-center p-6 text-on-surface-variant border border-dashed border-outline-variant rounded-lg">No stock batch logs recorded. Use restock.</div>
                )}
              </div>
            </div>
          </div>

          <div className="border-t border-outline-variant pt-5 space-y-3">
            <h4 className="font-bold text-on-surface text-sm flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-primary" /> Active generic salt alternatives (Substitutes)
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {substitutes.map(sub => (
                <div key={sub.id} className="border border-outline-variant rounded-lg p-3 bg-surface-container-low hover:bg-surface-container flex justify-between items-center">
                  <div>
                    <span className="font-bold text-primary text-xs">{sub.name}</span>
                    <p className="text-[10px] text-on-surface-variant">{sub.manufacturer} • {sub.dosage}</p>
                  </div>
                  <span className="text-xs font-bold text-on-surface font-mono">{sub.total_stock} in stock</span>
                </div>
              ))}
              {substitutes.length === 0 && (
                <div className="text-xs text-on-surface-variant italic p-2 md:col-span-2">No other medications matched generic salt "{medicine.generic_name}".</div>
              )}
            </div>
          </div>
        </div>

        <div className="p-4 border-t border-outline-variant bg-surface-container-low flex justify-end gap-2">
          <button className="px-4 py-2 border border-outline-variant rounded-lg text-xs font-bold hover:bg-surface-container text-on-surface" onClick={onClose}>
            Close View
          </button>
        </div>
      </div>
    </div>
  );
}
