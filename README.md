Automated Extraction of Public Procurement Data 
Using Selenium and Shadow DOM Traversal: A Case 
Study on the Alberta Purchasing Connection Website 
Author: Dr  Paurush Totlani 
Date: August 31, 2025 
Abstract 
Public procurement data is vital for research in economics, supply chains, and governance. 
Modern procurement portals increasingly rely on Web Components and Shadow DOM, 
which complicates traditional scraping approaches. This paper presents a reproducible 
Python framework that combines Selenium WebDriver with custom JavaScript to traverse 
Shadow DOM trees, robust pagination routines with page change fingerprinting, duplicate 
suppression, and conservative pacing to minimize server load. Using the Government of 
Alberta’s Alberta Purchasing Connection (APC) search portal as a case study, the system 
extracts opportunity titles, URLs, and short descriptions and persists them in JSON Lines 
(JSONL) for downstream analysis. We discuss design choices, legal ethical considerations, 
and limitations, and outline how the approach generalizes to other public procurement 
platforms. 
1. Introduction 
Government procurement transparency fosters competition, accountability, and better value 
for taxpayers. Researchers often require longitudinal datasets of tender notices across 
jurisdictions. While many portals expose data through conventional HTML, others render 
content within Shadow DOM trees, preventing naive DOM queries from locating elements. 
This manuscript details an automation approach that enables reliable data collection from 
such interfaces specifically, the Alberta Purchasing Connection Website opportunity search 
to facilitate reproducible research datasets. 
2. Background and Related Work 
Web scraping has matured alongside modern web application architectures. Selenium 
WebDriver provides a language agnostic API for browser automation, enabling 
interaction with client rendered content. However, Shadow DOM encapsulation, integral to 
Web Components, isolates markup and styles from the main document tree. To extract data 
reliably, scrapers must enumerate shadow roots and perform deep queries. Practical 
guidance on scraping ethics emphasizes respect for terms of service and the Robots 
Exclusion Protocol. 
3. Materials and Methods 
3.1 Data Source: Alberta Purchasing Connection 
Alberta Purchasing Connection is the Government of Alberta’s online portal for posting 
public procurement opportunities. The search interface presents paginated lists of 
opportunities with titles, summaries, and links to full postings. Only publicly visible 
information was accessed. The implementation was designed to follow polite scraping 
practices, including delay jitter and periodic cooling off intervals. Users must review and 
comply with Alberta Purchasing Connections Website terms of use before replication or 
large scale data collection. 
3.2 Software Environment 
The implementation uses Python 3 with Selenium WebDriver and Firefox (GeckoDriver). 
Driver binaries are provisioned programmatically via the webdriver manager library. 
Execution may be headless or visible. Logging tracks page loads, pagination progress, and 
item counts for reproducibility. 
3.3 Shadow DOM Traversal 
To locate results rendered within nested shadow roots, the system injects JavaScript 
utilities that include: 
• Enumerating all hosts possessing a shadow Root. 
• Recursively descending into each shadow tree. 
• Performing deep query selector operations across the composed tree. 
This enables robust identification of result cards and pagination controls that would 
otherwise be opaque to standard Selenium locators. 
3.4 Pagination and Page Change Fingerprinting 
The portal’s paginator is controlled using two complementary strategies: 
• Typing a target page number into a numeric input when present. 
• Clicking numeric links or buttons when available. 
After initiating navigation, the scraper monitors for a page change by fingerprinting the 
first result (title and href) and polling until it differs from the prior page. Retries 
incrementally extend the wait window and include back off delays. If navigation fails 
repeatedly, the run halts gracefully to avoid excessive requests. 
3.5 Record Extraction and Deduplication 
Each result card yields a tuple of Title, URL, and optional short Description. A set of seen 
URLs prevents duplicate records across pagination. To accommodate lazy loaded content, 
the script scrolls to the document bottom multiple times per page before parsing. 
3.6 Output Format and Reproducibility 
Records are written line by line to a JSON Lines (JSONL) file, enabling incremental 
processing and simple downstream ingestion into data frames or databases. Logged 
counters report pages processed and rows collected. Hyperparameters such as start/end 
pages, wait timeouts, and per page caps are configurable to facilitate replication and 
controlled experiments. 
4. Results and Applications 
In end to end runs, the framework consistently collected structured opportunity records 
across paginated result sets. The resulting JSONL can feed analytical tasks such as 
temporal trend analysis, sectoral comparisons, supplier landscape mapping, and policy 
evaluation. Because the method targets the rendered UI rather than an unstable internal 
API, it demonstrates resilience to minor site changes while remaining sensitive to major 
redesigns. 
5. Legal, Ethical, and Responsible Use 
The approach is intended exclusively for publicly available information and must be used 
in accordance with applicable law, the portal’s terms of use, and the Robots Exclusion 
Protocol. Practitioners should follow these principles: 
• Throttle requests with randomized delays. 
• Avoid bypassing access controls. 
• Attribute sources appropriately. 
• Cease or adjust collection if servers indicate strain. 
6. Limitations 
Portals that substantially change their markup or interaction model can break the 
automation and require maintenance. Single process Selenium may be slower than 
specialized crawlers for very large collections. Shadow DOM traversal relies on executing 
custom scripts; restrictive Content Security Policies could limit such execution in some 
environments. 
7. Conclusion 
This case study demonstrates a practical, reproducible recipe for extracting structured 
procurement data from a Shadow DOM based web portal. By combining deep traversal, 
robust pagination, deduplication, and conservative pacing, the method yields analysis 
ready JSONL datasets while foregrounding ethical and legal safeguards. The same pattern
