import {
  Building,
  Download,
  FileText,
  Layers,
  RotateCcw,
  Trash2,
  X
} from 'lucide-react';
import { formatDateTime, formatINR } from '../../lib/format';
import { canCancel, canRefund } from './rules';
import { BarcodeSVG } from './Visuals';

interface Props {
  invoice: any;
  onClose: () => void;
  onDownload: () => void;
  onRefund: (id: string) => void;
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
}

export default function InvoiceDrawer({ invoice, onClose, onDownload, onRefund, onCancel, onDelete }: Props) {
  return (
  <div className="fixed inset-0 z-50 flex justify-end no-print">

    {/* Overlay backdrop */}
    <div
      className="absolute inset-0 bg-black/40 backdrop-blur-xs transition-all"
      onClick={onClose}
    />

    {/* Sliding sheet container */}
    <div className="w-[500px] h-full bg-white shadow-2xl relative flex flex-col z-10 animate-slide-in">

      {/* Header controls */}
      <div className="p-4 border-b border-outline-variant flex items-center justify-between bg-surface-container-low shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary" />
          <div>
            <h3 className="text-xs font-black uppercase text-primary tracking-wider">Invoice Ledger Sheet</h3>
            <p className="text-[10px] text-on-surface-variant font-mono">{invoice.id}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-surface-container rounded-full"
        >
          <X className="w-5 h-5 text-on-surface-variant" />
        </button>
      </div>

      {/* Scrollable details body */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">

        {/* Receipt Preview Canvas wrapper */}
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-6 space-y-6 text-on-surface relative shadow-sm">

          {/* Visual Official Hospital Title */}
          <div className="text-center border-b border-primary/20 pb-4">
            <div className="font-black text-sm text-primary tracking-wide uppercase">{invoice.store_name}</div>
            <div className="text-[8px] text-outline font-extrabold uppercase mt-0.5">Clinical Excellence in Pharmacy Care</div>
          </div>

          {/* Patient Context & Reference Details */}
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div className="space-y-1">
              <span className="text-[9px] text-outline font-black uppercase">PATIENT PROFILE</span>
              <p className="font-bold text-on-surface">{invoice.patient_name}</p>
              <p className="text-[10px] text-on-surface-variant font-mono">ID: {invoice.patient_id || 'Walk-in'}</p>
              <p className="text-[10px] text-on-surface-variant">Phone: {invoice.patient_phone}</p>
            </div>
            <div className="space-y-1 text-right">
              <span className="text-[9px] text-outline font-black uppercase">TX DETAILS</span>
              <p className="font-bold text-on-surface font-mono">{invoice.id}</p>
              <p className="text-[10px] text-on-surface-variant">{formatDateTime(invoice.date)}</p>
              <p className="text-[10px] text-on-surface-variant">Doc: {invoice.doctor_name}</p>
            </div>
          </div>

          {/* List Items table */}
          <div className="border-t border-b border-outline-variant/60 py-3">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-outline-variant/30 text-[9px] text-outline font-black uppercase">
                  <th className="pb-2 text-left">Description</th>
                  <th className="pb-2 text-center w-16">Batch</th>
                  <th className="pb-2 text-center w-10">Qty</th>
                  <th className="pb-2 text-right w-16">Price</th>
                  <th className="pb-2 text-right w-20">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/20">
                {invoice.billing_items.map((item: any, idx: number) => (
                  <tr key={idx} className="text-on-surface">
                    <td className="py-2.5 font-bold">{item.name}</td>
                    <td className="py-2.5 text-center font-mono text-[9px] text-on-surface-variant">{item.batch_number}</td>
                    <td className="py-2.5 text-center font-semibold">{item.quantity}</td>
                    <td className="py-2.5 text-right font-mono font-semibold text-on-surface-variant">{formatINR(item.unit_price)}</td>
                    <td className="py-2.5 text-right font-mono font-bold">{formatINR(item.total_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* GST Breakdowns */}
          {invoice.tax_breakdown && (
            <div className="bg-surface-container-low border border-outline-variant/60 rounded-lg p-3 text-[10px] text-on-surface-variant space-y-1">
              <div className="font-bold text-[9px] uppercase tracking-wider text-outline">GST TAX BREAKDOWN</div>
              <div className="flex justify-between font-mono">
                <span>CGST (6.0%):</span>
                <span>{formatINR(invoice.tax_breakdown.cgst)}</span>
              </div>
              <div className="flex justify-between font-mono">
                <span>SGST (6.0%):</span>
                <span>{formatINR(invoice.tax_breakdown.sgst)}</span>
              </div>
              <div className="flex justify-between font-mono border-t border-outline-variant/30 pt-1 font-bold text-on-surface">
                <span>Total GST Collected:</span>
                <span>{formatINR(invoice.tax_breakdown.total_gst)}</span>
              </div>
            </div>
          )}

          {/* Subtotal & Totals area */}
          <div className="flex justify-end">
            <div className="w-1/2 space-y-1.5 text-xs">
              <div className="flex justify-between text-on-surface-variant">
                <span>Subtotal:</span>
                <span className="font-mono font-semibold">{formatINR(invoice.gross_amount - invoice.discount_applied)}</span>
              </div>
              <div className="flex justify-between text-error">
                <span>Discount:</span>
                <span className="font-mono font-bold">-{formatINR(invoice.discount_applied)}</span>
              </div>
              <div className="flex justify-between text-on-surface border-t border-outline-variant/40 pt-1.5 font-black text-sm">
                <span className="text-primary uppercase tracking-wide">Total Due:</span>
                <span className="font-mono text-primary">{formatINR(invoice.net_payable)}</span>
              </div>
            </div>
          </div>

          {/* Insurance details if claim */}
          {invoice.insurance_details && invoice.insurance_details.provider && (
            <div className="border border-purple-200 bg-purple-50/50 rounded-lg p-3 text-[10px] text-purple-800 space-y-1">
              <div className="font-black text-[9px] uppercase tracking-wider text-purple-900 flex items-center gap-1">
                <Building className="w-3.5 h-3.5" /> Insurance Claim Information
              </div>
              <div className="grid grid-cols-2 gap-2 mt-1">
                <div>Insurer: <strong>{invoice.insurance_details.provider}</strong></div>
                <div>Policy: <strong>{invoice.insurance_details.policy_number}</strong></div>
                <div>Claim Ref: <strong>{invoice.insurance_details.claim_number}</strong></div>
                <div>Approved: <strong>{formatINR(invoice.insurance_details.approved_amount)}</strong></div>
                <div className="col-span-2">Claim Status: <span className="underline font-bold uppercase">{invoice.insurance_details.status}</span></div>
              </div>
            </div>
          )}

          {/* Refund details if refunded */}
          {invoice.refund_details && invoice.refund_details.refund_amount && (
            <div className="border border-error/20 bg-error/5 rounded-lg p-3 text-[10px] text-error space-y-1">
              <div className="font-black text-[9px] uppercase tracking-wider text-error flex items-center gap-1">
                <RotateCcw className="w-3.5 h-3.5" /> Refund Logged
              </div>
              <div>Refund Amount: <strong>{formatINR(invoice.refund_details.refund_amount)}</strong></div>
              <div>Approved By: <strong>{invoice.refund_details.approved_by}</strong></div>
              <div>Reason: <strong>{invoice.refund_details.reason}</strong></div>
            </div>
          )}

          {/* QR and Barcode Visuals */}
          <div className="flex items-center justify-between pt-4 border-t border-outline-variant/30">
            <div>
              {invoice.qr_code && (
                <img
                  src={invoice.qr_code}
                  alt="Verification QR"
                  className="w-16 h-16 border border-outline-variant/60 p-0.5 rounded bg-white"
                />
              )}
            </div>
            <div>
              <BarcodeSVG value={invoice.barcode} />
            </div>
          </div>
        </div>

        {/* Transaction Audit Trail Log */}
        <div className="space-y-3">
          <h4 className="text-xs font-black uppercase text-outline tracking-wider flex items-center gap-1"><Layers className="w-4 h-4" /> Activity Log Trail</h4>
          <div className="space-y-2">
            {invoice.audit_trail && invoice.audit_trail.map((log: any, idx: number) => (
              <div key={idx} className="bg-surface-container-low border border-outline-variant/60 p-2.5 rounded-lg text-[10px] text-on-surface-variant flex items-start gap-2">
                <div className="w-1.5 h-1.5 bg-primary rounded-full mt-1 shrink-0"></div>
                <div className="flex-1">
                  <div className="flex justify-between items-center">
                    <strong className="text-on-surface font-semibold">{log.action_type}</strong>
                    <span className="font-mono text-[8px] text-outline">{formatDateTime(log.timestamp)}</span>
                  </div>
                  <p className="mt-0.5 font-medium text-outline">User: {log.user}</p>
                  <p className="mt-1 font-mono text-[9px] bg-white border border-outline-variant/30 px-1 py-0.5 rounded inline-block">
                    {log.previous_value ? `Changed from ${log.previous_value} to ` : ''}{log.new_value}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* Floating actions footer */}
      <div className="p-4 border-t border-outline-variant bg-surface-container-low flex gap-2 shrink-0">
        <button
          onClick={onDownload}
          className="flex-1 py-2 bg-primary text-white text-xs font-bold rounded-lg hover:opacity-90 flex items-center justify-center gap-1.5 transition-all"
        >
          <Download className="w-4 h-4" /> Download PDF
        </button>

        {canRefund(invoice) && (
          <button
            onClick={() => onRefund(invoice.id)}
            className="px-3 py-2 bg-white border border-outline text-error font-bold text-xs rounded-lg hover:bg-error/5 transition-all"
          >
            Refund
          </button>
        )}
        {canCancel(invoice) && (
          <button
            onClick={() => onCancel(invoice.id)}
            className="px-3 py-2 bg-white border border-outline text-error font-bold text-xs rounded-lg hover:bg-error/5 transition-all"
          >
            Cancel
          </button>
        )}

        <button
          onClick={() => onDelete(invoice.id)}
          className="px-2 py-2 bg-white border border-outline text-on-surface-variant hover:text-error rounded-lg hover:bg-error/5 transition-all"
          title="Delete invoice record"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

    </div>
  </div>
  );
}
