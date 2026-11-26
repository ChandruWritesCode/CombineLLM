# Phase 8: provider discovery and guided setup

Model coordination moves to Phase 9. Phase 8 adds **Find a model** at `/discover`,
a searchable curated directory with dated official sources, offer classifications,
provider-specific walkthroughs, account/key links and prefilled connection setup.

## Directory coverage

The checked directory contains Groq, Google Gemini/Gemma, OpenRouter, Cloudflare
Workers AI, Cohere, Cerebras, NVIDIA API Catalog, Mistral and local Ollama. This is
not an exhaustive inventory of the internet. Regional offers and promotions can
change faster than releases. The checked date is a documentation review date, not
a successful live-inference test or a guarantee of account eligibility.

Recurring free allocations, selected free models, evaluation keys, expiring trials,
conditional offers and local hardware are labeled separately. Cerebras currently
requires a verified payment method for trial credits. Mistral eligibility must be
confirmed in the account console. NVIDIA is evaluation access under trial terms.
GitHub Models, Hugging Face free-account inference credits and SambaNova's former
free access are explicitly excluded based on the official sources linked in-app.

The source of truth is `app/static/provider-catalog.json`. Each entry includes
an official signup/documentation link, offer category, review date, guide and
adapter preset. Review official terms before updating entries. Never infer a free
API entitlement from a free chat website or a freely generated API key.

## User walkthrough

1. Open Find a model, search a provider and read its offer/eligibility notes.
2. Open its official account/key page. The user signs up, accepts any terms and
   creates their own credential. CombineLLM does not automate account creation.
3. Choose Set up this provider. Review the endpoint and available model ID. Sample
   IDs may be retired or unavailable to a particular account. Providers without
   a reliable default require entering the model from their console.
4. Paste the key into the password field and save. The existing encrypted registry
   is used; the key is not kept in localStorage, URLs or the provider catalog.
   Closing the setup dialog clears the field. Saving makes no inference request.
5. Optionally confirm Test connection. The greeting can consume quota or credits;
   failures leave the saved connection available for correction in Settings.
6. Select the new connection in chat. Workspace defaults and fallback order stay
   unchanged. OpenRouter users can save without a key and connect their account
   through the existing Settings login option.

Cloudflare requires replacing ACCOUNT_ID in its base URL and a Workers AI token.
Ollama requires a running local server and an installed text model. Docker's host
address differs from native localhost; the guide explains both. All cloud guides
use existing text adapters; custom protocols, tools and multimodal support are
not introduced. Most compatible presets omit optional stream usage reporting to
avoid unsupported parameters; users can enable it in Settings.

## Cost, privacy and validation

No price is automatically set to zero. Free eligibility is provider/account-specific,
and advisory budgets do not block spending. Provider prompts leave the machine;
review each provider's data policy before testing. No existing credential is copied
to a different provider. The guide never downloads models or installs software.

Tests validate catalog structure, URLs, connection schema compatibility, route
availability, encrypted-secret redaction and that saving does not call a provider
or alter defaults. JavaScript syntax and deployment checks complement backend tests.
Live availability of every directory entry is not verified.

Release validation: 80 tests passed; Ruff lint/format, JavaScript syntax and Compose
configuration checks passed. Docker rebuilt and reported healthy. No schema
migration was required. Live inference was not verified across the directory.
