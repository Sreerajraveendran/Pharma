// Which actions an invoice's status allows (mirrors the server's rules)
export const REFUNDABLE = ['Paid', 'Partially Paid', 'Partially Refunded'];
export const canRefund = (inv: any) => REFUNDABLE.includes(inv.status) && (inv.amount_paid - (inv.refunded_amount || 0)) > 0;
export const canCancel = (inv: any) => ['Paid', 'Pending', 'Partially Paid'].includes(inv.status) && !(inv.refunded_amount > 0);
