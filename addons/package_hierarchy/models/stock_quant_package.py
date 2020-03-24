"""Packages with inheritance."""

import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_is_zero

_logger = logging.getLogger(__name__)


class QuantPackage(models.Model):
    """ Add the ability for a package to contain another package """

    _inherit = "stock.quant.package"
    _parent_name = "parent_id"
    _parent_order = "name"
    _order = "id"

    display_name = fields.Char("Display Name", compute="_compute_display_name")
    parent_id = fields.Many2one(
        "stock.quant.package",
        "Parent Package",
        ondelete="restrict",
        help="The package containing this item",
    )
    top_parent_id = fields.Many2one(
        "stock.quant.package", compute="_compute_top_parent_id", store=True
    )

    children_quant_ids = fields.One2many(
        "stock.quant", string="All content", compute="_compute_children_quant_ids"
    )
    children_ids = fields.One2many("stock.quant.package", "parent_id", "Contained Packages")
    depth = fields.Integer(compute="_compute_depth", store=True)

    @api.depends("parent_id")
    def _compute_top_parent_id(self):
        for pack in self:
            parent = pack.parent_id

            if not parent:
                pack.top_parent_id = False
            elif parent.top_parent_id:
                pack.top_parent_id = parent.top_parent_id
            else:
                pack.top_parent_id = parent

    @api.constrains("parent_id", "children_ids")
    @api.onchange("parent_id", "children_ids")
    def _constrain_depth(self):
        max_package_depth = self.env.user.get_user_warehouse().u_max_package_depth
        for pack in self:
            top_parent = pack.top_parent_id or pack.parent_id
            if top_parent.depth > max_package_depth:
                raise ValidationError(_("Maximum package depth exceeded."))

    @api.depends("children_ids", "children_ids.depth")
    def _compute_depth(self):
        """Is the max depth of any children"""
        for pack in self:
            children = pack.children_ids

            if not children:
                pack.depth = 1
            else:
                pack.depth = max(pack.children_ids.mapped("depth")) + 1

    @api.constrains("parent_id")
    def _check_parent_not_multi_location(self):
        for parent_package in self.mapped("parent_id"):
            parent_package._check_not_multi_location()

    @api.constrains("parent_id")
    def _check_package_recursion(self):
        if not self._check_recursion("parent_id"):
            raise ValidationError("A package cannot be its own ancestor.")

    def _check_not_multi_location(self):
        for package in self:
            locations = package.children_quant_ids.mapped("location_id")
            if len(locations) > 1:
                raise ValidationError(
                    _("Package cannot be in multiple " "locations:\n%s\n%s")
                    % (package.name, ", ".join([l.name for l in locations]))
                )

    @api.depends(
        "parent_id", "children_ids", "quant_ids.package_id",
    )
    def _compute_children_quant_ids(self):
        for package in self:
            if isinstance(package.id, models.NewId):
                package.children_quant_ids = []
            else:
                package._check_not_multi_location()
                package.children_quant_ids = self.env["stock.quant"].search(
                    [
                        ("package_id", "child_of", package.id),
                        "|",
                        ("quantity", "!=", 0),
                        ("reserved_quantity", "!=", 0),
                    ]
                )

    @api.depends(
        "quant_ids.package_id",
        "quant_ids.location_id",
        "quant_ids.company_id",
        "quant_ids.owner_id",
        "quant_ids.quantity",
        "quant_ids.reserved_quantity",
    )
    def _compute_package_info(self):
        for package in self:
            values = {
                "location_id": False,
                "owner_id": False,
            }

            comparison_recs = False

            if package.quant_ids:
                comparison_recs = package.quant_ids
            elif package.children_ids:
                comparison_recs = package.children_ids

            if comparison_recs:
                values["location_id"] = comparison_recs[0].location_id
                if all(q.owner_id == comparison_recs[0].owner_id for q in comparison_recs):
                    values["owner_id"] = comparison_recs[0].owner_id
                if all(q.company_id == comparison_recs[0].company_id for q in comparison_recs):
                    values["company_id"] = comparison_recs[0].company_id

            package.location_id = values["location_id"]
            package.company_id = values.get("company_id")
            package.owner_id = values["owner_id"]

    @api.depends("parent_id")
    def _compute_display_name(self):
        """Compute the display name for a package. Include name of immediate parent."""
        for package in self:
            if package.parent_id:
                package.display_name = "%s/%s" % (package.parent_id.name, package.name)
            else:
                package.display_name = package.name

    # def is_all_contents_in(self, rs):
    #     """See if the entire contents of a package is in recordset rs.
    #     rs can be a recordset of quants or packages.
    #     """
    #     for rec in rs:
    #         if rs._name == "stock.quant":
    #             compare_rs = rec.children_quant_ids
    #         elif rs._name == "stock.quant.package":
    #             compare_rs = rec.children_ids
    #         else:
    #             msg = "Expected stock.quant or stock.quant.package, got %s instead."
    #             raise ValidationError(_(msg) % rs._name)
    #         if not all([a in rs for a in compare_rs]):
    #             return Falserelation
    def _get_contained_quants(self):
        """Overide to include picks quants of child packages"""
        return self.env["stock.quant"].search([("package_id", "child_of", self.ids)])

    def _get_move_lines_domain(self):
        return [
            "|",
            ("result_package_id", "child_of", self.ids),
            ("package_id", "child_of", self.ids),
        ]

    def get_move_lines(self, aux_domain=None, **kwargs):
        MoveLines = self.env["stock.move.line"]
        domain = self._get_move_lines_domain()
        if aux_domain:
            domain.extend(aux_domain)
        return MoveLines.search(domain, **kwargs)

    def action_view_picking(self):
        """Overide to include picks of child packages"""
        action = self.env.ref("stock.action_picking_tree_all").read()[0]
        domain = self._get_move_lines_domain()
        pickings = self.env["stock.move.line"].search(domain).mapped("picking_id")
        action["domain"] = [("id", "in", pickings.ids)]
        return action

    def product_quantities_by_key(self, get_key=lambda q: q.product_id):
        """This function computes the product quantities the given package grouped by a key
            Args:
                get_key: a callable which takes a quant and returns the key

        """
        res = {}
        for key, quant_grp in self._get_contained_quants().groupby(get_key):
            res[key] = sum(quant_grp.mapped("quantity"))
        return res

    def is_fulfilled_by(self, move_lines):
        """ Check if a set of packages are fulfilled by a set of move lines"""
        Precision = self.env["decimal.precision"]

        def get_key(x):
            return (x.product_id, x.lot_id)

        precision_digits = Precision.precision_get("Product Unit of Measure")
        pack_qtys = self.product_quantities_by_key(get_key)
        pack_move_lines = self.get_move_lines(aux_domain=[("id", "in", move_lines.ids)])

        mls_qtys = {}
        for key, mls_grp in pack_move_lines.groupby(get_key):
            mls_qtys[key] = sum(mls_grp.mapped("product_qty"))

        # How do we want to deal with the case where the mls have more than the package has?
        # ATM we say it doesn't fulfill which is not quite right
        for key in set(pack_qtys.keys()) | set(mls_qtys.keys()):
            if not float_is_zero(
                pack_qtys.get(key, 0) - mls_qtys.get(key, 0), precision_digits=precision_digits
            ):
                return False
        return True
