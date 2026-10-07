import React, { useState } from 'react';
import { apiFetch, errorMessage } from '../../api';
import { notify } from '../../lib/notify';
import { invalidate } from '../../queries';

const INPUT = 'w-full h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:ring-1 focus:ring-primary outline-none';

interface Props {
  categories: any[];
  onClose: () => void;
}

// Owns its form state, so typing here doesn't re-render the inventory table
export default function AddMedicineModal({ categories, onClose }: Props) {
  const [med, setMed] = useState<any>({
    name: '', generic_name: '', form: 'Tablet', dosage: '',
    category_id: categories[0]?.id || '', manufacturer: '', prescription_required: false,
    storage_requirement: '', side_effects: '', min_stock_level: 50, base_uom: 'Strip',
  });
  const [saving, setSaving] = useState(false);
  const set = (field: string) => (e: React.ChangeEvent<any>) =>
    setMed({ ...med, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await apiFetch('/api/medicines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...med, min_stock_level: parseInt(med.min_stock_level, 10) || 0 }),
      });
      if (res.ok) {
        await invalidate.catalog();
        notify.success(`Added ${med.name}.`);
        onClose();
      } else {
        notify.error('Failed to add medicine: ' + await errorMessage(res, 'unknown error'));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <form onSubmit={submit} className="bg-white border border-outline-variant max-w-lg w-full rounded-xl overflow-hidden shadow-2xl flex flex-col">
        <div className="p-4 border-b border-outline-variant bg-surface flex justify-between items-center">
          <h3 className="font-bold text-on-surface text-sm">Add New Medicine SKU</h3>
          <button type="button" className="text-on-surface-variant hover:text-on-surface font-bold" onClick={onClose}>✕</button>
        </div>
        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <div className="grid grid-cols-2 gap-4 text-xs font-semibold text-on-surface-variant">
            <div className="col-span-2">
              <label className="block mb-1">Brand Name (e.g. Augmentin 625 Duo)</label>
              <input type="text" required className={INPUT} value={med.name} onChange={set('name')} />
            </div>
            <div className="col-span-2">
              <label className="block mb-1">Generic / Active Salt Formulation</label>
              <input type="text" required className={INPUT} value={med.generic_name} onChange={set('generic_name')} />
            </div>
            <div>
              <label className="block mb-1">Form</label>
              <select className={INPUT} value={med.form} onChange={set('form')}>
                <option>Tablet</option>
                <option>Syrup</option>
                <option>Injection</option>
                <option>Inhaler</option>
                <option>Gel</option>
              </select>
            </div>
            <div>
              <label className="block mb-1">Dosage Specification</label>
              <input type="text" required className={INPUT} placeholder="e.g. 625mg / 100mcg" value={med.dosage} onChange={set('dosage')} />
            </div>
            <div>
              <label className="block mb-1">Category Group</label>
              <select className={INPUT} value={med.category_id} onChange={set('category_id')}>
                {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block mb-1">Manufacturer</label>
              <input type="text" required className={INPUT} value={med.manufacturer} onChange={set('manufacturer')} />
            </div>
            <div>
              <label className="block mb-1">Minimum Alert level</label>
              <input type="number" min={0} className={INPUT} value={med.min_stock_level} onChange={set('min_stock_level')} />
            </div>
            <div>
              <label className="block mb-1">Packaging UOM</label>
              <input type="text" className={INPUT} value={med.base_uom} onChange={set('base_uom')} />
            </div>
            <div className="col-span-2">
              <label className="block mb-1">Storage Conditions</label>
              <input type="text" className={INPUT} placeholder="e.g. Store below 25C" value={med.storage_requirement} onChange={set('storage_requirement')} />
            </div>
            <div className="col-span-2">
              <label className="block mb-1">Side Effects &amp; Clinical Warnings</label>
              <textarea rows={2} className="w-full p-2 bg-surface-container-low border border-outline-variant rounded-lg focus:ring-1 focus:ring-primary outline-none" placeholder="Allergies and interaction warnings" value={med.side_effects} onChange={set('side_effects')} />
            </div>
            <div className="col-span-2 flex items-center gap-2 py-2">
              <input type="checkbox" id="rx_req" checked={med.prescription_required} onChange={set('prescription_required')} />
              <label htmlFor="rx_req" className="font-bold cursor-pointer">Prescription mandatory (Schedule H regulation)</label>
            </div>
          </div>
        </div>
        <div className="p-4 border-t border-outline-variant bg-surface-container-low flex justify-end gap-2 text-xs">
          <button type="button" className="px-4 py-2 border border-outline-variant rounded-lg font-bold hover:bg-surface-container" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={saving} className="px-4 py-2 bg-primary text-white font-bold rounded-lg hover:opacity-90 disabled:opacity-60">Create SKU</button>
        </div>
      </form>
    </div>
  );
}
