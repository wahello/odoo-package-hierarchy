from odoo import fields, models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _check_entire_pack(self):
        super(StockPicking, self)._check_entire_pack()

    def _check_entire_pack(self):
        """Set u_result_parent_package_id when moving entire parent package."""
        super(StockPicking, self)._check_entire_pack()
        self.move_line_ids.construct_package_hierarchy_links()

