from io import BytesIO
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from django.utils import timezone

class ExecutiveReportPDFGenerator:
    """
    Compiles operational analytical matrices into structured, binary 
    PDF presentation reports suitable for immediate C-Suite audit review.
    """

    @classmethod
    def compile_executive_pdf_buffer(cls, financial_data, catalog_data, compliance_data):
        """
        Assembles financial parameters, inventory matrices, and risk summaries
        natively within an unalterable dynamic canvas layout stream.
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )
        
        styles = getSampleStyleSheet()
        
        # Define high-end custom corporate palette
        primary_color = colors.HexColor('#0F172A')   # Slate 900
        secondary_color = colors.HexColor('#2563EB') # Blue 600
        accent_warn = colors.HexColor('#DC2626')     # Red 600
        light_bg = colors.HexColor('#F8FAFC')        # Slate 50
        grid_color = colors.HexColor('#E2E8F0')      # Slate 200

        # Custom Typography Elements
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=24,
            leading=28,
            textColor=primary_color,
            spaceAfter=6
        )
        section_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=14,
            leading=18,
            textColor=secondary_color,
            spaceBefore=14,
            spaceAfter=8
        )
        body_style = ParagraphStyle(
            'ReportBody',
            parent=styles['BodyText'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#334155')
        )
        header_cell_style = ParagraphStyle(
            'HeaderCell',
            parent=body_style,
            fontName='Helvetica-Bold',
            textColor=colors.white
        )

        story = []

        # 1. Document Title Block
        story.append(Paragraph("DYNAMIC RETAIL SYSTEM", ParagraphStyle('Sub', fontName='Helvetica-Bold', fontSize=10, textColor=secondary_color, leading=12)))
        story.append(Paragraph("Executive Performance & Audit Ledger", title_style))
        story.append(Paragraph(f"Compiled on: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} EAT | System Scope: All Branches", body_style))
        story.append(Spacer(1, 15))

        # 2. Executive Operational Summary Blocks (Key Metrics Grid)
        story.append(Paragraph("1. High-Level Compliance Risk Summary", section_style))
        summary_text = (
            f"<b>Total Void Transactions Triggered:</b> {compliance_data['voided_transactions_count']} <br/>"
            f"<b>Manual Payment Webhook Overrides:</b> {compliance_data['manual_payment_confirmations_count']} <br/>"
            f"<b>Net Cash Variance Profile:</b> KES {compliance_data['net_cash_variance']:,.2f} across ({compliance_data['variance_incidents_logged']}) shift incidents.<br/>"
            f"<b>Average Logistics Transit Time:</b> {catalog_data['average_fulfillment_minutes']} Minutes."
        )
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 15))

        # 3. Table 1: Branch Financial Performance Distribution
        story.append(Paragraph("2. Regional Branch Network Revenue Distribution", section_style))
        branch_table_data = [[Paragraph("Branch Node Location", header_cell_style), Paragraph("Total Registered Sales Volume", header_cell_style), Paragraph("Gross Segment Revenue", header_cell_style)]]
        
        for branch in financial_data['branch_performance_matrix']:
            branch_table_data.append([
                Paragraph(branch['name'], body_style),
                Paragraph(str(branch['volume']), body_style),
                Paragraph(f"KES {branch['revenue']:,.2f}", body_style)
            ])
            
        t1 = Table(branch_table_data, colWidths=[200, 140, 192])
        t1.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), primary_color),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, -1), light_bg),
            ('GRID', (0, 0), (-1, -1), 0.5, grid_color),
        ]))
        story.append(t1)
        story.append(Spacer(1, 15))

        # 4. Table 2: Top Performing Products Portfolio
        story.append(Paragraph("3. Product Sales Velocity Rankings", section_style))
        prod_table_data = [[Paragraph("Product Specification Name", header_cell_style), Paragraph("SKU Reference", header_cell_style), Paragraph("Units Dispatched", header_cell_style), Paragraph("Accumulated Income", header_cell_style)]]
        
        for item in catalog_data['top_performing_products']:
            prod_table_data.append([
                Paragraph(item['name'], body_style),
                Paragraph(item['sku'], body_style),
                Paragraph(str(item['units_sold']), body_style),
                Paragraph(f"KES {item['gross_revenue']:,.2f}", body_style)
            ])
            
        t2 = Table(prod_table_data, colWidths=[180, 110, 100, 142])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), primary_color),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('BACKGROUND', (0, 1), (-1, -1), light_bg),
            ('GRID', (0, 0), (-1, -1), 0.5, grid_color),
        ]))
        story.append(t2)
        story.append(Spacer(1, 15))

        # 5. Table 3: Flagged Critical Security Exceptions
        story.append(Paragraph("4. Real-Time Security & Override Escalations", section_style))
        risk_table_data = [[Paragraph("Timestamp", header_cell_style), Paragraph("Exception Trigger", header_cell_style), Paragraph("Accountable Profile", header_cell_style), Paragraph("Textual Audit Reason/Justification", header_cell_style)]]
        
        for risk in compliance_data['flagged_critical_incidents']:
            risk_table_data.append([
                Paragraph(risk['timestamp'].strftime('%Y-%m-%d %H:%M'), body_style),
                Paragraph(risk['action_type'], body_style),
                Paragraph(risk['initiator__email'], body_style),
                Paragraph(risk['justification_trail'], body_style)
            ])
            
        if len(risk_table_data) == 1:
            risk_table_data.append([Paragraph("No critical override exceptions flagged within this auditing window.", body_style), "", "", ""])

        t3 = Table(risk_table_data, colWidths=[90, 110, 120, 212])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), accent_warn),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('BACKGROUND', (0, 1), (-1, -1), light_bg),
            ('GRID', (0, 0), (-1, -1), 0.5, grid_color),
        ]))
        story.append(t3)

        # Build Document Schema Frame
        doc.build(story)
        buffer.seek(0)
        return buffer


class OperationsReportPDFGenerator:
    """Compact, human-readable PDF for the verified operations report."""

    @staticmethod
    def _page(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(36, 22, 'Emporium Plug - Internal management report')
        canvas.drawRightString(A4[0] - 36, 22, f'Page {doc.page}')
        canvas.restoreState()

    @classmethod
    def compile(cls, report):
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4, rightMargin=36, leftMargin=36,
            topMargin=36, bottomMargin=38,
            title='Emporium Plug Operations Report',
        )
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='ReportTitle', parent=styles['Title'], fontName='Helvetica-Bold',
            fontSize=20, leading=24, textColor=colors.HexColor('#0f172a'),
            spaceAfter=8,
        ))
        styles.add(ParagraphStyle(
            name='ReportMeta', parent=styles['BodyText'], fontSize=9, leading=13,
            textColor=colors.HexColor('#475569'), spaceAfter=10,
        ))
        styles.add(ParagraphStyle(
            name='ReportSection', parent=styles['Heading2'], fontName='Helvetica-Bold',
            fontSize=12, leading=15, textColor=colors.HexColor('#0f172a'),
            spaceBefore=12, spaceAfter=6,
        ))
        styles.add(ParagraphStyle(
            name='MoneyRight', parent=styles['BodyText'], alignment=TA_RIGHT,
            fontSize=9,
        ))
        story = [
            Paragraph('Emporium Plug Operations Report', styles['ReportTitle']),
            Paragraph(
                f"{report['definition']['branch']} | {report['definition']['start']} to "
                f"{report['definition']['end']} | {report['definition']['timezone']}",
                styles['ReportMeta'],
            ),
            Paragraph(report['definition']['revenue_basis'], styles['ReportMeta']),
        ]

        def table(rows, widths=None):
            result = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
            result.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            return result

        sales = report['sales']
        story.extend([
            Paragraph('Sales summary', styles['ReportSection']),
            table([
                ['Recognized revenue', 'Orders', 'Discounts', 'Delivery fees', 'Average order'],
                [f"KES {sales['revenue']}", str(sales['orders']), f"KES {sales['discounts']}",
                 f"KES {sales['delivery_fees']}", f"KES {sales['average_order']}"],
            ], [110, 70, 100, 100, 100]),
            Paragraph('Payment methods', styles['ReportSection']),
            table(
                [['Method', 'Orders', 'Amount (KES)']] + [
                    [row['payment_method'], str(row['order_count']), str(row['amount'])]
                    for row in sales['payment_breakdown']
                ], [210, 90, 150],
            ),
            Paragraph('Top products', styles['ReportSection']),
            table(
                [['Product', 'SKU', 'Units', 'Sales (KES)']] + [
                    [row['name'], row['sku'], str(row['units']), str(row['amount'])]
                    for row in report['products'][:15]
                ], [200, 100, 65, 100],
            ),
        ])
        controls = report['controls']
        story.extend([
            Paragraph('Operational controls', styles['ReportSection']),
            table([
                ['Voids', 'Manual payment checks', 'Failed/reconciliation', 'Unverified variances', 'Pending refunds'],
                [str(controls['voids']), str(controls['manual_payment_confirmations']),
                 str(controls['failed_or_reconciliation_payments']),
                 str(controls['unverified_shift_variances']),
                 str(report['promotions_returns']['pending_manual_refunds'])],
            ], [70, 105, 110, 105, 90]),
            Spacer(1, 8),
            Paragraph(report['definition']['returns_basis'], styles['ReportMeta']),
        ])
        doc.build(story, onFirstPage=cls._page, onLaterPages=cls._page)
        buffer.seek(0)
        return buffer
