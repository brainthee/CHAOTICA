# Skills, Services & Qualifications — Proposed Taxonomy

**Status:** Proposal for SLT review
**Purpose:** A clean-sheet skills framework for a penetration testing / red team consultancy, mapped to our current service catalogue and the industry qualifications we track.
**Scope:** This proposal *replaces* the existing skill categories and skills in CHAOTICA. It is built bottom-up from the 31 services we sell and the 58 qualifications we already record, so that every skill either enables a service, is evidenced by a qualification, or supports delivery.

---

## 1. Design principles

1. **Service-led.** Every service must map to at least one *required* skill so the "who can deliver this?" readiness analysis works. Today 14 of 31 services have no skills attached — this fixes that.
2. **Evidence-led.** Every qualification we track should map to one or more skills, so awarding a certificate can inform someone's skill profile and so we can answer "does our qualification base cover this service?".
3. **Rateable per person.** Skills are things an individual can be rated on (No experience → Can do with support → Can do alone → Specialist). Categories group them for the skills matrix.
4. **Delivery skills count.** Report writing, QA, scoping and engagement management are first-class skills — they gate quality as much as technical ability.
5. **Right-sized.** ~95 skills across 11 categories. Granular enough to spot capability gaps, coarse enough that people will actually keep them updated.

---

## 2. Proposed skill categories

| # | Category | Focus |
|---|----------|-------|
| 1 | Infrastructure & Network Testing | External/internal infra, AD, network devices, build reviews, breakout, wireless |
| 2 | Web & API Security | Web apps, APIs, authentication, business logic, open banking |
| 3 | Mobile Security | iOS/Android apps & devices, MDM, mobile reversing |
| 4 | Cloud & Container Security | AWS, Azure, GCP, M365, Docker, Kubernetes, IaC |
| 5 | Red Teaming & Adversary Simulation | C2, evasion, lateral movement, physical, scenario/simulated attack |
| 6 | Application Security & Code Review | Language-specific secure code review, SAST/DAST, secure SDLC |
| 7 | Specialist & Emerging Technology | AI/LLM, OT/ICS, IoT/hardware, automotive, telco, blockchain, crypto |
| 8 | Social Engineering | Phishing, vishing, physical pretexting, awareness |
| 9 | Detection & Defensive Security | Purple team, detection engineering, SIEM, threat hunting, SOC, IR |
| 10 | Governance, Risk & Compliance | Threat modelling, Cyber Essentials, vuln management, risk, standards |
| 11 | Consultancy & Professional Delivery | Report writing, QA, scoping, engagement management, client management, mentoring |

---

## 3. Skill catalogue (by category)

### 1. Infrastructure & Network Testing
- External Infrastructure Testing
- Internal Infrastructure Testing
- Active Directory Assessment
- Active Directory Exploitation (Kerberos, delegation, ADCS)
- Network Protocols & Services
- Network Segmentation / VLAN Review
- Firewall Rule-base Review
- Network Device Configuration Review (Cisco / Juniper / Palo Alto / Check Point)
- IPv6 Security
- Build / Host Hardening Review — Windows (Desktop & Server)
- Build / Host Hardening Review — Unix / Linux
- Build / Host Hardening Review — macOS
- Citrix / Kiosk / Application Breakout
- Thick Client / Desktop Application Testing
- Wireless Network Security (Wi-Fi)
- Vulnerability Scanning & Triage

### 2. Web & API Security
- Web Application Testing
- API Security Testing (REST / GraphQL / SOAP)
- Authentication & Authorisation Testing
- Business Logic Testing
- Open Banking / Financial API Testing
- Web Services & Legacy XML

### 3. Mobile Security
- iOS Application Testing
- Android Application Testing
- iOS Device Testing
- Android Device Testing
- Mobile Device Management (MDM) Assessment
- Mobile Reverse Engineering

### 4. Cloud & Container Security
- Amazon Web Services (AWS) Security
- Microsoft Azure Security
- Google Cloud Platform (GCP) Security
- Microsoft 365 Security
- Cloud Configuration & Architecture Review
- Container Security (Docker)
- Kubernetes / Orchestration Security
- Infrastructure-as-Code Review

