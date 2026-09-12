# Model setup

[简体中文](models.zh-CN.md) · [Home](../README.en.md)

## DeepSeek

Choose AI analysis in Model settings, keep DeepSeek selected, enter your own API key and select Verify and enable. The preset supplies the official endpoint and model. A connection test verifies availability, not correctness of every analysis.

Keys are encrypted locally; leave the field empty later to retain the saved value. Changing provider or custom endpoint requires the corresponding key and does not automatically send the old key to a new address. Demo mode offers an explicit option to clear the saved key.

## Other services and local models

Select Other compatible service / local model, supply the base URL and exact model name, and use a `/chat/completions`-compatible endpoint. Local Ollama, for example, uses `http://localhost:11434/v1` and the installed model name. Remote endpoints require HTTPS; local models without authentication can leave the key empty. Compatibility does not guarantee reliable planning from every model.

## Data flow and responses

Planning sends questions, schema and up to 10 recent messages; summarization sends SQL, column names and up to 30 result rows. Database credentials and local file paths are not model context. Follow your organization’s data policies when selecting providers.

The interface language is the default response language; explicitly request another language in your question if needed. Each analysis uses the language captured at its start. Model outputs may be wrong: verify SQL and data before business use. Providers charge API fees; demo mode does not call a model.
