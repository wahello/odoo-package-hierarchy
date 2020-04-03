from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _check_entire_pack(self):
        """Set u_result_parent_package_id when moving entire parent package."""
        super(StockPicking, self)._check_entire_pack()
        self.move_line_ids.construct_package_hierarchy_links()

    def button_validate(self):
        self.ensure_one()
        max_package_depth = self.env.user.get_user_warehouse().u_max_package_depth
        # Validate all package links in picking
        links = self.move_line_ids.mapped("u_result_package_link_ids")

        children_count = {}
        for link in links:
            if link.child_id in children_count:
                children_count[link.child_id] = children_count[link.child_id] + 1
            else:
                children_count[link.child_id] = 1

        # Sanitize links, check for repeated children as we should not have any
        # Only exception may be moving a package from one package into another package. This will
        # create a 'un-link' (no-parent) and a 'link' (with parent).
        for child_id, count in children_count.items():
            if count == 2:
                repeated_links = links.filtered(lambda x: x.child_id == child_id)
                parent_ids = [link.parent_id.id for link in repeated_links]
                if parent_ids.count(False) != 1:
                    raise ValidationError(_("Package has several links associated with it."))
            elif count != 1:
                raise ValidationError(_("Package has several links associated with it."))

        # 1 Find terminal children and parents
        # 2 Follow each terminal child up the chain via links until it reaches a terminal parent
        # 3 Record the length of the chain and terminal child + parent > use later in validation
        # 4 Make sure that we traverse every link whilst looping over step 2/3, if links are missed
        # it indicates that a loop is present

        # 1 Get all children and parents (excluding unlinks as they do not impact these chains):
        links_excluding_unlinks = [link for link in links if link.parent_id]
        parents = set(link.parent_id for link in links_excluding_unlinks)
        children = set(link.child_id for link in links_excluding_unlinks)
        terminal_parents = parents - children
        terminal_children = children - parents

        links_checked = {link: False for link in links_excluding_unlinks}
        chains_to_check = []

        for child in terminal_children:
            chain_length = 2
            current_link = next((link for link in links_excluding_unlinks if link.child_id == child), None)
            while chain_length <= max_package_depth:
                links_checked[current_link] = True
                print(chain_length, current_link)
                parent = current_link.parent_id
                if parent in terminal_parents:
                    chains_to_check.append({'chain_length': chain_length, 'parent': parent, 'child': child})
                    break
                else:
                    current_link = next((link for link in links_excluding_unlinks if link.child_id == parent), None)
                    chain_length += 1
            if chain_length > max_package_depth:
                raise ValidationError(_("Proposed move line(s) would cause package depth to exceed maximum permitted"))

        if False in links_checked.values():
            raise ValidationError(_("Proposed move line(s) would result in a package loop"))

        for chain in chains_to_check:
            # Check for self-ancestors
            current_ancestors = chain["parent"]._return_ancestors()
            if chain["child"] in current_ancestors:
                raise ValidationError(_("Proposed move line(s) would result in a package loop"))

            # Check the depth of the proposed tree
            if next((link for link in links if link.child_id == chain["parent"] and not link.parent_id), False):
                length_above = 0
            else:
                length_above = chain["parent"]._return_num_ancestors()
            child_package = chain["child"]
            length_below = child_package.depth - 1
            total_length = length_above + length_below + chain["chain_length"]
            if total_length > max_package_depth:
                raise ValidationError(_("Proposed move line(s) would cause package depth to exceed maximum permitted"))

        res = super(StockPicking, self).button_validate()
        return res
