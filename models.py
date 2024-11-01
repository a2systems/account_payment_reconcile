from odoo import tools, models, fields, api, _
from odoo.exceptions import ValidationError
import openpyxl
import base64
from datetime import date,datetime

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    reconciliation_move_id = fields.Many2one('account.move',string='Asiento Conciliación')

    @api.model
    def account_payment_reconcile_cron(self):
        domain = [('state','=','posted'),('is_reconciled','=',False)]
        payments = self.env['account.payment'].search(domain)
        journal_code = self.env['ir.config_parameter'].sudo().get_param('PAYMENT_RECONCILE_JOURNAL','MISC')
        account_code = self.env['ir.config_parameter'].sudo().get_param('PAYMENT_RECONCILE_ACCOUNT','MISC')
        reconcile_amount = self.env['ir.config_parameter'].sudo().get_param('PAYMENT_RECONCILE_AMOUNT','1')
        for payment in payments:
            partner_account = payment.partner_id.property_account_receivable_id
            lines = payment.move_id.line_ids
            move_lines = self.env['account.move.line']
            for line in lines:
                if line.account_id.id == partner_account.id and abs(line.amount_residual) < float(reconcile_amount):
                    journal_id = self.env['account.journal'].search([('code','=',journal_code)],limit=1)
                    if not journal_id:
                        raise ValidationError('No hay diario MISC')
                    account_id = self.env['account.account'].search([('code','=',account_code)],limit=1)
                    if not account_id:
                        raise ValidationError('No hay cuenta %s'%(account_code))
                    vals_move = {
                            'ref': 'Asiento conciliación pago %s'%(payment.display_name),
                            'date': str(date.today()),
                            'journal_id': journal_id.id,
                            'move_type': 'entry',
                            'partner_id': payment.partner_id.id,
                            }
                    move_id = self.env['account.move'].create(vals_move)
                    amount = abs(line.amount_residual)
                    vals_debit = {
                            'move_id': move_id.id,
                            'account_id': partner_account.id,
                            'journal_id': move_id.journal_id.id,
                            'partner_id': payment.partner_id.id,
                            'name': 'Debito conciliacion pago %s'%(payment.name),
                            'debit': amount,
                            'credit': 0,
                            }
                    debit_id = self.env['account.move.line'].with_context({'check_move_validity': False}).create(vals_debit)
                    vals_credit = {
                            'move_id': move_id.id,
                            'account_id': account_id.id,
                            'journal_id': move_id.journal_id.id,
                            'partner_id': payment.partner_id.id,
                            'name': 'Credito conciliación pago %s'%(payment.name),
                            'debit': 0,
                            'credit': amount,
                            }
                    credit_id = self.env['account.move.line'].with_context({'check_move_validity': False}).create(vals_credit)
                    move_id.action_post()
                    move_lines += line
                    move_lines += debit_id
                    move_lines.reconcile()
                    payment.reconciliation_move_id = move_id.id
                    payment.message_post(body=_(('Asiento conciliacion %s creado y validado')%(move_id.name)))
                    self.env.cr.commit()
