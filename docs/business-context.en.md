# Business context

[简体中文](business-context.zh-CN.md) · [Home](../README.en.md)

Select a source in Data sources, then choose Business context in the preview area. Fill in and save:

- **Business notes**: coverage, usage conventions and exclusions.
- **Column descriptions**: `table.column`, display name, meaning, units and common values.
- **Metric definitions**: names, formulas, filters and date conventions.
- **Relationships**: join columns and one-to-many relationships within the source, including aggregation requirements.

Draft from data values, under Column descriptions, reads each column's distinct count and range, plus actual values for text columns with at most 12 distinct values, and appends them to the box. Drafts are neither saved automatically nor sent to a model. Columns whose names suggest personal data, such as names, phones, emails or addresses, have their values skipped. Remove what you do not need, add meanings and units, then save.

For example: amount fields are cents; net revenue is paid non-test order amounts minus completed refunds, divided by 100. Aggregate refunds by order before joining to avoid double counting. Use multiline natural language; SQL is not required and user-entered text is not automatically translated.

## Saving and referencing

Saving confirms the definitions. Only content changes increment the version; saving identical content does not. Each AI analysis uses the snapshot captured at its start for planning, repairs and summaries. Changing definitions does not rewrite historical analyses.

Expand Business context vN beneath an analysis to inspect its original definitions. Markdown exports include the version and definitions too. The original sales demo does not apply or claim to use business context; see below for the commerce investigation demo. Unconfigured sources keep their normal analysis behavior.

## Verified queries

Mark as correct, at the top right of an analysis result, saves that SQL as a verified query. Rewrite the question as a standalone question first, for example turning the follow-up “What about profit?” into “Compare profit by region”. Verifying the same question again replaces its SQL; each source keeps up to 200.

During AI analysis, Zhishu finds up to 3 verified queries in the current source with similar wording and gives them to the model as examples with their SQL. Expand “Used N verified queries as reference” beneath an analysis to see them. Examples are references only; the current schema and business definitions win when they conflict. SQL is revalidated against the current schema when verified. Demo mode does not use examples. View and delete verified queries at the bottom of the Business context window.

## Scope

This is business-knowledge-assisted querying, not a semantic calculation engine. The model is instructed to clarify missing or conflicting definitions; verify important conclusions against executed SQL and results. Model guesses are never automatically saved as permanent knowledge. Cross-source querying remains unsupported. Remote AI receives these definitions: do not enter passwords or keys.

See the [evaluation guide](evaluation.en.md) for validation methodology.

## Retrieval and investigation

The development edition combines BM25 with local multilingual E5 embeddings. Metric and relationship constraints remain mandatory; field descriptions are retrieved selectively. Full snapshots remain in history rather than being injected wholesale. Imported structured metrics are excluded after a context revision to avoid stale formulas. AI investigations use one immutable snapshot throughout. The original rule demo does not use business context; the new commerce demo executes its built-in definitions only and requires AI after definitions change.
