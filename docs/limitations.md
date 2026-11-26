# Known limitations

Honest list for v0.1 (prototype).

- **GCP adapter not yet run against a live project.** Its mapping is tested on fixtures shaped like
  Asset Inventory output, and every SDK call was checked against the installed client libraries,
  but nothing has been run against real GCP yet. Expect fixes on the first real scan.
- **Verified savings are not produced.** The `verified` basis exists, but comparing billing before
  and after a change isn't implemented. All figures are estimated or absent.
- **GCP savings are narrow on purpose.** Only VM and Cloud SQL resizing (vCPU ratio of the billed
  cost), stopping VMs and removing whole resources get a figure. Disk type and storage class changes
  need list prices, which CloudGini doesn't guess, so they show no figure on GCP.
- **Billing to resource mapping.** Needs the *detailed* (resource-level) billing export. VM rows are
  mapped from numeric instance IDs; other resource types match on `resource.global_name` and may not
  match every service.
- **Utilisation windows.** VM right-sizing needs 14 days of CPU **and** memory metrics (memory needs
  the Ops Agent). Until then the item is "requires manual review" with no figure.
- **Snapshot schedules** and some dependencies (e.g. DNS records pointing at an IP) are not read;
  the UI marks such checks as unknown or tells you to check them.
- **Simulated estate** has a fixed shape and lives in process memory; restarting the backend resets it.
- **Single instance.** Rate limiting and the simulated estate are in memory.
- **Identity** is per API key, not per person; no SSO.
- **AWS and Azure** are not implemented; the provider interfaces are ready for them.
- **No compliance mapping.** The ten checks are configuration checks, not CIS, SOC 2 or similar.
