# -*- coding: utf-8 -*-
from odoo import models, fields


class OCRDashboard(models.Model):
    _name = "ocr.dashboard"
    _description = "OCR Dashboard (Analytics)"

    name = fields.Char(string="Name", default="Clareo Dashboard")

    invoice_count = fields.Integer(compute="_compute_stats")
    receipt_count = fields.Integer(compute="_compute_stats")
    completed_count = fields.Integer(compute="_compute_stats")
    error_count = fields.Integer(compute="_compute_stats")
    avg_confidence = fields.Float(compute="_compute_stats")
    total_amount = fields.Float(compute="_compute_stats")

    def _compute_stats(self):
        Document = self.env["ocr.document"]
        for rec in self:
            invoices = Document.search([("doc_type", "=", "invoice")])
            receipts = Document.search([("doc_type", "=", "receipt")])
            completed = Document.search([("status", "=", "completed")])
            errors = Document.search([("status", "=", "error")])

            rec.invoice_count = len(invoices)
            rec.receipt_count = len(receipts)
            rec.completed_count = len(completed)
            rec.error_count = len(errors)
            rec.total_amount = sum(
                completed.mapped("total_amount")
            ) if completed else 0.0
            confidences = [
                d.confidence_score for d in completed if d.confidence_score
            ]
            rec.avg_confidence = (
                sum(confidences) / len(confidences) if confidences else 0.0
            )