### 5. Red Teaming & Adversary Simulation
- OSINT Gathering & Analysis
- Command & Control (C2) Frameworks
- Initial Access / Payload Development
- Defence Evasion (AV / EDR bypass)
- Lateral Movement & Privilege Escalation
- Physical Security / Facility Breakout
- Attack Path Mapping (MITRE ATT&CK)
- Assumed Breach / Scenario Testing
- Simulated Targeted Attack (CBEST / STAR / TIBER)

### 6. Application Security & Code Review
- Secure Code Review — C# / .NET
- Secure Code Review — Java
- Secure Code Review — Python
- Secure Code Review — JavaScript / TypeScript
- Secure Code Review — C / C++
- Secure Code Review — PHP
- Secure Code Review — Go
- Secure Code Review — Swift / Objective-C
- SAST / DAST Tooling
- Secure SDLC / DevSecOps

### 7. Specialist & Emerging Technology
- AI / LLM Security
- Operational Technology (OT) / ICS / SCADA
- IoT / Embedded Device Security
- Hardware Security & Reverse Engineering
- Automotive Security
- Consumer / Product Security
- Telecommunications Security
- Blockchain / Smart Contract Security
- Applied Cryptography Review

### 8. Social Engineering
- Phishing Campaign Design & Delivery
- Vishing (Voice Phishing)
- Physical Social Engineering / Pretexting
- Security Awareness Assessment

### 9. Detection & Defensive Security (Purple / SOC)
- Purple Team Exercise Delivery
- Detection Engineering
- SIEM / Log Analysis
- Threat Hunting
- Security Operations (SOC) Consultancy
- Incident Response
- Threat Intelligence

### 10. Governance, Risk & Compliance
- Threat Modelling
- Cyber Essentials / Cyber Essentials Plus Assessment
- Vulnerability Management Programme Consultancy
- Risk Assessment & Management
- Security Architecture Review
- Compliance & Standards (ISO 27001 / PCI DSS / NIST)

### 11. Consultancy & Professional Delivery
- Report Writing
- Technical Quality Assurance (QA)
- Editorial / Report QA
- Engagement Scoping
- Project / Engagement Management
- Client Relationship Management
- Presentation & Debrief Delivery
- Mentoring & Knowledge Sharing

---

## 4. Service → Skill mapping

**R** = Required (needed to deliver / lead the service) · **D** = Desired (strengthens the team but not essential).
Core services are marked ★.

