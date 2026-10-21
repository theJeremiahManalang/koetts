"""Run credential-safe live S3 denial checks using a narrowly scoped verifier identity.

Requires gcloud login and iam.serviceAccounts.getOpenIdToken on the named account.
This script does not grant permissions, impersonate users or invoke providers.
"""

import argparse
import json
import subprocess
import urllib.error
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="https://koetts-s3-api-gu5jb64hpq-uk.a.run.app")
parser.add_argument("--project", default="koetts-9bf7f")
parser.add_argument(
    "--service-account", default="koetts-s3-api@koetts-9bf7f.iam.gserviceaccount.com"
)
args = parser.parse_args()
URL = args.url.rstrip("/")


def call(url, headers=None, body=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def mint(audience):
    access = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True, stderr=subprocess.PIPE
    ).strip()
    status, body = call(
        "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
        + args.service_account
        + ":generateIdToken",
        {
            "Authorization": "Bearer " + access,
            "x-goog-user-project": args.project,
            "Content-Type": "application/json",
        },
        {"audience": audience, "includeEmail": True},
    )
    if status != 200:
        raise RuntimeError("Service ID-token mint failed with status " + str(status))
    return json.loads(body)["token"]


token = mint(URL)
headers = {
    "Authorization": "Bearer " + token,
    "X-Serverless-Authorization": "Bearer " + token,
}
cases = [
    ("anonymous platform denial", "/ready", {}, 403),
    ("authorized readiness", "/ready", headers, 200),
    ("missing Firebase credential", "/identity", headers, 401),
    (
        "forged Firebase credential",
        "/identity",
        {**headers, "X-KoeTTS-User-Token": "forged"},
        401,
    ),
    (
        "ambiguous Firebase credentials",
        "/identity",
        {
            **headers,
            "X-KoeTTS-User-Token": "forged",
            "X-KoeTTS-Session-Cookie": "forged",
        },
        401,
    ),
    (
        "independent wrong audience denial",
        "/ready",
        {**headers, "Authorization": "Bearer " + mint("https://wrong.example")},
        401,
    ),
]
for label, path, supplied, expected in cases:
    status, body = call(URL + path, supplied)
    print(label + ": " + str(status), flush=True)
    if status != expected:
        raise RuntimeError(label + " expected " + str(expected))
    if label == "authorized readiness":
        assert json.loads(body) == {"ready": True, "mode": "verification"}
print("Private live probes passed; no user impersonation or provider calls.")
