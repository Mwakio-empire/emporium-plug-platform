# Image-search decision

Decision: defer visual similarity search until after the reliable client MVP launches.

It is feasible, but a customer photo cannot reliably identify an exact product. A responsible implementation would:

- accept a tightly validated, short-lived image upload;
- generate an image embedding;
- search embeddings for active catalog images, probably using PostgreSQL `pgvector` at this scale;
- combine visual similarity with category, price and in-stock filters;
- label results as similar matches and retain text/category search;
- avoid facial/location metadata retention and document deletion timing;
- measure top-5 relevance against real catalog/customer examples.

Prerequisites are consistent product photography, sufficient catalog size, approved upload privacy/retention and measured customer demand. Start with staff-assisted WhatsApp image enquiries and track volume; build the feature only if the evidence justifies its cost.
