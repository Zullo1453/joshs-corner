# Something to think about

The Hub’s daily card is an offline, curated library in `app/data/daily_thoughts.json`. It has 371 entries: 53 in each of seven fixed weekday categories. The deterministic ordinal-week index means the same date always shows the same entry, and a category completes 53 weekly occurrences before repeating, without a database write or external request.

To add or replace an entry, use a unique `id` in the relevant category with non-empty `title`, `body`, and `think_about`. Optional sources require both `source_name` and an HTTPS `source_url`; factual entries should use a reputable primary, academic, museum, government, or reference source wherever practical. `audit_library()` reports the total plus sourced and unsourced counts by category. The validation tests require exactly 53 entries in every category.

This is a passive Hub experiment only. It does not create a Growth section, use AI or an API, store user data, or add interaction controls.
