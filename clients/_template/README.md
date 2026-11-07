# Client template

`python -m scripts.clients new <slug> --name "Client Name"` copies this folder to `clients/<slug>/`.

Before running anything for a new client:

1. **client.json** — fill in website, audience, core promise and competitors. Only add `proof_points` you can substantiate. Set `engagement.relationship` (`client`, `pilot` or `own-product`), `offer` and `status`.
2. **budgets.json** — set `target_cpa` from the client's real economics (what a customer is worth to them), and caps they have agreed to in writing.
3. Put the client's exports in `clients/<slug>/data/`. That folder is git-ignored: client data never enters the repo. Delete it after delivery.

Generated reports go to `clients/<slug>/reports/` (also git-ignored).
