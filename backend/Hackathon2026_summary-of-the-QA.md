# Q&A Session -- April 28^th^, 2026 {#qa-session-april-28th-2026}

## 14:00-14:30 BKK, ZOOM {#bkk-zoom}

> *Global Hackathon on AI for Digital Trade Regulatory Analysis -- held by UN ESCAP & KMITL*
>
> **Summary of the session**

<table>
<colgroup>
<col style="width: 47%" />
<col style="width: 52%" />
</colgroup>
<thead>
<tr>
<th colspan="2"><blockquote>
<p><strong>1. Scope, users, and what to build</strong></p>
</blockquote></th>
</tr>
</thead>
<tbody>
<tr>
<td>1.1 Who are the target users?</td>
<td><p><strong>Primary:</strong> ESCAP RDTII researchers, especially in the Asia-Pacific region (the people doing the manual workflow on slide 4).</p>
<p><strong>Secondary:</strong> policymakers and analysts in member-state ministries. Both non-technical — no code, no JSON. <strong>Implication:</strong> the 20% human-review step must be obvious in the UI, not buried.</p></td>
</tr>
<tr>
<td>1.2 What level of analysis / detail is expected?</td>
<td><p><strong>Article-level granularity</strong> — each output points to a specific article in a specific document, with all 6 mandatory fields (title, last update, URL, scope, provisions, impact).</p>
<p>A reviewer must verify or reject any mapping in seconds. Document-level summaries fail at the citation-fidelity benchmark at Stage 2.</p></td>
</tr>
<tr>
<td>1.3 Would an NTM classification solution be suitable?</td>
<td><p><strong>Not directly.</strong> Mandatory pillars are 6 (Cross-border Data Flows)</p>
<p>+ 7 (Domestic Data Protection); broad NTM is out of scope. Works only if your NTM approach is redirected to extract digital trade provisions or provisions related to ICT goods specifically. Pillars 6 and 7 are non-negotiable; everything else is design choice.</p></td>
</tr>
<tr>
<td>1.4 Could you clarify the overall scope?</td>
<td style="text-align: left;"><p>Build a <strong>deployable open-source AI tool</strong> (Apache 2.0) that automates 80% of the RDTII workflow on slide 5 — search, retrieve, describe — leaving 20% for human validation.</p>
<p><strong>Mandatory:</strong> Pillars 6 and 7.</p>
<p><strong>Bonus:</strong> tools that scale to additional pillars.</p>
<p><strong>Geographic coverage:</strong> Your tool should show that it works for multiple Asia-Pacific countries (see Q 5.4).</p></td>
</tr>
<tr>
<td colspan="2"><blockquote>
<p><strong>2. Originality, prior work, innovation vs practicality</strong></p>
</blockquote></td>
</tr>
<tr>
<td>2.1 Can we build on existing solutions?</td>
<td><p><strong>Yes</strong> — open-source libraries, pre-trained models, and licensed components are allowed. Originality means contribution, not invention.</p>
<p><strong>Hard constraints:</strong> licenses must be Apache-2.0-compatible AND your system must work when components are swapped. Disclose all reused components in the Technical Memo.</p></td>
</tr>
<tr>
<td>2.2 Can existing systems be submitted?</td>
<td><strong>Build on prior work: yes. Submit unchanged: no</strong> — must show meaningful new development for this challenge. If your starting point is substantial for pre-existing internal work, contact organizers before applying. Final repo ships under Apache 2.0 either way.</td>
</tr>
<tr>
<td>2.3 Innovation vs practicality?</td>
<td><strong>Practicality dominates</strong> — ~70% of Stage 3 score is deployment, interface, generalisation, and live stress test. Innovation earns leverage where it delivers measurable results: 20 points at Stage 2 for Discovery of New Evidence. Optimise for "does it work, cheaply, repeatably, on unseen jurisdictions?"</td>
</tr>
<tr>
<td>2.4 What about IP rights?</td>
<td>Under the Apache License 2.0, individual contributors retain the copyright/intellectual property (IP) rights to their original contributions. However, by licensing the work under Apache 2.0, these owners grant a perpetual, worldwide, non-exclusive, free-</td>
</tr>
</tbody>
</table>

