import React, { useState } from 'react';
import { apiFetch, errorMessage } from '../../api';
import { notify } from '../../lib/notify';
import { invalidate } from '../../queries';

const INPUT = 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:ring-1 focus:ring-primary outline-none';

interface Props {
  medicines: any[];
  initialMedicineId?: string;
  onClose: () => void;
}

// Owns its form state, so typing here doesn't re-render the inventory table
export default function AddBatchModal({ medicines, initialMedicineId, onClose }: Props) {
  const [batch, setBatch] = useState<any>({
    medicine_id: initialMedicineId || medicines[0]?.id || '', batch_number: '', expiry_date: '',
    quantity_on_hand: 100, supplier_id: 'supp_01',
    location_code: 'Aisle 1, Shelf A', purchase_price: 10.0, mrp: 15.0,
  });
  const [saving, setSaving] = useState(false);
  const set = (field: string) => (e: React.ChangeEvent<any>) => setBatch({ ...batch, [field]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await apiFetch('/api/batches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...batch,
          quantity_on_hand: parseInt(batch.quantity_on_hand, 10),
          purchase_price: parseFloat(batch.purchase_price),
          mrp: parseFloat(batch.mrp),
        }),
      });
      if (res.ok) {
        await invalidate.stock();
        notify.success(`Batch ${batch.batch_number} added.`);
        onClose();
      } else {
        notify.error('Failed to add batch: ' + await errorMessage(res, 'unknown error'));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <form onSubmit={submit} className="bg-white border border-outline-variant max-w-md w-full rounded-xl overflow-hidden shadow-2xl flex flex-col">
        <div className="p-4 border-b border-outline-variant bg-surface flex justify-between items-center">
          <h3 className="font-bold text-on-surface text-sm">Replenish Medicine Batch</h3>
          <button type="button" className="text-on-surface-variant hover:text-on-surface font-bold" onClick={onClose}>✕</button>
        </div>
        <div className="p-5 space-y-4 text-xs font-semibold text-on-surface-variant">
          <div>
            <label className="block mb-1">Select Medication</label>
            <select className={INPUT} value={batch.medicine_id} onChange={set('medicine_id')}>
              {medicines.map(m => <option key={m.id} value={m.id}>{m.name} ({m.dosage})</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block mb-1">Batch Number</label>
              <input type="text" required className={`${INPUT} font-mono`} placeholder="e.g. #AUG302" value={batch.batch_number} onChange={set('batch_number')} />
            </div>
            <div>
              <label className="block mb-1">Expiry Date</label>
              <input type="date" required className={INPUT} value={batch.expiry_date} onChange={set('expiry_date')} />
            </div>
            <div>
              <label className="block mb-1">Quantity Received</label>
              <input type="number" min={0} required className={`${INPUT} font-mono`} value={batch.quantity_on_hand} onChange={set('quantity_on_hand')} />
            </div>
            <div>
              <label className="block mb-1">Location Code</label>
              <input type="text" required className={INPUT} placeholder="e.g. Aisle 2, Shelf D" value={batch.location_code} onChange={set('location_code')} />
            </div>
            <div>
              <label className="block mb-1">Purchase Price per unit (₹)</label>
              <input type="number" min={0} step="0.01" required className={`${INPUT} font-mono`} value={batch.purchase_price} onChange={set('purchase_price')} />
            </div>
            <div>
              <label className="block mb-1">MRP per unit (₹)</label>
              <input type="number" min={0.01} step="0.01" required className={`${INPUT} font-mono`} value={batch.mrp} onChange={set('mrp')} />
            </div>
          </div>
        </div>
        <div className="p-4 border-t border-outline-variant bg-surface-container-low flex justify-end gap-2 text-xs">
          <button type="button" className="px-4 py-2 border border-outline-variant rounded-lg font-bold hover:bg-surface-container" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={saving} className="px-4 py-2 bg-primary text-white font-bold rounded-lg hover:opacity-90 disabled:opacity-60">Replenish Stock</button>
        </div>
      </form>
    </div>
  );
}
