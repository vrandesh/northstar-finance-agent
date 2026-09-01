
# Done (the essential foundation)
* Clear, well-defined formats for requests, tools, and the final recommendation — so nothing is ambiguous.
* Search system (BM25) that separates "results that came back" from "results that are actually trustworthy enough to use."
* A rule-based decision engine that checks for: duplicate entries, signs of fraud/tampering, whether the vendor is valid, whether the amounts match across documents (within allowed tolerance), and whether the source is trustworthy enough. Every rule and number is hard-coded, and every decision points to the evidence behind it.
* A workflow (LangGraph) that pauses for human in the loop for approval, can be safely resumed if interrupted, and won't run forever (has a step limit). LLM behind an adapter (fake by default), used only to explain; validated with a deterministic fallback; **no outcome authority**.
* The AI model is used only to explain decisions in plain language — not to make them. It's swappable, has a backup fallback if it fails, and by default runs in test mode. It has no power to change the outcome.
* All data is saved in a local database (SQLite): the state of each run, a full history log, a record to prevent duplicate actions, and approval records. Bank details are hidden/masked for safety.
* Guardrails to prevent conflicting updates and to double-check everything is still valid right before final approval.

# Not Done 
* Foreign Currency Tool implementation
* Cloud Deployment for either Azure / AWS via IaC (preferred choice of deployment) with proper CI/CD implementation
* No Auth on the endpoints, Happy to integrate this with either AWS IAM or Azure Entra app registration provided there is a oAuth Implementation for users and groups
* No clear formatting fix yet. Would love to do this asap. 
* Provide a Visual Interface to this whole workflow agent that can help achieve results since, Seeing is believing. 
* Visual Interface for Gating mechanism (Approval Mechanism by Stakeholders)

## How AI was used

An AI assistant reviewed the design, suggested edge cases, and served as a (AI Assisted) test suite I checked my own outputs against. 
