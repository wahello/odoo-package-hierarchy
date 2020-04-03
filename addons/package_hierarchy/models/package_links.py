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
    parent_left = fields.Integer('Left Parent', index=True)
    parent_right = fields.Integer('Left Parent', index=True)

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




    @api.constrains("parent_id", "child_id")
    @api.onchange("parent_id", "child_id")
    def _constrain_link_tree(self):
        """
        TODO: Need to check all links in self:
        First check if there are two links in self with the same child:
        this may occur if a package is unlinked and re-linked elsewhere
        in this case delete the link with no parent. If >2 links or if
        one does not have a null parent, error.
        Then need to create chains from all links in self.
        We then need to create the prospective package tree using these links as building blocks
        This needs to consider any chains are in the same tree that aren't directly linked
        It also needs to consider a check for self ancestors (infinite chains)
        Finally from this (or during this) we can check on our constraints such as depth

        Assumptions:
        - All links for a pick are created at once (allows us to loop through self)
        - We do not need to check the links for every other pick (could be very expensive)
        """
        max_package_depth = self.env.user.get_user_warehouse().u_max_package_depth

        # Sanitize links, check for repeated children as we should not have repeated children
        # Only exception may be moving a package from one package into another package. This will
        # create a 'un-link' (no-parent) and a 'link' (with parent). In this case we may remove
        # the un-link.
        children_count = {link: self.count(link.child_id) for link in self}
        for key, value in children_count:
            if value > 2:
                raise ValidationError(_("Package is being moved to several different packages."))
            elif value == 2:
                repeated_links = self.filtered(lambda x: x.child_id == key)
                if not any(link.parent_id is None for link in repeated_links):
                    raise ValidationError(_("Package is being moved to several different packages."))
                for link in repeated_links:
                    # Remove parentless link from self
                    if link.parent_id is None:
                        self.remove(link)
                        exit()

        # Next create chains of links in self, being careful of self-ancestors (infinite loops)


        # Extend these chains to create full trees from existing package heirachy, and linking
        # in chains when relevant. This may end up with one full tree for each chain or multiple of
        # these chains could exist in the same tree. Again be wary of infinite loops.






    # Functions below were the first draft but are not up to scrath as they only take the existing
    # tree into account and not how links may interact with one another. Leaving here for reference

    # @api.depends("child_id", "child_id.depth")
    # def _compute_would_be_depth(self):
    #     for link in self:
    #         if link.child_id:
    #             link.depth = link.child_id.depth
    #         else:
    #             link.depth = 0

    # @api.constrains("parent_id", "child_id")
    # @api.onchange("parent_id", "child_id")
    # def _constrain_would_be_depth(self):
    #     max_package_depth = self.env.user.get_user_warehouse().u_max_package_depth
    #     for link in self:
    #         if link.parent_id:
    #             num_ancestors = link.parent_id._return_num_ancestors() + 1
    #         else:
    #             num_ancestors = 0
    #         total_depth = num_ancestors + link.depth
    #         if total_depth > max_package_depth:
    #             raise ValidationError(_("Maximum package depth would be exceeded."))

    # @api.constrains("parent_id", "child_id")
    # @api.onchange("parent_id", "child_id")
    # def _constrain_self_ancestor(self):
    #     """Prevent packages from being their own ancestors."""
    #     for link in self:
    #         ancestor = link.parent_id
    #         child_pack = link.child_id
    #         while ancestor:
    #             if child_pack.id == ancestor.id:
    #                 raise ValidationError(_("Package would be an ancestor of itself."))
    #             else:
    #                 ancestor = ancestor.parent_id
