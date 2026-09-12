# Business context

[简体中文](business-context.zh-CN.md) · [Home](../README.en.md)

Select a source in Data sources, then choose Business context in the preview area. Fill in and save:

- **Business notes**: coverage, usage conventions and exclusions.
- **Column descriptions**: `table.column`, display name, meaning, units and common values.
- **Metric definitions**: names, formulas, filters and date conventions.
- **Relationships**: join columns and one-to-many relationships within the source, including aggregation requirements.

For example: amount fields are cents; net revenue is paid non-test order amounts minus completed refunds, divided by 100. Aggregate refunds by order before joining to avoid double counting. Use multiline natural language; SQL is not required and user-entered text is not automatically translated.

## Saving and referencing

Saving confirms the definitions. Only content changes increment the version; saving identical content does not. Each AI analysis uses the snapshot captured at its start for planning, repairs and summaries. Changing definitions does not rewrite historical analyses.

Expand Business context vN beneath an analysis to inspect its original definitions. Markdown exports include the version and definitions too. Demo mode does not apply or claim to use business context. Unconfigured sources keep their normal analysis behavior.

## Scope

This is business-knowledge-assisted querying, not a semantic calculation engine. The model is instructed to clarify missing or conflicting definitions; verify important conclusions against executed SQL and results. Model guesses are never automatically saved as permanent knowledge. Cross-source querying remains unsupported. Remote AI receives these definitions: do not enter passwords or keys.

See the [evaluation guide](evaluation.en.md) for validation methodology.
