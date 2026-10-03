# Privilege-escalation vulnerabilities — obtaining the sudo packages

Each of these vulns works by installing a **specific, intentionally-vulnerable version of `sudo`** on the
victim host. Those `.deb` packages are **not shipped in this repo** (we don't redistribute old vulnerable
binaries). To use a vuln, download its exact `.deb` from a Debian package archive — e.g.
[snapshot.debian.org](https://snapshot.debian.org/) or [pkgs.org](https://pkgs.org/) — and place it in the
vuln's own directory under the filename the playbook expects (the `copy` task's `src:`), listed below.

| Vuln | Directory | Expected file | Vulnerable `sudo` version |
|------|-----------|---------------|---------------------------|
| sudobaron | `sudobaron/`   | `sudo_1.8.19p1-2.1_amd64.deb` | 1.8.19p1-2.1 |
| sudobypass | `sudobypass/` | `sudo_1.8.10p3-1.deb`          | 1.8.10p3-1 |
| sudoedit  | `sudoedit/`    | `sudo_1.8.26-2_amd64.deb`     | 1.8.26-2 |

Verify the package's checksum against the archive before using it. The playbook `dpkg`-installs the file
you place here; if the file is absent the playbook fails with a clear "file not found", so these vulns are
opt-in. `*.deb` is gitignored, so a package you drop in will not be accidentally committed.