| Service | Required skills (R) | Desired skills (D) |
|---------|---------------------|--------------------|
| **External Infrastructure Assessment ★** | External Infrastructure Testing | Vulnerability Scanning & Triage; OSINT Gathering & Analysis; Web Application Testing |
| **Internal Infrastructure Assessment ★** | Internal Infrastructure Testing | Active Directory Assessment; Lateral Movement & Privilege Escalation; Network Protocols & Services |
| **Build Review ★** | Build/Host Hardening — Windows; Build/Host Hardening — Unix/Linux; Build/Host Hardening — macOS | Active Directory Assessment; Vulnerability Scanning & Triage |
| **Web Application Assessment ★** | Web Application Testing; Authentication & Authorisation Testing | API Security Testing; Business Logic Testing; Web Services & Legacy XML |
| **Web API Assessment ★** | API Security Testing | Authentication & Authorisation Testing; Web Application Testing; Business Logic Testing |
| **Red Team ★** | OSINT Gathering & Analysis; C2 Frameworks; Defence Evasion; Initial Access / Payload Development; Lateral Movement & Privilege Escalation | Physical Security / Facility Breakout; Phishing Campaign Design & Delivery; Attack Path Mapping; Simulated Targeted Attack |
| Active Directory Assessment | Active Directory Assessment; Active Directory Exploitation | Internal Infrastructure Testing; Lateral Movement & Privilege Escalation; Network Protocols & Services |
| Network Device Review | Network Device Configuration Review; Network Protocols & Services; Network Segmentation / VLAN Review | Firewall Rule-base Review; IPv6 Security; Wireless Network Security |
| Breakout Assessment | Citrix / Kiosk / Application Breakout | Build/Host Hardening — Windows; Thick Client / Desktop Application Testing |
| Thick Client / Desktop App Assessment | Thick Client / Desktop Application Testing; Citrix / Kiosk / Application Breakout | Secure Code Review — C#/.NET; Secure Code Review — C/C++; Hardware Security & Reverse Engineering |
| Wireless Security Assessment | Wireless Network Security (Wi-Fi) | Network Protocols & Services; Hardware Security & Reverse Engineering |
| Vulnerability Assessment | Vulnerability Scanning & Triage | External Infrastructure Testing; Internal Infrastructure Testing; Report Writing |
| Cloud Assessment | AWS Security; Azure Security; GCP Security; M365 Security; Cloud Configuration & Architecture Review | Container Security; Kubernetes / Orchestration Security; Infrastructure-as-Code Review |
| Containerisation Assessment | Container Security (Docker); Kubernetes / Orchestration Security | Cloud Configuration & Architecture Review; Infrastructure-as-Code Review |
| Mobile Application Assessment | iOS Application Testing; Android Application Testing | Mobile Reverse Engineering; API Security Testing |
| Mobile Device Assessment | iOS Device Testing; Android Device Testing | Mobile Device Management (MDM) Assessment |
| Mobile MDM Assessment | Mobile Device Management (MDM) Assessment | iOS Device Testing; Android Device Testing |
| Code Review | *At least one* Secure Code Review language | All Secure Code Review languages; SAST / DAST Tooling; Secure SDLC / DevSecOps |
| Open Banking Assessment | Open Banking / Financial API Testing; API Security Testing | Web Application Testing; Authentication & Authorisation Testing |
| AI/LLM Assessment | AI / LLM Security | Web Application Testing; API Security Testing; Secure Code Review — Python |
| Product Security | Consumer / Product Security; IoT / Embedded Device Security | Hardware Security & Reverse Engineering; Automotive Security; Telecommunications Security; Wireless Network Security |
| SCADA/ICS Assessment | Operational Technology (OT) / ICS / SCADA | Network Device Configuration Review; Hardware Security & Reverse Engineering |
| OSINT Assessment | OSINT Gathering & Analysis | Threat Intelligence; Phishing Campaign Design & Delivery |
| Social Engineering | Phishing Campaign Design & Delivery; Physical Social Engineering / Pretexting | Vishing; OSINT Gathering & Analysis; Security Awareness Assessment |
| Scenario Testing | Assumed Breach / Scenario Testing | C2 Frameworks; Lateral Movement & Privilege Escalation; Attack Path Mapping |
| Purple Team | Purple Team Exercise Delivery; Detection Engineering | C2 Frameworks; Defence Evasion; Threat Hunting; SIEM / Log Analysis; Attack Path Mapping |
| SoC Consultancy | Security Operations (SOC) Consultancy; SIEM / Log Analysis | Detection Engineering; Threat Hunting; Incident Response; Threat Intelligence |
| Threat Modelling | Threat Modelling | Security Architecture Review; Secure SDLC / DevSecOps; Risk Assessment & Management |
| Vulnerability Management | Vulnerability Management Programme Consultancy | Vulnerability Scanning & Triage; Risk Assessment & Management; Compliance & Standards |
| Project Management | Project / Engagement Management | Client Relationship Management; Engagement Scoping |
| Bespoke Consultancy | Engagement Scoping; Client Relationship Management | Report Writing; Presentation & Debrief Delivery; Risk Assessment & Management |

> **Cross-cutting:** *Report Writing*, *Technical QA* and *Presentation & Debrief Delivery* apply to essentially every technical service. Rather than list them on all 31 rows, recommend treating them as baseline delivery skills expected of every consultant, tracked in the matrix but not gating individual services.

---

## 5. Qualification → Skill & Service mapping

For each qualification we track, the skills it evidences and the services it most supports. This lets us answer *"we have N holders of X — what does that buy us?"* and *"to staff service Y, which certs should we be funding?"*.

