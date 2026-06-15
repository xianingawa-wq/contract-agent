# Contract Agent

CLI contract review agent for identifying and explaining contract risks.

## MVP Direction

The first version will be a hybrid reviewer:

- A deterministic rule layer flags common contract risks.
- An optional LLM layer explains findings and suggests review comments.
- The CLI works with plain text contracts first, then can expand to Word/PDF later.
