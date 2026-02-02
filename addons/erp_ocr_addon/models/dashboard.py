from odoo import models, fields, api

class OcrDashboard(models.TransientModel):
    _name = 'ocr.dashboard'
    _description = 'OCR Dashboard'

    name = fields.Char(string="Name", default="OCR Dashboard")

    # --- KPIs ---
    invoice_count = fields.Integer(compute='_compute_kpis')
    receipt_count = fields.Integer(compute='_compute_kpis')
    failed_count = fields.Integer(compute='_compute_kpis')
    
    # Financials
    total_processed_value = fields.Float(string="Total Value", compute='_compute_kpis')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    # --- Recent Activity List ---
    recent_document_ids = fields.Many2many('ocr.document', compute='_compute_recent')

    def _compute_kpis(self):
        for record in self:
            Document = self.env['ocr.document']
            
            # FIXED: Using 'doc_type'
            record.invoice_count = Document.search_count([('doc_type', '=', 'invoice')])
            record.receipt_count = Document.search_count([('doc_type', '=', 'receipt')])
            record.failed_count = Document.search_count([('state', '=', 'failed')])
            
            # Financials
            docs_processed = Document.search([('state', 'in', ['done', 'reviewed'])])
            record.total_processed_value = sum(d.total_incl_tax for d in docs_processed)

    def _compute_recent(self):
        for record in self:
            # Load last 10 documents regardless of status
            record.recent_document_ids = self.env['ocr.document'].search(
                [], order='create_date desc', limit=10
            )

    # --- Actions ---
    def action_open_invoices(self):
        return self._open_action('Invoices', [('doc_type', '=', 'invoice')]) # FIXED

    def action_open_receipts(self):
        return self._open_action('Receipts', [('doc_type', '=', 'receipt')]) # FIXED

    def action_open_failed(self):
        return self._open_action('Failed Documents', [('state', '=', 'failed')])

    def _open_action(self, name, domain):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'ocr.document',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {'create': False},
        }

    @api.model
    def action_get_dashboard(self):
        res_id = self.create({}).id
        return {
            'name': 'Dashboard',
            'res_model': 'ocr.dashboard',
            'view_mode': 'form',
            'res_id': res_id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }