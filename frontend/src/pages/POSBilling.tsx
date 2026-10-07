import { useEffect, useMemo, useState } from 'react';
import { apiFetch, errorMessage } from '../api';
import { notify } from '../lib/notify';
import { invalidate, useBatches, useMedicines, usePatientPrescriptions, usePatients } from '../queries';
import {
  Search,
  ShoppingCart,
  User,
  AlertTriangle,
  Trash2,
  Plus,
  Minus,
  CreditCard,
  CheckCircle,
  FileSpreadsheet,
  Download,
  Printer
} from 'lucide-react';

export default function POSBilling() {
  const { data: patients = [] } = usePatients();
  const { data: medicines = [] } = useMedicines();
  const { data: batches = [] } = useBatches();

  const [selectedPatientId, setSelectedPatientId] = useState('');
  const selectedPatient = useMemo(() => patients.find((p: any) => p.id === selectedPatientId) || null,
    [patients, selectedPatientId]);
  const { data: patientRx = [] } = usePatientPrescriptions(selectedPatientId || null);
  const prescriptions = useMemo(() => patientRx.filter((rx: any) => rx.status === 'Active'), [patientRx]);
  const [selectedPrescriptionId, setSelectedPrescriptionId] = useState('');

  const [searchQuery, setSearchQuery] = useState('');
  const [cart, setCart] = useState<any[]>([]);
  const [discountPercent, setDiscountPercent] = useState<any>(0);
  const [paymentMethod, setPaymentMethod] = useState('Cash');

  const [checkoutResult, setCheckoutResult] = useState<any>(null);
  const [checkingOut, setCheckingOut] = useState(false);
  const [lastCheckoutData, setLastCheckoutData] = useState<any>(null);

  // Default to the patient's first active prescription
  useEffect(() => {
    setSelectedPrescriptionId(prescriptions[0]?.id || '');
  }, [prescriptions]);

  // Sellable batches per medicine, earliest expiry first (FEFO); expired ones are excluded
  const batchesByMedicine = useMemo(() => {
    const now = Date.now();
    const map = new Map<string, any[]>();
    for (const b of batches) {
      if (new Date(b.expiry_date).getTime() <= now) continue;
      const list = map.get(b.medicine_id);
      if (list) list.push(b); else map.set(b.medicine_id, [b]);
    }
    map.forEach(list => list.sort((a, b) => new Date(a.expiry_date).getTime() - new Date(b.expiry_date).getTime()));
    return map;
  }, [batches]);

  const filteredMeds = useMemo(() => {
    if (!searchQuery) return [];
    const q = searchQuery.toLowerCase();
    return medicines.filter((m: any) => m.name.toLowerCase().includes(q) || m.generic_name.toLowerCase().includes(q));
  }, [searchQuery, medicines]);

  // Allergy and prescription warnings for the cart
  const warnings = useMemo(() => {
    const out: any[] = [];
    for (const item of cart) {
      const med = medicines.find((m: any) => m.id === item.medicine_id);
      if (!med) continue;
      // Allergy check (e.g. penicillin allergy vs amoxycillin)
      for (const allergy of selectedPatient?.allergies || []) {
        const salt = med.generic_name.toLowerCase();
        if (salt.includes(allergy.toLowerCase()) || (allergy.toLowerCase() === 'penicillin' && salt.includes('amoxycillin'))) {
          out.push({
            type: 'ALLERGY',
            message: `ALLERGY ALERT: Patient ${selectedPatient.name} is allergic to ${allergy}! ${med.name} contains ${med.generic_name}.`,
            medId: med.id,
          });
        }
      }
      // Schedule H prescription verification
      if (med.prescription_required && !selectedPrescriptionId) {
        out.push({
          type: 'REGULATORY',
          message: `PRESCRIPTION REQUIRED: ${med.name} is a Schedule H/X drug. No prescription selected!`,
          medId: med.id,
        });
      }
    }
    return out;
  }, [cart, medicines, selectedPatient, selectedPrescriptionId]);

  // Cart operations use the latest state, so rapid clicks aren't lost
  const addToCart = (med: any, batch: any) => {
    if (batch.quantity_on_hand <= 0) return;
    setCart(current => {
      const existing = current.find(item => item.batch_id === batch.id);
      if (existing) {
        if (existing.quantity >= batch.quantity_on_hand) return current;
        return current.map(item => item.batch_id === batch.id ? { ...item, quantity: item.quantity + 1 } : item);
      }
      return [...current, {
        medicine_id: med.id,
        name: med.name,
        generic: med.generic_name,
        batch_id: batch.id,
        batch_number: batch.batch_number,
        quantity: 1,
        unit_mrp: batch.mrp,
        max_qty: batch.quantity_on_hand,
      }];
    });
  };

  const removeFromCart = (batchId: string) => {
    setCart(current => current.filter(item => item.batch_id !== batchId));
  };

  const updateCartQty = (batchId: string, val: number) => {
    setCart(current => current.map(item => item.batch_id === batchId
      ? { ...item, quantity: Math.max(1, Math.min(item.max_qty, item.quantity + val)) }
      : item));
  };
  // Helper calculation
  const getSubtotal = () => cart.reduce((sum, item) => sum + (item.quantity * item.unit_mrp), 0);
  const getDiscount = () => getSubtotal() * (discountPercent / 100.0);
  const getNetTotal = () => getSubtotal() - getDiscount();

  const handleCheckout = async () => {
    // Guard against double submission: a second click would sell the cart twice
    if (cart.length === 0 || checkingOut) return;
    setCheckingOut(true);

    // Prices are decided by the server from the batch; only quantities are sent
    const requestData = {
      patient_id: selectedPatientId || null,
      prescription_id: selectedPrescriptionId || null,
      items: cart.map(item => ({
        medicine_id: item.medicine_id,
        batch_id: item.batch_id,
        quantity: item.quantity
      })),
      payment_method: paymentMethod,
      discount_percent: Math.min(100, Math.max(0, parseFloat(discountPercent) || 0))
    };

    try {
      const res = await apiFetch('/api/pos/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData)
      });
      if (res.ok) {
        const data = await res.json();
        // The receipt shows exactly what was billed, using the server's figures
        setLastCheckoutData({
          patientName: selectedPatient ? selectedPatient.name : "Walk-in Customer",
          dob: selectedPatient ? selectedPatient.date_of_birth : "",
          doctorName: prescriptions.find((r: any) => r.id === selectedPrescriptionId)?.prescribed_by || "",
          visitDate: new Date().toLocaleDateString(),
          billingItems: data.items.map((item: any) => ({
            name: item.name,
            quantity: item.quantity,
            unit_price: item.unit_price,
            total_price: item.total_price
          })),
          subtotal: data.total_amount,
          discountPercent: discountPercent,
          discountApplied: data.discount_applied,
          netPayable: data.net_amount,
          gstIncluded: data.gst_included,
          paymentMethod: paymentMethod,
          transactionId: data.invoice_id
        });

        setCheckoutResult(data);
        // Clear state
        setCart([]);
        setDiscountPercent(0);
        setSelectedPatientId('');
        // Stock, prescriptions and the dashboard changed: refresh them everywhere
        invalidate.sale();
      } else {
        notify.error("Checkout failed: " + await errorMessage(res, "unknown error"));
      }
    } catch (err) {
      console.error("Checkout error:", err);
      notify.error("Checkout error. Please check the connection to the server.");
    } finally {
      setCheckingOut(false);
    }
  };

  // The receipt is the invoice PDF that billing creates for every POS sale
  const receiptPdfUrl = (inline: boolean) =>
    `/api/billing/invoices/${encodeURIComponent(lastCheckoutData.transactionId)}/pdf` +
    `?tz_offset=${-new Date().getTimezoneOffset()}${inline ? '&inline=true' : ''}`;

  const handleDownloadPDF = async () => {
    if (!lastCheckoutData) return;
    try {
      const res = await apiFetch(receiptPdfUrl(false));
      if (!res.ok) {
        notify.error("Failed to download PDF receipt: " + await errorMessage(res, "unknown error"));
        return;
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `receipt_${lastCheckoutData.transactionId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      notify.error("Error downloading PDF receipt");
    }
  };

  // Opens the PDF in a new tab, where the browser's viewer can print it
  const handlePrintReceipt = () => {
    if (lastCheckoutData) window.open(receiptPdfUrl(true), '_blank');
  };

  return (
    <div className="flex-1 flex overflow-hidden max-h-[calc(100vh-64px)]">
      {/* Left panel: Product Lookup and Clinical Details */}
      <div className="flex-1 flex flex-col p-6 min-w-0 overflow-y-auto space-y-6">
        {/* Patient Lookup Card */}
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5 space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="font-semibold text-on-surface flex items-center gap-2">
              <User className="w-5 h-5 text-primary" /> Patient Association
            </h3>
            {selectedPatient && selectedPatient.allergies.length > 0 && (
              <span className="px-2 py-0.5 text-xs rounded bg-error-container text-error font-bold animate-pulse">
                Allergies: {selectedPatient.allergies.join(", ")}
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-bold text-on-surface-variant uppercase mb-1">Select Patient Profile</label>
              <select 
                className="w-full h-10 px-3 bg-surface-container-low border border-outline-variant rounded-lg text-sm focus:ring-2 focus:ring-primary focus:outline-none"
                value={selectedPatientId} 
                onChange={(e) => setSelectedPatientId(e.target.value)}
              >
                <option value="">Walk-in Customer (Anonymous)</option>
                {patients.map(p => (
                  <option key={p.id} value={p.id}>{p.name} ({p.phone})</option>
                ))}
              </select>
            </div>
            {selectedPatientId && prescriptions.length > 0 && (
              <div>
                <label className="block text-xs font-bold text-on-surface-variant uppercase mb-1">Select Active Prescription</label>
                <select 
                  className="w-full h-10 px-3 bg-surface-container-low border border-outline-variant rounded-lg text-sm focus:ring-2 focus:ring-primary focus:outline-none"
                  value={selectedPrescriptionId}
                  onChange={(e) => setSelectedPrescriptionId(e.target.value)}
                >
                  {prescriptions.map((rx: any) => (
                    <option key={rx.id} value={rx.id}>
                      Issued by {rx.prescribed_by} ({new Date(rx.date_issued).toLocaleDateString()})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          
          {/* Active Prescription Quick Addition Helper */}
          {selectedPatientId && prescriptions.length > 0 && selectedPrescriptionId && (
            <div className="bg-primary/5 border border-primary/20 rounded-lg p-3 space-y-2">
              <span className="text-xs font-bold text-primary uppercase">Prescribed Medications</span>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {prescriptions.find((r: any) => r.id === selectedPrescriptionId)?.medicines.map((m: any, idx: number) => {
                  const alreadyDispensed = m.dispensed_quantity >= m.quantity_prescribed;
                  const med = medicines.find(med => med.id === m.medicine_id);
                  const activeBatches = (batchesByMedicine.get(m.medicine_id) || []).filter((b: any) => b.quantity_on_hand > 0);
                  
                  return (
                    <div key={idx} className="flex justify-between items-center text-xs bg-white border border-outline-variant rounded p-2">
                      <div>
                        <span className="font-semibold text-on-surface">{m.medicine_name} {m.dosage}</span>
                        <p className="text-[10px] text-on-surface-variant font-mono">
                          Rx: {m.quantity_prescribed} | Disp: {m.dispensed_quantity} ({m.quantity_prescribed - m.dispensed_quantity} remaining)
                        </p>
                      </div>
                      {!alreadyDispensed && activeBatches.length > 0 ? (
                        <button 
                          className="bg-primary text-white px-2 py-1 rounded text-[10px] hover:bg-primary-container font-semibold"
                          onClick={() => addToCart(med, activeBatches[0])}
                        >
                          Dispense Batch #{activeBatches[0].batch_number}
                        </button>
                      ) : (
                        <span className="text-[10px] text-on-surface-variant font-semibold bg-surface-container px-2 py-0.5 rounded">
                          {alreadyDispensed ? "Dispensed" : "Out of Stock"}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Global Medicine / Batch Search Card */}
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-5 space-y-4 flex-1 flex flex-col min-h-[300px]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-outline h-4 w-4" />
            <input 
              type="text" 
              className="w-full pl-10 pr-4 h-10 bg-surface-container-low border border-outline-variant rounded-lg text-sm focus:ring-2 focus:ring-primary focus:outline-none"
              placeholder="Search medications by brand name or generic active salt (e.g. Augmentin, Paracetamol)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {searchQuery ? (
            <div className="flex-1 overflow-y-auto space-y-4">
              {filteredMeds.length === 0 ? (
                <div className="text-center p-6 text-on-surface-variant">No medications found matching "{searchQuery}"</div>
              ) : (
                filteredMeds.map((med: any) => {
                  const medBatches = batchesByMedicine.get(med.id) || [];
                  return (
                    <div key={med.id} className="border border-outline-variant rounded-lg p-3 bg-white space-y-2">
                      <div className="flex justify-between items-start">
                        <div>
                          <h4 className="font-semibold text-on-surface text-sm">{med.name} <span className="text-xs text-on-surface-variant font-normal">({med.dosage})</span></h4>
                          <span className="text-xs text-on-surface-variant italic font-mono">{med.generic_name}</span>
                        </div>
                        {med.prescription_required && (
                          <span className="px-2 py-0.5 text-[9px] rounded bg-error-container text-error font-bold uppercase tracking-wider">
                            Schedule H
                          </span>
                        )}
                      </div>
                      <div className="divide-y divide-outline-variant">
                        {medBatches.map(batch => (
                          <div key={batch.id} className="flex justify-between items-center py-2 text-xs">
                            <div>
                              <span className="font-semibold font-mono text-on-surface">Batch #{batch.batch_number}</span>
                              <p className="text-[10px] text-on-surface-variant">
                                Loc: {batch.location_code} | Exp: {new Date(batch.expiry_date).toLocaleDateString()} | Stock: {batch.quantity_on_hand}
                              </p>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="font-bold text-on-surface">₹{batch.mrp.toFixed(2)}</span>
                              <button 
                                className="bg-secondary text-white px-2 py-1 rounded hover:opacity-90 font-semibold"
                                onClick={() => addToCart(med, batch)}
                                disabled={batch.quantity_on_hand <= 0}
                              >
                                {batch.quantity_on_hand > 0 ? "Add to Cart" : "Out of Stock"}
                              </button>
                            </div>
                          </div>
                        ))}
                        {medBatches.length === 0 && (
                          <div className="text-xs text-on-surface-variant py-2">No active batches available.</div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-on-surface-variant gap-2 opacity-60">
              <FileSpreadsheet className="w-10 h-10 text-outline" />
              <p className="text-xs font-semibold">Enter search queries to lookup inventory and batches</p>
            </div>
          )}
        </div>
      </div>

      {/* Right panel: Cart Details & Checkout Terminal */}
      <div className="w-[380px] bg-surface-container border-l border-outline-variant flex flex-col shrink-0">
        <div className="p-4 border-b border-outline-variant bg-surface flex justify-between items-center">
          <h3 className="font-bold text-on-surface flex items-center gap-2 text-sm uppercase tracking-wider">
            <ShoppingCart className="w-4 h-4 text-primary" /> Active Billing Cart ({cart.length})
          </h3>
          {cart.length > 0 && (
            <button className="text-xs text-error font-semibold hover:underline" onClick={() => setCart([])}>Clear</button>
          )}
        </div>

        {/* Warning banners */}
        {warnings.length > 0 && (
          <div className="bg-error-container border-b border-error/20 p-3 space-y-2">
            {warnings.map((w, idx) => (
              <div key={idx} className="flex gap-2 items-start text-xs text-error font-semibold leading-tight">
                <AlertTriangle className="w-4 h-4 shrink-0 text-error" />
                <p>{w.message}</p>
              </div>
            ))}
          </div>
        )}

        {/* Cart items list */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {cart.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-on-surface-variant opacity-60 text-center gap-2">
              <ShoppingCart className="w-8 h-8 text-outline" />
              <p className="text-xs font-semibold">Cart is currently empty.</p>
            </div>
          ) : (
            cart.map(item => (
              <div key={item.batch_id} className="bg-surface-container-lowest border border-outline-variant p-3 rounded-lg flex flex-col justify-between gap-2 shadow-xs">
                <div className="flex justify-between items-start">
                  <div>
                    <h5 className="font-bold text-on-surface text-xs leading-tight">{item.name}</h5>
                    <span className="text-[10px] text-on-surface-variant font-mono">Batch #{item.batch_number}</span>
                  </div>
                  <button className="text-on-surface-variant hover:text-error" onClick={() => removeFromCart(item.batch_id)}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                <div className="flex justify-between items-center mt-2">
                  <div className="flex items-center gap-2">
                    <button className="p-1 rounded bg-surface-container-low hover:bg-surface-container-high border border-outline-variant" onClick={() => updateCartQty(item.batch_id, -1)}>
                      <Minus className="w-3 h-3 text-on-surface" />
                    </button>
                    <span className="text-xs font-bold text-on-surface w-4 text-center">{item.quantity}</span>
                    <button className="p-1 rounded bg-surface-container-low hover:bg-surface-container-high border border-outline-variant" onClick={() => updateCartQty(item.batch_id, 1)}>
                      <Plus className="w-3 h-3 text-on-surface" />
                    </button>
                  </div>
                  <span className="font-bold text-on-surface text-xs">₹{(item.quantity * item.unit_mrp).toFixed(2)}</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Pricing Summary */}
        <div className="p-4 bg-surface border-t border-outline-variant space-y-3">
          <div className="space-y-1.5 text-xs text-on-surface-variant font-semibold">
            <div className="flex justify-between">
              <span>Subtotal:</span>
              <span className="text-on-surface">₹{getSubtotal().toFixed(2)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span>Discount (%):</span>
              <input 
                type="number" 
                className="w-12 h-6 px-1 text-center bg-surface-container-low border border-outline-variant rounded font-semibold text-on-surface"
                value={discountPercent} 
                onChange={(e) => setDiscountPercent(Math.max(0, Math.min(100, parseFloat(e.target.value) || 0)))}
              />
            </div>
            <div className="flex justify-between text-error font-bold">
              <span>Discount Applied:</span>
              <span>- ₹{getDiscount().toFixed(2)}</span>
            </div>
            <div className="h-[1px] bg-outline-variant my-1"></div>
            <div className="flex justify-between text-sm font-bold text-on-surface">
              <span>Net Payable:</span>
              <span className="text-primary text-base font-black">₹{getNetTotal().toFixed(2)}</span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs">
            {['Cash', 'Card', 'UPI'].map(method => (
              <button 
                key={method} 
                className={`py-2 border rounded-lg font-bold transition-all ${paymentMethod === method ? 'bg-primary text-white border-primary' : 'bg-surface-container-low border-outline-variant text-on-surface-variant hover:bg-surface-container-high'}`}
                onClick={() => setPaymentMethod(method)}
              >
                {method}
              </button>
            ))}
          </div>

          <button 
            className="w-full py-3 bg-secondary text-white font-bold rounded-lg flex items-center justify-center gap-2 hover:opacity-90 active:scale-98 transition-all disabled:opacity-50"
            disabled={cart.length === 0 || checkingOut}
            onClick={handleCheckout}
          >
            <CreditCard className="w-4 h-4" /> {checkingOut ? 'PROCESSING…' : <>DISPENSE &amp; PRINT BILL</>}
          </button>
        </div>
      </div>

      {/* Checkout Success Modal */}
      {checkoutResult && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white border border-outline-variant max-w-4xl w-full rounded-xl p-6 shadow-xl flex flex-col md:flex-row gap-6 max-h-[85vh]">
            
            {/* Left panel: Info & Actions */}
            <div className="md:w-1/3 flex flex-col items-center justify-between text-center space-y-4 py-2 shrink-0">
              <div className="flex flex-col items-center space-y-3">
                <CheckCircle className="w-16 h-16 text-secondary animate-bounce" />
                <div>
                  <h4 className="font-bold text-on-surface text-lg">Transaction Successful</h4>
                  <p className="text-xs text-on-surface-variant mt-1">Dispensed successfully from Terminal 042</p>
                </div>
              </div>
              
              <div className="bg-surface-container p-3 rounded-lg w-full text-left space-y-1.5 text-xs text-on-surface-variant font-semibold">
                <div className="flex justify-between"><span className="font-normal">Transaction ID:</span><span className="font-mono font-bold text-primary">{checkoutResult.transaction_id}</span></div>
                <div className="flex justify-between"><span className="font-normal">Total Amount:</span><span className="font-bold text-on-surface">₹{checkoutResult.total_amount.toFixed(2)}</span></div>
                <div className="flex justify-between"><span className="font-normal">Discount:</span><span className="font-bold text-error">- ₹{checkoutResult.discount_applied.toFixed(2)}</span></div>
                <div className="flex justify-between text-sm text-on-surface pt-1.5 border-t border-outline-variant font-black"><span>Net Paid:</span><span>₹{checkoutResult.net_amount.toFixed(2)}</span></div>
              </div>

              <div className="w-full space-y-2 text-xs">
                <button 
                  className="w-full py-2.5 bg-primary text-white font-bold rounded-lg hover:opacity-90 flex items-center justify-center gap-2"
                  onClick={handleDownloadPDF}
                >
                  <Download className="w-4 h-4" /> Download PDF Receipt
                </button>
                 <button 
                  className="w-full py-2.5 bg-white border border-outline text-on-surface font-bold rounded-lg hover:bg-surface-container flex items-center justify-center gap-2"
                  onClick={handlePrintReceipt}
                >
                  <Printer className="w-4 h-4" /> Print Receipt
                </button>
                <div className="pt-2 border-t border-outline-variant/30 w-full">
                  <button 
                    className="w-full py-2.5 bg-secondary text-white font-bold rounded-lg hover:opacity-90 active:scale-98 transition-all"
                    onClick={() => {
                      setCheckoutResult(null);
                      setLastCheckoutData(null);
                    }}
                  >
                    Done (New Sale)
                  </button>
                </div>
              </div>
            </div>

            {/* Vertical Divider */}
            <div className="hidden md:block w-px bg-outline-variant self-stretch"></div>

            {/* Right panel: receipt summary (the PDF is the billing invoice) */}
            {lastCheckoutData && (
              <div className="flex-1 flex flex-col min-h-[350px] md:min-h-0">
                <div className="text-xs font-bold text-on-surface-variant mb-2">Receipt</div>
                <div className="flex-1 bg-surface-dim border border-outline-variant rounded-lg p-3 overflow-y-auto">
                  <div className="bg-white rounded border border-outline-variant/60 p-4 text-xs space-y-3 select-text">
                    <div className="flex justify-between items-start border-b border-outline-variant pb-2">
                      <div>
                        <div className="font-black text-primary text-sm">Tax Invoice</div>
                        <div className="font-mono text-on-surface-variant">{lastCheckoutData.transactionId}</div>
                      </div>
                      <div className="text-right text-on-surface-variant">
                        <div>{lastCheckoutData.visitDate}</div>
                        <div>Paid by {lastCheckoutData.paymentMethod}</div>
                      </div>
                    </div>
                    <div className="text-on-surface-variant space-y-0.5">
                      <div><span className="font-bold text-on-surface">Patient:</span> {lastCheckoutData.patientName}</div>
                      {lastCheckoutData.doctorName && (
                        <div><span className="font-bold text-on-surface">Prescribed by:</span> {lastCheckoutData.doctorName}</div>
                      )}
                    </div>
                    <table className="w-full">
                      <thead className="text-[10px] uppercase text-outline border-b border-outline-variant">
                        <tr>
                          <th className="text-left py-1">Item</th>
                          <th className="text-center py-1">Qty</th>
                          <th className="text-right py-1">Rate</th>
                          <th className="text-right py-1">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lastCheckoutData.billingItems.map((item: any, idx: number) => (
                          <tr key={idx} className="border-b border-outline-variant/40">
                            <td className="py-1.5">{item.name}</td>
                            <td className="py-1.5 text-center">{item.quantity}</td>
                            <td className="py-1.5 text-right">₹{Number(item.unit_price).toFixed(2)}</td>
                            <td className="py-1.5 text-right">₹{Number(item.total_price).toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="space-y-1 ml-auto w-48">
                      <div className="flex justify-between"><span>Subtotal</span><span>₹{Number(lastCheckoutData.subtotal).toFixed(2)}</span></div>
                      <div className="flex justify-between text-error"><span>Discount</span><span>- ₹{Number(lastCheckoutData.discountApplied).toFixed(2)}</span></div>
                      <div className="flex justify-between font-black text-sm border-t border-outline-variant pt-1"><span>Net Paid</span><span>₹{Number(lastCheckoutData.netPayable).toFixed(2)}</span></div>
                      <div className="text-[10px] text-outline text-right">Includes GST of ₹{Number(lastCheckoutData.gstIncluded || 0).toFixed(2)}</div>
                    </div>
                  </div>
                </div>
              </div>
            )}

          </div>
        </div>
      )}
    </div>
  );
}
