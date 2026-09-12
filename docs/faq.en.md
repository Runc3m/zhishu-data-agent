# FAQ

[简体中文](faq.zh-CN.md) · [Home](../README.en.md)

### Why a local address? Is a terminal needed?

127.0.0.1 means your own computer, not a public sharing link. Double-click `Zhishu.exe`; source scripts are for developers. Other users download the app and have separate data and settings.

### What if AI fails?

Test the connection in Model settings. HTTP 401 usually means an invalid key, 402 insufficient balance, 404 an incorrect custom endpoint/model, and 429 rate limits or quota. Retry timeouts later. Include version, steps and a redacted error in Issues, never keys or business records.

### Why are some questions unsupported?

Demo only covers predefined examples and simple follow-ups. AI queries the current source, not unconnected data or arbitrary files, and cannot execute code. Unclear questions or column meanings need clarification.

### How do I check numbers?

Inspect the executed SQL, result table and truncation notices. Results have up to 500 rows, charts up to 50 groups, and model summaries receive up to 30 rows. Sample records are synthetic, not real business performance.

### What about Excel, multiple files and collaboration?

Not currently supported. Export a single worksheet to CSV first. Future directions in the roadmap are not already implemented features.
