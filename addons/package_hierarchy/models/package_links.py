# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError


class PackageHierarchyLink(models.Model):
    _name = "package.hierarchy.link"
    _description = "Links for constructing package hierarchies"

    _parent_name = "parent_id"
    _parent_store = True
    _order = "id"

    name = fields.Char(index=True, store=True, compute="_compute_name")
    parent_path = fields.Char(index=True)
    parent_id = fields.Many2one(
        "stock.quant.package", string="Parent package", ondelete="cascade", check_company=True
    )
    child_id = fields.Many2one(
        "stock.quant.package", string="Child package", ondelete="cascade", check_company=True
    )
    move_line_ids = fields.Many2many(
        "stock.move.line",
        column1="link_id",
        column2="move_line_id",
        string="Stock move line",
        ondelete="cascade",
        check_company=True,
    )
    company_id = fields.Many2one("res.company", default=False)
    depth = fields.Integer(compute="_compute_would_be_depth")

    def construct(self):
        for parent_package, links in self.groupby("parent_id"):
            links.mapped("child_id").write(
                {"parent_id": parent_package.id if parent_package else False}
            )

    @api.model
    def create_top_level_unlinks(self, packages, move_lines=False):
        # Warm the cache
        packages.get_move_lines(aux_domain=[("id", "in", move_lines.ids)])
        link_vals = []
        # Create unlinks from higher level packages
        for top_level_pack in packages:
            if top_level_pack.parent_id:
                mls = top_level_pack.get_move_lines(aux_domain=[("id", "in", move_lines.ids)])
                link_vals.append(
                    {
                        "parent_id": False,
                        "child_id": top_level_pack.id,
                        "move_line_ids": [(6, 0, mls.ids if mls else False)],
                    }
                )

        if link_vals:
            return self.create(link_vals)
        return self.browse()

    @api.depends("parent_id", "child_id")
    def _compute_name(self):
        for link in self.filtered(lambda p: not isinstance(p.id, models.NewId)):
            link.name = (
                "Link %s and %s" % (link.parent_id.name, link.child_id.name)
                if link.parent_id and link.child_id
                else "Unlink parent of %s" % link.child_id.name
            )

    def _compute_would_be_depth(self):
        # TODO by checking children and parent pairs
        pass
