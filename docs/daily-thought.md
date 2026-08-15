# Something to think about

The Hub’s daily card is an offline, curated library in `app/data/daily_thoughts.json`. It has seven fixed weekday categories and uses a deterministic week-based index, so the same date always shows the same entry without a database write or external request.

To add an entry, add a unique `id` to the relevant category with non-empty `title`, `body`, and `think_about`. Optional sources require both `source_name` and an HTTPS `source_url`. The validation tests require at least eight entries in every category.

This is a passive Hub experiment only. It does not create a Growth section, use AI or an API, store user data, or add interaction controls.