<table>
<colgroup>
<col style="width: 47%" />
<col style="width: 52%" />
</colgroup>
<thead>
<tr>
<th></th>
<th>of-charge, irrevocable license to anyone to use, modify, and distribute the software.</th>
</tr>
</thead>
<tbody>
<tr>
<td colspan="2"><blockquote>
<p><strong>3. Evaluation, judging, and recognition</strong></p>
</blockquote></td>
</tr>
<tr>
<td>3.1 How is scoring structured?</td>
<td><strong>Three stages, each with a published rubric.</strong> Weights shift design → delivery → production-readiness. Stage 1 is two-thirds of team capability and methodology (no code yet). Stage 3 emphasizes readiness for real UN deployment.</td>
</tr>
<tr>
<td>3.2 What does each stage measure?</td>
<td><p><strong>Stage 1 (Application):</strong> Team expertise 40% / Methodology 30% / Sustainability 30%. <strong>Stage 2 (Round 1):</strong> Substantive</p>
<p>accuracy 40% / Technical resilience 30% / Architecture 30%. <strong>Stage 3 (Finale):</strong> autonomous generalization, interface, deployment, live stress test on unseen countries.</p></td>
</tr>
<tr>
<td>3.3 Who judges?</td>
<td><strong>International panel:</strong> ESCAP, regional commissions, UNCTAD, WTO, World Bank, academic partners. <strong>COI (conflict of interest) rule:</strong> no judging teams you're in, supervise, mentor, or have financial ties with. Written COI declarations from all judges; best-effort screening of assignments.</td>
</tr>
<tr>
<td colspan="2"><blockquote>
<p><strong>4. Application, teams, and process</strong></p>
</blockquote></td>
</tr>
<tr>
<td>4.1 Key dates / submission deadline?</td>
<td><p><strong>Apply by 25 May 2026, 16:00 Bangkok / 9:00 UTC</strong>. Shortlist 31May → Round 1 submission 20 July → hybrid pitch 31 July → finalists 1 August → final submission 30 September → <strong>award ceremony at ESCAP Bangkok, 15 October 2026</strong>.</p>
<p>Further information will be provided to shortlisted candidates.</p></td>
</tr>
<tr>
<td>4.2 Will templates be provided?</td>
<td><strong>Yes</strong> — Concept Video brief, Technical Memo template, Declaration of Originality, is available on the website. <strong>Funding-partner matchmaking: NO.</strong> No development funding, no API credits, no compute, no sponsor-matching service.</td>
</tr>
<tr>
<td>4.3 Application items + formatting?</td>
<td><strong>Four items:</strong> CVs of all members; Concept Video (max 5 min including credits); Technical Memo (max 2 pages — reviewers read first 2 only, diagrams count); signed Declaration of Originality + Apache 2.0 consent. English only. Cost estimate per 50-page doc must be in the Memo. No late submissions except documented platform failure.</td>
</tr>
<tr>
<td>4.4 Eligibility?</td>
<td><strong>Open globally</strong> — students, faculty, researchers, professionals, any nationality. Teams can mix across universities, countries, and student/professional status. Multiple teams per institution allowed, no cap. <strong>Only rule: dual-competency</strong> (Technical + Substantive Lead). ESCAP interns and consultants are welcome as long as there are no conflict of interests.</td>
</tr>
<tr>
<td>4.5 Team structure?</td>
<td><strong>1–5 members.</strong> Technical Lead (AI architecture, extraction, deployment) + Substantive Lead (legal/policy, output accuracy). <strong>Soloists allowed</strong> but must hold both Lead roles and prove dual competency at Stage 1 (high bar). <strong>Faculty:</strong> full member OR advisor — not both.</td>
</tr>
<tr>
<td>4.6 collaboration platform?</td>
<td><strong>Organizer-to-team:</strong> Q&amp;A Portal + SharePoint Resource Library. <strong>Within your team:</strong> you choose your own tools — we don't prescribe. <strong>Inter-team open channel:</strong> linked to the matchmaking decision (likely Discord/LinkedIn).</td>
</tr>
<tr>
<td colspan="2"><blockquote>
<p><strong>5. Tech stack, fine-tuning, datasets, funding</strong></p>
</blockquote></td>
</tr>
<tr>
<td>5.1 What tech stack is allowed?</td>
<td><strong>Anything during development</strong> — paid LLM APIs (Claude, GPT, Gemini) fine. <strong>But:</strong> design must be modularly swappable to open-weight models (e.g. Llama 3) — scored heavily, 20 pts at Stage 1 + 20 at Stage 3. Open-source components OK if Apache-2.0-compatible; disclose all in Memo.</td>
</tr>
<tr>
<td>5.2 Fine-tune open-weight models?</td>
<td><strong>Yes.</strong> Fine-tuning allowed; resulting weights are part of the submission. Base model license must be Apache-2.0-</td>
</tr>
</tbody>
</table>

