import io
from xml.sax.saxutils import escape
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from orders.models import Order


class CommercialDocumentGenerator:
    """
    High-performance programmatic document generation engine compiling transaction 
    receipts and invoices natively into memory streams.
    """

    @classmethod
    def generate_invoice_pdf_stream(cls, order_id):
        """
        Fetches system database transactional states from Phase 4 and builds 
        a clean, production-grade legal invoice output stream.
        """
        try:
            order = Order.objects.select_related('customer', 'branch').prefetch_related('items__product', 'items__variant__product').get(id=order_id)
        except Order.DoesNotExist:
            raise ValidationError(f"Invoicing Error: Target transaction record with ID #{order_id} does not exist.")

        # Initialize the byte-stream memory buffer layer
        buffer = io.BytesIO()
        
        # Initialize canvas container utilizing standard Letter constraints
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
        )
        
        story = []
        styles = getSampleStyleSheet()

        # Custom Branded Typographical Style Formats
        title_style = ParagraphStyle(
            'InvoiceTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=24,
            leading=28,
            textColor=colors.HexColor('#1A365D')  # Corporate Deep Navy
        )
        meta_style = ParagraphStyle(
            'InvoiceMeta',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#4A5568')
        )
        header_cell_style = ParagraphStyle(
            'HeaderCell',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=12,
            textColor=colors.white
        )
        body_cell_style = ParagraphStyle(
            'BodyCell',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#2D3748')
        )

        # 1. Header Branded Meta Block Insertion
        story.append(Paragraph("DYNAMIC RETAIL SYSTEM", title_style))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Branch: {escape(order.branch.name)}", meta_style))
        story.append(Paragraph(f"Receipt Reference: {escape(order.order_number)}", meta_style))
        story.append(Paragraph(f"Date Issued: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}", meta_style))
        story.append(Spacer(1, 15))

        # 2. Customer Profile Details Segment
        if order.customer:
            customer_name = order.customer.get_full_name() or order.customer_name or order.customer.email or "Guest"
        else:
            customer_name = order.customer_name or "Guest"
        story.append(Paragraph("<b>BILLED TO:</b>", meta_style))
        story.append(Paragraph(f"Customer: {escape(customer_name)}", meta_style))
        story.append(Paragraph(f"Contact: {escape(order.customer_phone or 'N/A')}", meta_style))
        story.append(Paragraph(f"Payment: {escape(order.get_payment_method_display())}", meta_style))
        if order.processed_by_id:
            story.append(Paragraph(f"Cashier: {escape(order.processed_by.username)}", meta_style))
        story.append(Spacer(1, 20))

        # 3. Transaction Itemized Invoice Ledger Table Construction
        # Header Row Layout
        table_data = [[
            Paragraph("Product Specification", header_cell_style),
            Paragraph("SKU Reference", header_cell_style),
            Paragraph("Unit Cost", header_cell_style),
            Paragraph("Qty", header_cell_style),
            Paragraph("Line Subtotal", header_cell_style)
        ]]

        # Populate rows cleanly by tracking item loops from Phase 4 definitions
        for item in order.items.all():
            subtotal = item.quantity * item.unit_price
            item_name = str(item.variant) if item.variant else item.product.name
            item_sku = item.product.sku if item.product else (item.variant.product.sku if item.variant else "N/A")
            table_data.append([
                Paragraph(escape(item_name), body_cell_style),
                Paragraph(escape(item_sku), body_cell_style),
                Paragraph(f"KES {item.unit_price:,.2f}", body_cell_style),
                Paragraph(str(item.quantity), body_cell_style),
                Paragraph(f"KES {subtotal:,.2f}", body_cell_style)
            ])

        # Financial Aggregation Summary Footer Row Definition
        table_data.append([
            Paragraph("<b>TOTAL PAID:</b>", body_cell_style),
            "", "", "",
            Paragraph(f"<b>KES {order.total_payable:,.2f}</b>", body_cell_style)
        ])

        # Define Explicit Structural Columns Proportional Width Profiles (Total = 532 pt)
        item_table = Table(table_data, colWidths=[182, 100, 90, 40, 120])
        
        # Professional Grid Framing and Table Styling Matrix
        item_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A365D')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#F7FAFC')), # Alternating row feel
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor('#1A365D')), # Bold base accent rule line
            ('TOPPADDING', (0, -1), (-1, -1), 12),
        ]))
        
        story.append(item_table)
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Subtotal: KES {order.subtotal:,.2f}", meta_style))
        story.append(Paragraph(f"Discount: KES {order.discount_amount:,.2f}", meta_style))
        if order.amount_received is not None:
            story.append(Paragraph(f"Cash received: KES {order.amount_received:,.2f}", meta_style))
            story.append(Paragraph(f"Change due: KES {order.change_due:,.2f}", meta_style))
        
        # Compile document composition structural sequence down into buffer stream completely
        doc.build(story)
        
        # Seek stream back to the initial bit registry point for direct safe read access extraction
        buffer.seek(0)
        return buffer
