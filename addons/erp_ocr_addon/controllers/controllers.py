# -*- coding: utf-8 -*-
# from odoo import http


# class ErpOcrAddon(http.Controller):
#     @http.route('/erp_ocr_addon/erp_ocr_addon', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/erp_ocr_addon/erp_ocr_addon/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('erp_ocr_addon.listing', {
#             'root': '/erp_ocr_addon/erp_ocr_addon',
#             'objects': http.request.env['erp_ocr_addon.erp_ocr_addon'].search([]),
#         })

#     @http.route('/erp_ocr_addon/erp_ocr_addon/objects/<model("erp_ocr_addon.erp_ocr_addon"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('erp_ocr_addon.object', {
#             'object': obj
#         })

