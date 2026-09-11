# Lists

Lists are standalone, reusable checklists. They are not to-dos, projects, or a shopping-list-specific data model.

- A list can have an optional description, favourite state, archive state, completion state, sections, active items, and retained completed items.
- Completing the final item moves a list to Completed automatically. A list can also be completed early, and reopened later without changing its item checkboxes.
- Deleting a section deliberately moves its items to the unsectioned area; it never deletes them.
- Templates are blueprints only. Starting a list from a template, or duplicating a list, makes an independent copy of sections, item details, and order.
- `checklists`, `list_sections`, `list_items`, `list_templates`, `list_template_sections`, and `list_template_items` are intentionally neutral, portable table names with no ownership column.

Universal Search indexes list names, list item text and details, and template names. Completed and archived matches remain discoverable at lower priority.

Lists is an Online Stage 2B / later feature: its schema is portable and compiles for PostgreSQL, but no cloud account, data migration, or deployment is part of this work.
