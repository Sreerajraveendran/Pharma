import React, { useState, useEffect } from 'react';
import { apiFetch, errorMessage } from '../../api';
import { Plus, Trash, FileText } from 'lucide-react';
import { notify } from '../../lib/notify';
import { invalidate, useMedicines, usePatients } from '../../queries';

interface NewPrescriptionModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function NewPrescriptionModal({ isOpen, onClose }: NewPrescriptionModalProps) {
  const { data: patients = [] } = usePatients();
  const { data: medicines = [] } = useMedicines();

  const [patientId, setPatientId] = useState('');
  const [prescribedBy, setPrescribedBy] = useState('Dr. Sarah Jenkins');
  const [prescriptionLines, setPrescriptionLines] = useState<any[]>([
    { medicine_id: '', dosage_instruction: '1 tablet twice daily after meals', duration_days: 7, quantity_prescribed: 14 }
  ]);

  // Default the selections once the (cached) lists are available
  useEffect(() => {
    if (!patientId && patients.length > 0) setPatientId(patients[0].id);
  }, [patients, patientId]);
  useEffect(() => {
    if (medicines.length > 0) {
      setPrescriptionLines(lines => lines.map(l => (l.medicine_id ? l : { ...l, medicine_id: medicines[0].id })));
    }
  }, [medicines]);

  const addLine = () => {
    setPrescriptionLines([
      ...prescriptionLines,
      { medicine_id: medicines[0]?.id || '', dosage_instruction: '1 tablet daily after breakfast', duration_days: 10, quantity_prescribed: 10 }
    ]);
  };

  const removeLine = (idx: number) => {
    if (prescriptionLines.length === 1) return;
    setPrescriptionLines(prescriptionLines.filter((_, i) => i !== idx));
  };

  const updateLine = (idx: number, field: string, value: any) => {
    setPrescriptionLines(prescriptionLines.map((line, i) => {
      if (i === idx) {
        return { ...line, [field]: value };
      }
      return line;
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!patientId) {
      notify.error("Please select a patient.");
      return;
    }

    const prescriptionData = {
      patient_id: patientId,
      prescribed_by: prescribedBy,
      status: 'Active',
      medicines: prescriptionLines.map(line => ({
        medicine_id: line.medicine_id,
        dosage_instruction: line.dosage_instruction,
        duration_days: parseInt(line.duration_days),
        quantity_prescribed: parseInt(line.quantity_prescribed),
        dispensed_quantity: 0
      }))
    };

  	try {
      const res = await apiFetch('/api/prescriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(prescriptionData)
      });
      if (res.ok) {
        invalidate.prescriptions();
        notify.success("Prescription created.");
        onClose();
      } else {
        notify.error("Failed to create prescription: " + await errorMessage(res, "unknown error"));
      }
    } catch (err) {
      console.error(err);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <form onSubmit={handleSubmit} className="bg-white border border-outline-variant max-w-2xl w-full rounded-xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
        
        {/* Header */}
        <div className="p-4 border-b border-outline-variant bg-surface flex justify-between items-center">
          <h3 className="font-bold text-on-surface text-sm flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary" /> Create New Prescription
          </h3>
          <button type="button" className="text-on-surface-variant hover:text-on-surface font-bold" onClick={onClose}>✕</button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1 text-xs font-semibold text-on-surface-variant">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block mb-1">Select Patient Profile</label>
              <select 
                className="w-full h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg outline-none"
                value={patientId} 
                onChange={e => setPatientId(e.target.value)}
              >
                {patients.map(p => (
                  <option key={p.id} value={p.id}>{p.name} ({p.phone})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block mb-1">Prescribing Doctor</label>
              <input 
                type="text" 
                required 
                className="w-full h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg outline-none text-on-surface font-bold" 
                value={prescribedBy} 
                onChange={e => setPrescribedBy(e.target.value)} 
              />
            </div>
          </div>

          <div className="border-t border-outline-variant pt-4 space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-[10px] font-bold text-on-surface uppercase tracking-wider">Prescribed Medication Lines</span>
              <button 
                type="button" 
                className="h-7 px-3 bg-primary text-white rounded font-bold flex items-center gap-1 hover:bg-primary-container text-[10px]"
                onClick={addLine}
              >
                <Plus className="w-3.5 h-3.5" /> Add Drug
              </button>
            </div>

            <div className="space-y-3">
              {prescriptionLines.map((line, idx) => (
                <div key={idx} className="border border-outline-variant p-3 rounded-lg bg-surface-container-low space-y-3 relative">
                  {prescriptionLines.length > 1 && (
                    <button 
                      type="button" 
                      className="absolute top-2 right-2 text-on-surface-variant hover:text-error"
                      onClick={() => removeLine(idx)}
                    >
                      <Trash className="w-4 h-4" />
                    </button>
                  )}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                    <div className="md:col-span-2">
                      <label className="block mb-1">Select Medication</label>
                      <select 
                        className="w-full h-9 px-2 bg-white border border-outline-variant rounded outline-none"
                        value={line.medicine_id} 
                        onChange={e => updateLine(idx, 'medicine_id', e.target.value)}
                      >
                        {medicines.map(m => (
                          <option key={m.id} value={m.id}>{m.name} ({m.dosage})</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block mb-1">Duration (days)</label>
                      <input 
                        type="number" 
                        required 
                        className="w-full h-9 px-2 bg-white border border-outline-variant rounded outline-none font-mono" 
                        value={line.duration_days} 
                        onChange={e => updateLine(idx, 'duration_days', e.target.value)} 
                      />
                    </div>
                    <div>
                      <label className="block mb-1">Total Quantity</label>
                      <input 
                        type="number" 
                        required 
                        className="w-full h-9 px-2 bg-white border border-outline-variant rounded outline-none font-mono" 
                        value={line.quantity_prescribed} 
                        onChange={e => updateLine(idx, 'quantity_prescribed', e.target.value)} 
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block mb-1">Dosage Instructions</label>
                    <input 
                      type="text" 
                      required 
                      className="w-full h-9 px-3 bg-white border border-outline-variant rounded outline-none font-medium text-on-surface italic" 
                      value={line.dosage_instruction} 
                      onChange={e => updateLine(idx, 'dosage_instruction', e.target.value)} 
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-outline-variant bg-surface-container-low flex justify-end gap-2 text-xs">
          <button type="button" className="px-4 py-2 border border-outline-variant rounded-lg font-bold hover:bg-surface-container" onClick={onClose}>Cancel</button>
          <button type="submit" className="px-4 py-2 bg-secondary text-white font-bold rounded-lg hover:opacity-90">Issue Prescription</button>
        </div>
      </form>
    </div>
  );
}
