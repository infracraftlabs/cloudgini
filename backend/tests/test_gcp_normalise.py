"""The GCP adapter's mapping from Cloud Asset Inventory records, on a small recorded-style fixture
(synthetic values in the shape the API returns). No network calls."""
from app.engine import cleanup, security
from app.engine.common import DEFAULT_THRESHOLDS as T
from app.providers.gcp import GcpProvider, normalise, p95

P = "demo-project"
C = f"https://www.googleapis.com/compute/v1/projects/{P}"
ASSETS = [
    {"name": f"//compute.googleapis.com/projects/{P}/zones/europe-west1-b/instances/vm-1", "asset_type": "compute.googleapis.com/Instance",
     "data": {"name": "vm-1", "id": "123", "status": "RUNNING", "machineType": f"{C}/zones/europe-west1-b/machineTypes/e2-standard-8",
              "zone": f"{C}/zones/europe-west1-b", "labels": {"env": "dev", "owner": "team-a"}}},
    {"name": f"//compute.googleapis.com/projects/{P}/zones/europe-west1-b/disks/orphan", "asset_type": "compute.googleapis.com/Disk",
     "data": {"name": "orphan", "sizeGb": "200", "type": f"{C}/zones/europe-west1-b/diskTypes/pd-balanced",
              "zone": f"{C}/zones/europe-west1-b", "creationTimestamp": "2020-01-01T00:00:00+00:00",
              "selfLink": f"{C}/zones/europe-west1-b/disks/orphan", "labels": {"env": "dev"}}},
    {"name": f"//compute.googleapis.com/projects/{P}/regions/europe-west1/addresses/ip-1", "asset_type": "compute.googleapis.com/Address",
     "data": {"name": "ip-1", "address": "203.0.113.5", "status": "RESERVED", "addressType": "EXTERNAL",
              "region": f"{C}/regions/europe-west1", "labels": {"env": "dev", "owner": "team-a"}}},
    {"name": f"//compute.googleapis.com/projects/{P}/global/firewalls/allow-ssh", "asset_type": "compute.googleapis.com/Firewall",
     "data": {"name": "allow-ssh", "direction": "INGRESS", "sourceRanges": ["0.0.0.0/0"], "targetTags": ["ssh"],
              "allowed": [{"IPProtocol": "tcp", "ports": ["22"]}], "network": f"{C}/global/networks/default",
              "description": "env=dev owner=team-a"}},
    {"name": f"//storage.googleapis.com/{P}-public", "asset_type": "storage.googleapis.com/Bucket",
     "data": {"name": f"{P}-public", "storageClass": "STANDARD", "location": "EU", "labels": {"env": "dev"}}},
    {"name": f"//iam.googleapis.com/projects/{P}/serviceAccounts/ci@{P}.iam.gserviceaccount.com",
     "asset_type": "iam.googleapis.com/ServiceAccount", "data": {"email": f"ci@{P}.iam.gserviceaccount.com", "uniqueId": "999"}},
    {"name": f"//iam.googleapis.com/projects/{P}/serviceAccounts/999/keys/abc", "asset_type": "iam.googleapis.com/ServiceAccountKey",
     "data": {"keyType": "USER_MANAGED", "validAfterTime": "2020-01-01T00:00:00+00:00"}},
]
POLICIES = {f"//storage.googleapis.com/{P}-public": [{"role": "roles/storage.objectViewer", "members": ["allUsers"]}]}
PROJECT_POLICY = {"bindings": [{"role": "roles/editor", "members": [f"serviceAccount:ci@{P}.iam.gserviceaccount.com"]}]}


def test_normalise_maps_core_types():
    res = {r.name: r for r in normalise(P, ASSETS, POLICIES, PROJECT_POLICY, {"europe-west1-b/e2-standard-8": (8, 32.0)})}
    assert all(r.data_source == "real" for r in res.values())
    vm = res["vm-1"]
    assert (vm.resource_type, vm.config["machine_type"], vm.config["vcpus"], vm.environment) == ("vm", "e2-standard-8", 8, "dev")
    assert res["orphan"].config["users"] == [] and res["orphan"].config["disk_type"] == "pd-balanced"
    assert res["ip-1"].config["status"] == "RESERVED" and res["ip-1"].region == "europe-west1"
    assert res["allow-ssh"].owner == "team-a"  # read from the description
    assert res[f"ci@{P}.iam.gserviceaccount.com"].config == {"roles": ["roles/editor"], "disabled": False,
                                                             "keys": [{"id": "abc", "type": "USER_MANAGED", "created": "2020-01-01T00:00:00+00:00"}]}
    assert res[P].resource_type == "iam_policy"


def test_rules_run_on_real_shaped_data():
    recs = normalise(P, ASSETS, POLICIES, PROJECT_POLICY, {})
    rules = {d.rule for d in security.evaluate(recs, T)}
    assert {"public_bucket", "open_ssh_rdp", "stale_sa_keys", "sa_excessive_permissions", "audit_logging", "permissive_iam"} <= rules
    clean = {d.rule for d in cleanup.evaluate(recs, {}, T)}
    assert {"unattached_disk", "unused_ip"} <= clean


def test_no_billing_export_means_no_cost():
    cd = GcpProvider(P, billing_table=None).get_cost_data(None, None)
    assert cd.records == [] and cd.basis == "none" and "no cost or savings" in cd.note


def test_gcp_estimates_never_guess_prices():
    vm = normalise(P, ASSETS, POLICIES, PROJECT_POLICY, {"europe-west1-b/e2-standard-8": (8, 32.0)})[0]
    g = GcpProvider(P)
    assert g.estimate_resource_cost(vm, {"machine_type": "e2-standard-4"}, 200.0).monthly == 100.0
    disk = [r for r in normalise(P, ASSETS, POLICIES, PROJECT_POLICY) if r.resource_type == "disk"][0]
    assert g.estimate_resource_cost(disk, {"disk_type": "pd-standard"}, 20.0) is None


def test_p95():
    assert p95(list(range(1, 101))) == 95 and p95([]) is None