<table>
<colgroup>
<col style="width: 47%" />
<col style="width: 52%" />
</colgroup>
<thead>
<tr>
<th></th>
<th>compatible (Llama 3 family OK; Mistral with care). <strong>Fine-tuned weights must be published in the GitHub repo</strong>, not kept private. Disclose training data and method in the Memo.</th>
</tr>
</thead>
<tbody>
<tr>
<td>5.3 Recommended AI tools / prompting?</td>
<td><strong>No prescription</strong> — design choices are scored. <strong>Patterns that work well:</strong> RAG over OCR'd legal text with article-level chunking + structured prompting for citation extraction + small classifiers for indicator mapping with LLM verification. Whatever you pick, prove generalisation and document the cost.</td>
</tr>
<tr>
<td>5.4 Datasets / technical requirements?</td>
<td><p><strong>Application stage:</strong> ESCAP website contains RDTII-related database and guide which can be used to train and test your system <a href="https://www.unescap.org/projects/rcdtra/coverage">(<u>Structure of Analysis | ESCAP</u></a> ; <a href="https://www.unescap.org/kp/2025/regional-digital-trade-integration-index-rdtii-21-guide"><u>Regional Digital Trade</u></a> <a href="https://www.unescap.org/kp/2025/regional-digital-trade-integration-index-rdtii-21-guide"><u>Integration Index (RDTII) 2.1: a guide | ESCAP</u></a>). However, your tool should prove that you can find new evidence beyond what is provided.</p>
<p>At this stage, there is no fixed coverage regarding countries. <strong>Round 1:</strong> 5–10 documents from <strong>3 provided countries</strong> + reference taxonomy in the Resource Library. <strong>Finale:</strong> 10 assigned countries (some non-English, some with messy portals</p>
<p>— anti-bot, scanned PDFs), deliver for <strong>at least 3 countries</strong>. <strong>Tool requirements:</strong> open-source, modular, OCR &lt;5% CER, audit view, self-hostable.</p></td>
</tr>
<tr>
<td colspan="2"><blockquote>
<p><strong>6. Mentorship, support, finale logistics</strong></p>
</blockquote></td>
</tr>
<tr>
<td>6.1 How accessible are mentors?</td>
<td><strong>Asynchronous via Q&amp;A Portal</strong> — target ~2 business days normally, 1 near deadlines. Mentors are a panel responding to portal queries and running scheduled office hours around milestones — <strong>not assigned 1:1</strong>, no live always-on chat. Plan accordingly.</td>
</tr>
<tr>
<td>6.2 What ongoing support?</td>
<td><strong>Q&amp;A Portal</strong> (help desk and discussion forum) + <strong>Resource Library on SharePoint</strong> (RDTII framework, reference taxonomy with semantic patterns, sample documents, sample portals, templates). Plus <strong>11 hours of structured training</strong> across two workshops: ESCAP 5 June + KMITL 10 June 2026.</td>
</tr>
<tr>
<td>6.3 Bangkok finale logistics?</td>
<td><strong>Travel grant up to USD 4,000 per finalist team</strong> — single pool regardless of where members fly from, ≤3 sponsored travellers, reimbursed against receipts. Visa invitation letters issued on request. Accommodation reimbursable. <strong>Accessibility accommodations require 4 weeks' notice</strong> — request as soon as finalists are announced (1 August).</td>
</tr>
</tbody>
</table>

> Recording available at: [[Global Hackathon on Using AI for Digital Trade Regulatory Analysis \| ESCAP]{.underline}](https://www.unescap.org/events/2026/global-hackathon-using-ai-digital-trade-regulatory-analysis)

### Other useful links:

> KMITL Event Page: [[digitaltradehack2026 - ENGINEER]{.underline}](https://www.eng.kmitl.ac.th/digitaltradehack2026/)
>
> ESCAP Event Page: [[Global Hackathon on Using AI for Digital Trade Regulatory Analysis \| ESCAP]{.underline}](https://www.unescap.org/events/2026/global-hackathon-using-ai-digital-trade-regulatory-analysis) Registration Link: [[Global Hackathon Using AI for Digital Trade Regulatory Analysis -- Application Form]{.underline}](https://www.jotform.com/form/260591342899065) **Regional Digital Trade Integration Index (RDTII) is the framework for the competition:**
>
> RDTII Framework: [[Structure of Analysis \| ESCAP]{.underline}](https://www.unescap.org/projects/rcdtra/coverage)
>
> RDTII Guide: [[Regional Digital Trade Integration Index (RDTII) 2.1: a guide \| ESCAP]{.underline}](https://www.unescap.org/kp/2025/regional-digital-trade-integration-index-rdtii-21-guide)
>
> Contact: If you have any further queries, drop us an email at [[escap-digitaltrade-hackathon@un.org]{.underline}](mailto:escap-digitaltrade-hackathon@un.org) and [[regtech2026@kmitl.ac.th]{.underline}.](mailto:regtech2026@kmitl.ac.th)
