import React, { useMemo, useState } from 'react';
import { apiFetch, errorMessage } from '../api';
import { notify } from '../lib/notify';
import { invalidate, usePatientPrescriptions, usePatients } from '../queries';
import {
  Plus,
  Search,
  UserPlus,
  FileText,
  AlertTriangle,
  Phone,
  Mail,
  CalendarDays
} from 'lucide-react';

const PAGE = 100;

export default function PatientsList() {
  const { data: patients = [] } = usePatients();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedPat = useMemo(
    () => patients.find((p: any) => p.id === selectedId) || patients[0] || null,
    [patients, selectedId]
  );
  // Only the selected patient's prescriptions are fetched
  const { data: patientRx = [] } = usePatientPrescriptions(selectedPat?.id);

  const [search, setSearch] = useState('');
  const [visible, setVisible] = useState(PAGE);
  const [isAddPatOpen, setIsAddPatOpen] = useState(false);

  // Register Patient form state
  const [newPat, setNewPat] = useState<any>({
    name: '', phone: '', email: '', date_of_birth: '', allergies: ''
  });

  const handleAddPatient = async (e: React.FormEvent) => {
    e.preventDefault();
    // Parse allergies list
    const allergiesList = newPat.allergies
      ? newPat.allergies.split(',').map((s: string) => s.trim()).filter((s: string) => s.length > 0)
      : [];

    const patientData = {
      name: newPat.name,
      phone: newPat.phone,
      email: newPat.email,
      date_of_birth: newPat.date_of_birth,
      allergies: allergiesList
    };

    try {
      const res = await apiFetch('/api/patients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patientData)
      });
      if (res.ok) {
        const created = await res.json();
        setIsAddPatOpen(false);
        setNewPat({ name: '', phone: '', email: '', date_of_birth: '', allergies: '' });
        await invalidate.patients();
        setSelectedId(created.id);
        notify.success(`Registered ${created.name}.`);
      } else {
        notify.error("Failed to register patient: " + await errorMessage(res, "unknown error"));
      }
    } catch (err) {
      console.error(err);
    }
  };

  const filteredPatients = useMemo(() => {
    const q = search.toLowerCase();
    return patients.filter((p: any) => p.name.toLowerCase().includes(q) || p.phone.includes(search));
  }, [patients, search]);
  return (
    <div className="flex-1 flex overflow-hidden max-h-[calc(100vh-64px)]">
      {/* Left panel: Patient profiles list */}
      <div className="w-[340px] border-r border-outline-variant flex flex-col bg-surface-container-lowest shrink-0">
        <div className="p-4 border-b border-outline-variant space-y-3">
          <div className="flex justify-between items-center">
            <h3 className="font-bold text-on-surface text-sm uppercase tracking-wider">Patient Registry</h3>
            <button 
              className="p-1.5 bg-primary text-white rounded-lg text-xs font-bold flex items-center gap-1 hover:bg-primary-container"
              onClick={() => setIsAddPatOpen(true)}
            >
              <Plus className="w-3.5 h-3.5" /> New Patient
            </button>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-outline h-3.5 w-3.5" />
            <input 
              type="text" 
              className="w-full pl-9 pr-3 h-8 bg-surface-container-low border border-outline-variant rounded-lg text-xs focus:ring-1 focus:ring-primary outline-none"
              placeholder="Search directory..."
              value={search}
              onChange={e => { setSearch(e.target.value); setVisible(PAGE); }}
            />
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto divide-y divide-outline-variant">
          {filteredPatients.slice(0, visible).map((p: any) => (
            <div 
              key={p.id}
              className={`p-4 cursor-pointer hover:bg-surface-container-low transition-colors space-y-1 ${selectedPat?.id === p.id ? 'bg-primary/5 border-l-4 border-primary' : ''}`}
              onClick={() => setSelectedId(p.id)}
            >
              <div className="flex justify-between items-start">
                <span className="font-bold text-on-surface text-sm">{p.name}</span>
                {p.allergies.length > 0 && (
                  <span className="px-1.5 py-0.5 text-[9px] rounded bg-error-container text-error font-bold uppercase">
                    Allergies
                  </span>
                )}
              </div>
              <p className="text-xs text-on-surface-variant font-mono">{p.phone}</p>
            </div>
          ))}
          {filteredPatients.length > visible && (
            <button
              className="w-full p-3 text-xs font-bold text-primary hover:bg-surface-container-low"
              onClick={() => setVisible(v => v + PAGE)}
            >
              Show more ({filteredPatients.length - visible} remaining)
            </button>
          )}
          {filteredPatients.length === 0 && (
            <div className="text-center p-6 text-xs text-on-surface-variant">No patients registered.</div>
          )}
        </div>
      </div>

      {/* Right panel: Active patient 360° clinical summary */}
      <div className="flex-1 flex flex-col min-w-0 bg-background overflow-y-auto p-6 space-y-6">
        {selectedPat ? (
          <>
            {/* Demographics Summary Card */}
            <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5 space-y-4">
              <div className="flex justify-between items-start border-b border-outline-variant pb-4">
                <div>
                  <span className="text-[10px] font-bold text-primary uppercase tracking-widest">Patient Profile</span>
                  <h2 className="text-xl font-bold text-on-surface mt-0.5">{selectedPat.name}</h2>
                </div>
                <div className="flex gap-4 text-xs font-semibold text-on-surface-variant">
                  <div className="flex items-center gap-1.5"><Phone className="w-4 h-4 text-outline" /> {selectedPat.phone}</div>
                  <div className="flex items-center gap-1.5"><Mail className="w-4 h-4 text-outline" /> {selectedPat.email}</div>
                  <div className="flex items-center gap-1.5"><CalendarDays className="w-4 h-4 text-outline" /> DoB: {selectedPat.date_of_birth}</div>
                </div>
              </div>

              {/* Allergy flags */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-on-surface-variant uppercase">Allergies:</span>
                {selectedPat.allergies.length > 0 ? (
                  selectedPat.allergies.map((a: string, idx: number) => (
                    <span key={idx} className="px-2 py-0.5 rounded text-xs bg-error-container text-error font-bold border border-error/20 flex items-center gap-1">
                      <AlertTriangle className="w-3.5 h-3.5" /> {a}
                    </span>
                  ))
                ) : (
                  <span className="px-2 py-0.5 rounded text-xs bg-secondary-container text-secondary font-bold border border-secondary/20">
                    No Known Drug Allergies (NKDA)
                  </span>
                )}
              </div>
            </div>

            {/* Prescription History log */}
            <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5 space-y-4">
              <div>
                <h3 className="font-semibold text-on-surface">Prescription Log</h3>
                <p className="text-xs text-on-surface-variant">History of clinical directions issued for this patient</p>
              </div>

              <div className="space-y-4">
                {patientRx.map((rx: any) => (
                  <div key={rx.id} className="border border-outline-variant rounded-lg overflow-hidden bg-white">
                    <div className="bg-surface-container-low px-4 py-3 border-b border-outline-variant flex justify-between items-center text-xs">
                      <div>
                        <span className="font-bold text-on-surface">Prescription ID: <span className="font-mono text-primary select-all">{rx.id}</span></span>
                        <p className="text-[10px] text-on-surface-variant mt-0.5">Issued by {rx.prescribed_by} on {new Date(rx.date_issued).toLocaleDateString()}</p>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${rx.status === 'Active' ? 'bg-primary-container/20 text-primary border-primary/20 animate-pulse' : 'bg-secondary-container text-secondary border-secondary/20'}`}>
                        {rx.status}
                      </span>
                    </div>
                    <div className="p-4 overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b border-outline-variant text-[10px] font-bold text-on-surface-variant uppercase select-none pb-2">
                            <th className="pb-2">Medicine Details</th>
                            <th className="pb-2">Dosage Instructions</th>
                            <th className="pb-2 text-right">Prescribed</th>
                            <th className="pb-2 text-right">Dispensed</th>
                            <th className="pb-2 text-right">Refills Left</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-outline-variant text-on-surface font-semibold">
                          {rx.medicines.map((m: any, mIdx: number) => (
                            <tr key={mIdx} className="hover:bg-surface-container/10">
                              <td className="py-2 text-primary">{m.medicine_name} <span className="text-[10px] text-on-surface-variant font-normal">({m.dosage})</span></td>
                              <td className="py-2 italic text-on-surface-variant font-medium">{m.dosage_instruction} ({m.duration_days} days)</td>
                              <td className="py-2 text-right font-mono">{m.quantity_prescribed}</td>
                              <td className="py-2 text-right font-mono text-secondary">{m.dispensed_quantity}</td>
                              <td className="py-2 text-right font-mono text-error">
                                {m.quantity_prescribed - m.dispensed_quantity}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
                {patientRx.length === 0 && (
                  <div className="text-center p-8 border border-dashed border-outline-variant rounded-lg text-xs text-on-surface-variant flex flex-col items-center gap-2 opacity-65">
                    <FileText className="w-8 h-8 text-outline" />
                    <p className="font-semibold">No prescriptions registered for this patient.</p>
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-on-surface-variant opacity-60 flex-col gap-2">
            <UserPlus className="w-10 h-10 text-outline" />
            <p className="text-sm font-semibold">Select a patient from the list to view profile details</p>
          </div>
        )}
      </div>

      {/* Register Patient Modal */}
      {isAddPatOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <form onSubmit={handleAddPatient} className="bg-white border border-outline-variant max-w-sm w-full rounded-xl overflow-hidden shadow-2xl flex flex-col">
            <div className="p-4 border-b border-outline-variant bg-surface flex justify-between items-center">
              <h3 className="font-bold text-on-surface text-sm">Register New Patient</h3>
              <button type="button" className="text-on-surface-variant hover:text-on-surface font-bold" onClick={() => setIsAddPatOpen(false)}>✕</button>
            </div>
            <div className="p-5 space-y-4 text-xs font-semibold text-on-surface-variant">
              <div>
                <label className="block mb-1">Full Name</label>
                <input type="text" required className="w-full h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:ring-1 focus:ring-primary outline-none text-on-surface font-bold" value={newPat.name} onChange={e => setNewPat({...newPat, name: e.target.value})} />
              </div>
              <div>
                <label className="block mb-1">Contact Phone</label>
                <input type="text" required className="w-full h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:ring-1 focus:ring-primary outline-none font-mono" placeholder="e.g. +1 555-0199" value={newPat.phone} onChange={e => setNewPat({...newPat, phone: e.target.value})} />
              </div>
              <div>
                <label className="block mb-1">Email Address</label>
                <input type="email" className="w-full h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:ring-1 focus:ring-primary outline-none" placeholder="e.g. email@example.com" value={newPat.email} onChange={e => setNewPat({...newPat, email: e.target.value})} />
              </div>
              <div>
                <label className="block mb-1">Date of Birth</label>
                <input type="date" required className="w-full h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:ring-1 focus:ring-primary outline-none" value={newPat.date_of_birth} onChange={e => setNewPat({...newPat, date_of_birth: e.target.value})} />
              </div>
              <div>
                <label className="block mb-1">Known Drug Allergies (comma separated)</label>
                <input type="text" className="w-full h-9 px-3 bg-surface-container-low border border-outline-variant rounded-lg focus:ring-1 focus:ring-primary outline-none" placeholder="e.g. Penicillin, Sulfa" value={newPat.allergies} onChange={e => setNewPat({...newPat, allergies: e.target.value})} />
                <span className="text-[10px] text-outline mt-1 block">Warnings will display automatically in checkout cart.</span>
              </div>
            </div>
            <div className="p-4 border-t border-outline-variant bg-surface-container-low flex justify-end gap-2 text-xs">
              <button type="button" className="px-4 py-2 border border-outline-variant rounded-lg font-bold hover:bg-surface-container" onClick={() => setIsAddPatOpen(false)}>Cancel</button>
              <button type="submit" className="px-4 py-2 bg-primary text-white font-bold rounded-lg hover:opacity-90">Register Profile</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
