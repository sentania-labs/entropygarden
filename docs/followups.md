# Follow-ups / Deferred Items

Running list of things noticed during play/dev that need addressing. Move to roadmap once scoped.

---

## Sim balance

- **Occupation distribution variance** — ring starting populations use weighted random assignment, so one ring can roll significantly fewer life support or farmer workers than another. Early games become RNG lotteries rather than skill/decision tests. Fix: guarantee a deterministic minimum per occupation per ring, randomize only the remainder.

- **Inter-ring resource transfer** — currently only `divert_power` allows resource movement between rings. Food, water, and oxygen have no transfer mechanic. This is a design gap: a ring running dry should be able to request aid from a surplus ring, authorized by captain or engineer. Fits the negotiation-over-optimization theme well. Add a `transfer_resource` action type.

---

## Infrastructure / ops

- **Persistent container logs** — Docker logs live in memory and are lost when containers are removed. Add log rotation config (json-file driver with size/count limits) or a syslog forwarding driver so logs survive restarts and can be shipped to an external aggregator (rsyslog, Graylog, Papertrail, Loki).

---

## Client / UX

- **vite.config.ts `allowedHosts: true`** — required for LAN/FQDN access through the nginx proxy. Already in place; note here in case it gets reverted.

