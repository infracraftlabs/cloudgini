#!/usr/bin/env python3
"""Estimate the monthly running cost of infra/terraform/demo from Google's Cloud Billing Catalog API
(list prices, before discounts and free tier). Needs `gcloud auth login`; makes read-only calls only.

    python3 scripts/demo-cost.py --region europe-west1

It prints every SKU it matched so you can check them. Confirm the total in the Google Cloud Pricing
Calculator before `terraform apply`.
"""
import argparse
import json
import subprocess
import urllib.parse
import urllib.request

HOURS = 730  # hours per month used by Google's calculator
# (label, service display name, SKU description must contain, unit quantity per month)
BOM = [
    ("e2-standard-4 vCPU (4 x 730 h)", "Compute Engine", "E2 Instance Core", 4 * HOURS),
    ("e2-standard-4 RAM (16 GB x 730 h)", "Compute Engine", "E2 Instance Ram", 16 * HOURS),
    ("e2-standard-2 vCPU (2 x 730 h)", "Compute Engine", "E2 Instance Core", 2 * HOURS),
    ("e2-standard-2 RAM (8 GB x 730 h)", "Compute Engine", "E2 Instance Ram", 8 * HOURS),
    ("Boot disks pd-standard (2 x 10 GB)", "Compute Engine", "Storage PD Capacity", 20),
    ("Big disk pd-ssd (100 GB)", "Compute Engine", "SSD backed PD Capacity", 100),
    ("Unattached disk pd-standard (50 GB)", "Compute Engine", "Storage PD Capacity", 50),
    ("Snapshot (up to 50 GB)", "Compute Engine", "Storage PD Snapshot", 50),
    ("Unused static IP (730 h)", "Compute Engine", "Static Ip Charge", HOURS),
    ("Bucket (<1 MB)", "Cloud Storage", "Standard Storage", 0.001),
]


def get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def all_pages(url, token, key):
    out, page = [], ""
    while True:
        sep = "&" if "?" in url else "?"
        data = get(f"{url}{sep}pageSize=5000" + (f"&pageToken={urllib.parse.quote(page)}" if page else ""), token)
        out += data.get(key, [])
        page = data.get("nextPageToken")
        if not page:
            return out


def unit_price(sku):
    expr = sku["pricingInfo"][0]["pricingExpression"]
    tiers = expr["tieredRates"]
    rate = tiers[-1]["unitPrice"]  # highest tier = price after any free tier
    return int(rate.get("units", 0)) + rate.get("nanos", 0) / 1e9, expr["usageUnit"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="europe-west1")
    args = ap.parse_args()
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    base = "https://cloudbilling.googleapis.com/v1"
    services = {s["displayName"]: s["name"] for s in all_pages(f"{base}/services", token, "services")}
    skus = {}
    total = 0.0
    for label, service, needle, qty in BOM:
        if service not in skus:
            skus[service] = all_pages(f"{base}/{services[service]}/skus?currencyCode=USD", token, "skus")
        matches = [s for s in skus[service]
                   if needle.lower() in s["description"].lower() and args.region in s.get("serviceRegions", [])
                   and s["category"].get("usageType") == "OnDemand" and "Preemptible" not in s["description"]
                   and "Spot" not in s["description"] and "Sole Tenancy" not in s["description"]
                   and "Custom" not in s["description"]]
        if len(matches) != 1:
            print(f"?? {label}: {len(matches)} SKUs matched '{needle}' in {args.region}; check manually:",
                  [m["description"] for m in matches][:5])
            continue
        price, unit = unit_price(matches[0])
        cost = price * qty  # quantities above are in the SKU units: h, GiBy.h, GiBy.mo
        total += cost
        print(f"{label:42} {matches[0]['description'][:50]:50} {price:.6f} USD/{unit}  = {cost:8.2f} USD/month")
    print(f"\nEstimated list-price total: {total:.2f} USD/month (about {total / 30:.2f} USD/day), before discounts and free tier.")


if __name__ == "__main__":
    main()
