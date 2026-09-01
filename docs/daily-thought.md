# Something to think about

The Hub’s daily card is an offline, curated micro-lesson library in app/data/daily_thoughts.json. It currently contains 56 lessons: eight in each of seven fixed weekday categories. The deterministic ordinal-week index means the same date always shows the same entry; the 8-week category rotation is local and requires no database write or external request.

## Lesson schema and quality bar

Every entry has a unique id, valid category, title, what_it_is, why_it_matters, optional example, concept-specific think_about, source_name, and HTTPS source_url. HTML is not stored or rendered. Lessons target roughly 100–160 words of visible teaching content and should explain a concept, its consequence, and a concrete case—not merely call it important.

Write the sections to suit the category: use mechanisms and application for product, economics, and science; context and historical connection for history; evidence or caveat for psychology; explanation and surprise for facts; and context and application for philosophy. The source must be a relevant deep link to the actual supporting page, paper, or institutional explanation. Replace an entry when no such source is available.

## Presentation and review

Wide Hub cards use two compact columns for labelled sections; at narrow widths they stack without shrinking the text or causing horizontal scroll. The teal panel, radius, and placement remain unchanged.

Before release, run audit_library() and review every entry for clear explanation, concrete significance, useful example where appropriate, unique Think about question, and direct source relevance. The audit reports coverage, duplicate explanations/questions, near-duplicate titles, and templated-question patterns; it is a structural prompt for human review, not proof that a source is relevant.