| Qualification | Body | Evidences (skills) | Supports (services) |
|---------------|------|--------------------|--------------------|
| OSCP / OSCP+ | Offensive Security | External & Internal Infra Testing; Lateral Movement & PrivEsc | External/Internal Infra; Build Review; Vuln Assessment |
| OSEP | Offensive Security | Defence Evasion; AD Exploitation; Lateral Movement | Red Team; Scenario Testing; Internal Infra |
| OSWE | Offensive Security | Web App Testing (white-box); Secure Code Review | Web App; Web API; Code Review; AI/LLM |
| OSWA | Offensive Security | Web Application Testing | Web Application Assessment |
| OSWP | Offensive Security | Wireless Network Security | Wireless Security Assessment |
| OSED | Offensive Security | Initial Access / Payload Dev; Exploit development | Code Review; Red Team; Thick Client |
| OSCE3 | Offensive Security | Advanced exploitation; Defence Evasion; Web | Red Team; Code Review |
| OSDA | Offensive Security | Detection Engineering; SIEM / Log Analysis | Purple Team; SoC Consultancy |
| OSTH | Offensive Security | Threat Hunting | Purple Team; SoC Consultancy |
| OSMR | Offensive Security | macOS; Hardware/Reverse Engineering | Build Review (macOS); Product Security |
| CRTO | Zero-Point Security | C2 Frameworks; Defence Evasion; Lateral Movement | Red Team; Scenario Testing; Purple Team |
| CRTL | Zero-Point Security | Red Team leadership; C2; Evasion | Red Team (lead) |
| CRTP | Altered Security | AD Exploitation; Lateral Movement | AD Assessment; Internal Infra; Red Team |
| CRTE | Altered Security | Advanced AD Exploitation | AD Assessment; Red Team |
| CCT INF | CREST | Internal/External Infra; AD; Network Device Review | Infra (lead); Build Review; Network Device Review |
| CCT APP | CREST | Web Application & API Testing | Web App; Web API; Open Banking |
| CRT | CREST | Web App + Infra fundamentals | Web App; External/Internal Infra |
| CPSA | CREST | Vuln Scanning; Web/Infra fundamentals | Vuln Assessment; External Infra |
| CCRTS | CREST | Red Team / Simulated Attack | Red Team |
| CCRTM | CREST | Red Team leadership; Simulated Targeted Attack | Red Team (lead) |
| CCSAS | CREST | Simulated Targeted Attack | Red Team; Scenario; Purple |
| CCSAM | CREST | Simulated Targeted Attack (management) | Red Team; Scenario (lead) |
| CSTL INF | The Cyber Scheme | Internal/External Infra (team lead) | Infra (lead) |
| CSTL WebApp | The Cyber Scheme | Web Application Testing (team lead) | Web App; Web API (lead) |
| CSTM | The Cyber Scheme | Infra fundamentals | External/Internal Infra; Vuln Assessment |
| CSIP | The Cyber Scheme | OT/ICS/SCADA; IoT | SCADA/ICS Assessment; Product Security |
| GPEN | GIAC | External/Internal Infra; AD | Infrastructure services |
| GWAPT | GIAC | Web Application & API Testing | Web App; Web API |
| GMOB | GIAC | iOS/Android Testing | Mobile App/Device Assessment |
| GCPN | GIAC | Cloud Config Review; AWS/Azure/GCP | Cloud Assessment; Containerisation |
| GXPN | GIAC | Payload Dev; Defence Evasion; Exploit dev | Red Team; Purple Team |
| eCPPT | INE Security | External/Internal Infra | Infrastructure services |
| eWPTX | INE Security | Advanced Web App & API Testing | Web App; Web API |
| eCXD | INE Security | Exploit / Payload Development | Red Team; Code Review |
| eJPT | INE Security | Entry infra / vuln scanning | Vuln Assessment |
| BSCP | PortSwigger | Web Application Testing | Web App; Web API |
| CEH | EC-Council | Broad pentest fundamentals | Vuln Assessment; Infrastructure |
| CSA | EC-Council | SOC; SIEM / Log Analysis | SoC Consultancy |
| C\|ASE .NET | EC-Council | Secure Code Review — C#/.NET | Code Review |
| C\|ASE Java | EC-Council | Secure Code Review — Java | Code Review |
| Pentest+ | CompTIA | External/Internal Infra; Vuln Scanning | Vuln Assessment; Infrastructure |
| Security+ | CompTIA | Foundational security | Build Review; Vuln Assessment |
| CASP+ | CompTIA | Security architecture (broad) | GRC / Consultancy |
| SCS (AWS Security Specialty) | Amazon | AWS Security; Cloud Config Review | Cloud Assessment |
| SAA (AWS Solutions Architect) | Amazon | AWS architecture | Cloud Assessment |
| CCP (AWS Cloud Practitioner) | Amazon | AWS fundamentals | Cloud Assessment (foundational) |
| AZ-500 | Microsoft | Azure Security | Cloud Assessment |
| AZ-900 | Microsoft | Azure fundamentals | Cloud Assessment (foundational) |
| CCSP | ISC2 | Cloud Security (broad) | Cloud Assessment; Containerisation |
| CISSP | ISC2 | Security leadership (broad) | Consultancy; Threat Modelling; GRC |
| CSSLP | ISC2 | Secure SDLC; Code Review | Code Review; Threat Modelling |
| SSCP | ISC2 | Operational security | GRC; Build Review |
| CISM | ISACA | Security management | Consultancy; Vuln Management |
| CRISC | ISACA | Risk management | Vuln Management; GRC |
| CISA | ISACA | Audit & compliance | Vuln Management; GRC |
| CE / CE+ | IASME | Cyber Essentials (Plus) Assessment | Cyber Essentials (GRC) — *see gap below* |

