# Developer Laptop Procurement — Requirements Package

## Source: IT Department Memo (2026-03-15, authored by Head of Engineering)

Requesting 100 developer laptops for the new Riga EU office, opening Q3 2026. Our developers run containerized microservices locally (Docker + Kubernetes), compile large Rust/Go codebases, and use multiple IDEs simultaneously. The machines must handle sustained high-CPU workloads without thermal throttling.

### Hardware Specifications

**Processing**
- CPU: minimum 8 physical cores. 12+ cores strongly preferred — our CI build times on 8-core machines are unacceptable (45min+ for full test suite). Current Berlin team uses 12-core AtlasBook systems and reports 22min builds.
- Architecture: x86_64 required. ARM64 is not acceptable — our toolchain (CUDA dev kit, several proprietary EDA tools) has no ARM Linux builds.

**Memory and Storage**
- RAM: 32 GB DDR5 minimum, non-negotiable. 16 GB is not viable — developers routinely use 24-28 GB with Docker + IDE + browser. If 64 GB options are available within budget, flag them as preferred.
- Storage: 1 TB NVMe SSD minimum. PCIe Gen 4 or newer. Must support hardware encryption (OPAL 2.0).

**Display**
- Size: 14 inch or larger.
- Resolution: 1920x1200 minimum. 2560x1600 (WQXGA) strongly preferred — developers report significantly better code readability at higher resolution with 16:10 aspect ratio.
- Aspect ratio: 16:10 required. 16:9 displays are too short for split code editor + integrated terminal layout. This is a hard requirement from the development team.
- Anti-glare/matte finish mandatory. Glossy screens cause eye strain in office lighting.
- NO touchscreen. Touchscreens add EUR 80-150 to unit cost, increase display fragility, worsen anti-glare properties, and drain battery. No developer use case justifies this. If a vendor's standard SKU includes touchscreen, request non-touch variant or deduct the cost difference.

**Ports and Connectivity**
- Minimum 2x USB-C (at least one Thunderbolt 4 for docking)
- Minimum 1x HDMI 2.0 or higher (direct monitor connection without dongle — developers present and demo frequently)
- Minimum 2x USB-A 3.0 (legacy peripherals: hardware security keys, USB debug interfaces, test equipment)
- Wi-Fi 6E or newer
- Bluetooth 5.2 or newer
- RJ45 Ethernet port preferred (not required — USB-C adapter acceptable for modern office docking)

**Battery and Thermal**
- Battery life: minimum 8 hours under normal development workload (IDE + browser + Docker idle). 10+ hours preferred.
- Thermal: must sustain full CPU load for 30+ minutes without throttling below base clock. Open-plan office — fan noise must remain below 45 dB under sustained load. Previous CinderBook batch (2024) was returned due to fan noise complaints.
- Weight: under 1.9 kg preferred. Under 2.1 kg maximum. Developers travel between Riga and Berlin offices monthly.

**Keyboard and Build**
- ISO keyboard layout (EU variants) must be available. Backlit keyboard required.
- Build quality: magnesium/aluminum chassis preferred. Must pass MIL-STD-810H or equivalent durability testing.
- Spill-resistant keyboard.

### Operating System
- Ubuntu 24.04 LTS is our standard OS. We do NOT use Windows. The vendor's hardware must hold official Canonical Ubuntu 24.04 LTS certification. Uncertified hardware is not acceptable — do not recommend any vendor whose model lacks this certification.
- Linux compatibility is required. Confirmed driver support for Wi-Fi, Bluetooth, suspend/resume, and external displays is mandatory.
- Vendor must permit self-imaging. BIOS/firmware must not be locked to a specific OS. Secure Boot must be configurable.
- TPM 2.0 required for LUKS full-disk encryption.

---

## Source: Finance Department Budget Approval (2026-03-22, signed by CFO)

Approved procurement budget: **EUR 180,000** for 100 developer workstations.

This represents EUR 1,800 per unit. This is the approved ceiling including hardware only. Setup, imaging, accessories (docks, monitors, peripherals) are covered under a separate IT operations budget line and must NOT be included in this procurement.

Note: the original IT request cited EUR 200,000 but this was reduced during Q2 budget review. The EUR 180,000 figure is the authorized amount. Any spend above this requires a supplementary budget request with VP Engineering and CFO co-approval.

Volume discounts negotiated with vendors are expected to bring effective per-unit cost below EUR 1,800. Framework agreements require Legal review if total value exceeds EUR 150,000.

---

## Source: CISO Directive (2026-04-01)

### Mandatory Compliance — No Exceptions

1. **ISO 27001 certification**: the hardware vendor must hold a current, valid ISO 27001 certificate from an accredited certification body. "In progress" or "applied for" is not acceptable. Certificate must be valid through at least 2027-06-30 (12 months post-delivery).

2. **GDPR Data Processing Agreement**: must be executed before any purchase order is issued. Standard vendor DPA templates are acceptable if reviewed by Legal.

3. **EU data residency**: units must ship from an EU-based warehouse. No direct shipments from outside the EU — customs processing introduces uncontrolled handling of pre-configured devices.

4. **Hardware security**:
   - TPM 2.0 mandatory
   - OPAL 2.0 SSD encryption support
   - No vendor-installed bloatware or telemetry agents. If vendor ships with pre-installed software, it must be fully removable without affecting hardware warranty.
   - BIOS/UEFI must support Secure Boot with custom key enrollment

5. **Supply chain**: vendor must disclose manufacturing origin and provide a written statement that no components are sourced from sanctioned entities under current EU regulations.

---

## Source: Operations Team Note (2026-04-05, Riga Office Manager)

Delivery timeline is critical. The Riga office opens 2026-09-01. Laptops must be delivered, imaged, and desk-ready by 2026-08-15 at the latest. Working backward:
- Internal imaging and setup: 2 weeks (2026-08-01 to 2026-08-15)
- Delivery buffer: 1 week
- Therefore: vendor must deliver by **2026-07-25** at the latest
- Contract signature target: **2026-06-01**
- That gives the vendor approximately **8 weeks** from contract to delivery

Also: we need compatible docking stations (USB-C/Thunderbolt). If the laptop vendor offers a certified dock, quote it separately. If not, confirm compatibility with Atlas USB-C Dock Standard (our Berlin office standard).
