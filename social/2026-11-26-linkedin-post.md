# LinkedIn post: CloudGini launch (draft, 2026-11-26)

Visual: carousel `carousel/cloudgini-carousel.pdf` (7 slides, 1080 × 1350; PNGs alongside). Upload as a document post.
1 lifecycle · 2 design · 3 overview · 4 evidence · 5 dry-run · 6 verification · 7 guard rails and status.
Screens are real captures of the app on the simulated estate (2026-11-26). Rebuild: `python3 social/make-carousel.py`.

---

A cost report that says "save this much a month" is easy to like and hard to check.

The figure often rests on a price the tool assumed, or on whichever week of metrics it happened to see.

In our AI Lab we built CloudGini, a prototype that looks for waste and security gaps in Google Cloud, and tries to be strict about what it doesn't know.

If memory metrics are missing, the item goes to manual review with no savings figure at all. Every number is labelled real or simulated, and estimated or verified.

Fixing things is deliberately narrow. There are five actions, each starts with a dry-run, needs a person's approval, and only counts as done after CloudGini reads the resource again.

In the demo, a firewall change that another tool quietly reverts ends as "failed", not "fixed".

The slides walk through the design and the real screens.

It's tested on a simulated estate (30 automated tests), not yet against a live project. The code is open:

https://infracraftlabs.com/lab/cloudgini/?utm_source=linkedin&utm_medium=organic_social&utm_campaign=cloudgini&utm_content=carousel_2026_11_26

https://github.com/infracraftlabs/cloudgini

How does your team check that a cost recommendation was right after the change?

#FinOps #GoogleCloud #CloudSecurity #DevOps

---

## Gate (docs/LINKEDIN-PLAYBOOK.md section 2)

- Opens with a relatable observation, reads as one story: yes.
- Detail after context, no bullets, no "you should": yes.
- Every number traceable: 5 actions, 30 tests (Lab page, repo README/tests). No savings figures quoted.
- Tested vs not tested stated: simulated estate only; live GCP not run.
- Visual built only from the project's facts: lifecycle, architecture, and real screenshots of the simulated demo.
- Length: about 175 words without links and hashtags.
