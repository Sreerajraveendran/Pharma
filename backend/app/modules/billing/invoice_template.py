INVOICE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {
        size: a4;
        margin: 1.5cm;
    }
    body {
        font-family: Helvetica, Arial, sans-serif;
        color: #151c27;
        font-size: 10pt;
        line-height: 1.4;
    }
    .header-table {
        width: 100%;
        border-bottom: 2px solid #003d9b;
        margin-bottom: 15px;
        padding-bottom: 10px;
    }
    .clinic-title {
        font-size: 18pt;
        font-weight: bold;
        color: #003d9b;
    }
    .clinic-details {
        text-align: right;
        font-size: 8.5pt;
        color: #5c5f60;
    }
    .meta-table {
        width: 100%;
        margin-bottom: 15px;
        border-bottom: 1px dashed #003d9b;
        padding-bottom: 8px;
    }
    .meta-table td {
        padding: 2px 0;
        font-size: 9pt;
    }
    .section-title {
        font-size: 11pt;
        font-weight: bold;
        color: #003d9b;
        border-bottom: 1px solid #e1e2e4;
        margin-top: 15px;
        margin-bottom: 8px;
        padding-bottom: 2px;
    }
    .med-table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 15px;
    }
    .med-table th {
        background-color: #f0f3ff;
        color: #003d9b;
        text-align: left;
        padding: 5px;
        font-size: 8.5pt;
        font-weight: bold;
        border-bottom: 1px solid #c3c6d6;
    }
    .med-table td {
        padding: 6px 5px;
        border-bottom: 1px solid #dee2e2;
        font-size: 9pt;
    }
    .summary-table {
        width: 40%;
        margin-top: 5px;
        border-collapse: collapse;
        float: right;
    }
    .summary-table td {
        padding: 3px 5px;
        font-size: 9pt;
    }
    .total-amount {
        font-size: 12pt;
        font-weight: bold;
        color: #003d9b;
    }
    .tax-breakdown-box {
        border: 1px solid #dee0e2;
        padding: 8px;
        margin-top: 15px;
        font-size: 8pt;
        color: #5c5f60;
        width: 50%;
        float: left;
    }
    .bottom-meta {
        clear: both;
        margin-top: 30px;
        width: 100%;
    }
    .qr-barcode-table {
        width: 100%;
        margin-top: 20px;
    }
    .signature-area {
        text-align: center;
        width: 200px;
        float: right;
    }
    .signature-line {
        border-bottom: 1px solid #151c27;
        margin-bottom: 3px;
    }
    .terms {
        font-size: 7.5pt;
        color: #737685;
        margin-top: 25px;
        border-top: 1px solid #e1e2e4;
        padding-top: 5px;
    }
</style>
</head>
<body>
    <table class="header-table">
        <tr>
            <td>
                <div class="clinic-title">{{ store_name }}</div>
                <div class="clinic-subtitle">Clinical Excellence in Pharmacy Care</div>
            </td>
            <td class="clinic-details">
                <div>PharmaCore Medical Plaza, Suite 400</div>
                <div>Metropolis, NY 10001</div>
                <div>Tel: (555) 010-8899</div>
            </td>
        </tr>
    </table>

    <table class="meta-table">
        <tr>
            <td><strong>PATIENT:</strong> {{ patient_name }}</td>
            <td style="text-align: right;"><strong>INVOICE ID:</strong> {{ id }}</td>
        </tr>
        <tr>
            <td><strong>PATIENT TYPE:</strong> {{ patient_type }}</td>
            <td style="text-align: right;"><strong>DATE & TIME:</strong> {{ date }}</td>
        </tr>
        <tr>
            <td><strong>REFERRING DOCTOR:</strong> {{ doctor_name }}</td>
            <td style="text-align: right;"><strong>PAYMENT METHOD:</strong> {{ payment_method }}</td>
        </tr>
    </table>

    <div class="section-title">BILLING ITEMS & MEDICINES</div>
    <table class="med-table">
        <thead>
            <tr>
                <th style="width: 45%;">Description</th>
                <th style="width: 15%;">Batch No.</th>
                <th style="width: 10%; text-align: center;">Qty</th>
                <th style="width: 15%; text-align: right;">Unit Price</th>
                <th style="width: 15%; text-align: right;">Total Price</th>
            </tr>
        </thead>
        <tbody>
            {% for item in billing_items %}
            <tr>
                <td><strong>{{ item.name }}</strong></td>
                <td><font face="Courier">{{ item.batch_number }}</font></td>
                <td style="text-align: center;">{{ item.quantity }}</td>
                <td style="text-align: right;">₹{{ "%.2f" | format(item.unit_price) }}</td>
                <td style="text-align: right;">₹{{ "%.2f" | format(item.total_price) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="tax-breakdown-box">
        <strong>GST TAX BREAKDOWN:</strong><br/>
        CGST (6.0%): ₹{{ "%.2f" | format(tax_breakdown.cgst) }}<br/>
        SGST (6.0%): ₹{{ "%.2f" | format(tax_breakdown.sgst) }}<br/>
        IGST (0.0%): ₹{{ "%.2f" | format(tax_breakdown.igst) }}<br/>
        <strong>Total GST Taxes: ₹{{ "%.2f" | format(tax_breakdown.total_gst) }}</strong>
    </div>

    <table class="summary-table">
        <tr>
            <td>Subtotal:</td>
            <td style="text-align: right;">₹{{ "%.2f" | format(gross_amount - discount_applied) }}</td>
        </tr>
        <tr>
            <td style="color: #ba1a1a;">Discount:</td>
            <td style="text-align: right; color: #ba1a1a;">- ₹{{ "%.2f" | format(discount_applied) }}</td>
        </tr>
        <tr style="border-top: 1px solid #c3c6d6;">
            <td style="font-weight: bold; color: #003d9b;">Total Due:</td>
            <td style="text-align: right;" class="total-amount">₹{{ "%.2f" | format(net_payable) }}</td>
        </tr>
    </table>

    <div style="clear: both; height: 10px;"></div>

    <table class="qr-barcode-table">
        <tr>
            <td style="width: 120px;">
                <img src="{{ qr_code }}" width="100" height="100" />
            </td>
            <td>
                <div style="font-size: 8.5pt; color: #5c5f60;">
                    <strong>Verification Details:</strong><br/>
                    Status: {{ status }}<br/>
                    Amount Paid: ₹{{ "%.2f" | format(amount_paid) }}<br/>
                    Balance Due: ₹{{ "%.2f" | format(balance_due) }}<br/>
                    Cashier: {{ cashier_name }}
                </div>
            </td>
            <td>
                <div class="signature-area">
                    <div style="height: 45px;"></div>
                    <div class="signature-line"></div>
                    <div style="font-size: 9pt; font-weight: bold;">Authorized Signatory</div>
                    <div style="font-size: 7.5pt; color: #5c5f60;">PHARMACORE ENTERPRISE</div>
                </div>
            </td>
        </tr>
    </table>

    <div class="terms">
        <strong>Terms & Conditions:</strong><br/>
        1. This is a computer-generated invoice and requires no physical signature.<br/>
        2. Medicines once sold cannot be returned or exchanged without a valid pharmacy audit verification.<br/>
        3. Please consult your physician before taking any prescribed medication.<br/>
        Thank you for choosing PharmaCore Medical Group!
    </div>
</body>
</html>"""