---

## 6. Gaps & observations for SLT

**Services with strong qualification coverage** (safe to scale, easy to evidence to clients):
External/Internal Infra, Web App, Web API, Red Team, Cloud Assessment.

**Services thin on external qualifications** (differentiate on skills & experience, not certs):
AI/LLM Assessment, OSINT Assessment, Social Engineering, Threat Modelling, Purple Team, Vulnerability Management, Bespoke Consultancy, Project Management. These rely on skill ratings and track record — worth being explicit with clients about how we evidence competence here.

**Qualification we hold but don't obviously sell:** IASME **Cyber Essentials / CE+ Assessor** — we track the cert but there is no "Cyber Essentials Assessment" in the service catalogue. Either add the service or reconsider funding the cert.

**Emerging areas with no certification market yet:** AI/LLM, IoT/Product Security (partially covered by CSIP), Blockchain. Treat as skill-and-portfolio-led capabilities.

**No project-management certifications tracked** (e.g. PRINCE2/PMP) despite a Project Management service — worth deciding whether to track these.

---

## 7. How this maps into CHAOTICA

Once approved, this translates directly to the data model. **The relationship plumbing (Phase 1) is already
built** — only the taxonomy *data* awaits approval:

- **Skill categories** → `SkillCategory` records (Section 2). *(data — Phase 2)*
- **Skills** → `Skill` records under each category (Section 3). *(data — Phase 2)*
- **Service → skill** → `Service.skillsRequired` / `Service.skillsDesired` M2M (Section 4). *(schema exists)*
- **Service → qualification** → `Service.qualificationsRequired` / `Service.qualificationsDesired` M2M, surfaced on
  the service detail page along with a *Qualified Personnel* readiness count. *(schema + UI built)*
- **Qualification → skill** → `Qualification.demonstrated_skills` (Skill M2M), editable on the qualification form
  and shown on both the qualification detail (*Skills Demonstrated*) and skill detail (*Evidenced By*) pages.
  *(schema + UI built)*

Still deferred to a later phase: behavioural automation (e.g. awarding a certificate auto-suggesting skill
updates) and factoring qualifications into the scheduler filter / skills matrix.

---

*Prepared from the live CHAOTICA service catalogue (31 services) and qualification register (58 qualifications across 15 awarding bodies).*
