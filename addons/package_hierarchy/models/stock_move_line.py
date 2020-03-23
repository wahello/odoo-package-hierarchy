# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    u_result_package_link_ids = fields.Many2many(
        "package.hierarchy.link",
        column1="move_line_id",
        column2="link_id",
        string="Package hierarchy links",
    )

    def _action_done(self):
        """ When a move_line is done construct the package hierarchy."""
        Quant = self.env["stock.quant"]

        super(StockMoveLine, self)._action_done()

        for dest_location, move_lines in self.exists().groupby("location_dest_id"):
            move_lines.mapped("u_result_package_link_ids").construct()

    # TODO look at optimizing package move/movelines if all of parent is in the picking

    def construct_package_hierarchy_links(self):
        Package = self.env["stock.quant.package"]
        PackageHierarchyLink = self.env["package.hierarchy.link"]
        packages = Package.search([("id", "parent_of", self.mapped("package_id").ids)])
        packages_fulfilled = packages.filtered(lambda p: p.is_fulfilled_by(self))
        top_level_packages = packages_fulfilled.filtered(
            lambda p: p.parent_id not in packages_fulfilled
        )
        PackageHierarchyLink.create_top_level_unlinks(top_level_packages, self)
