# SEO & AEO report: machinoai.in

Run `b6984e3f-25ab-4738-80a6-21124c5b0e0f` · 2026-11-15 · weekly · complete

> **Cost:** **$0.0152** estimated LLM spend · 4 calls on gpt-6-luna · 43,132 input tokens (0 cached) · 21,688 output tokens (incl. 6,595 reasoning) · crawling, PageSpeed and Search Console are free
>
> **Coverage:** 233 of 2,720 sitemap URLs fetched (8.6%): 174 HTML pages analysed, 59 returned errors · **crawl stopped early**: the site kept returning server errors (first after 102 pages); 267 queued pages not crawled · PageSpeed: 0 of 5 priority pages measured (http_429; no PAGESPEED_API_KEY) · Search Console: not configured (keyword metrics unavailable)

## Executive summary

The highest-priority issue is the sampled crawl’s 59 server errors (53 HTTP 503s and 6 HTTP 500s), after which the crawl paused and stopped early. The clearest content opportunities are to improve the token-calculator page and make the sampled model and RAG pages more useful, although search demand and performance are unverified. The crawl fetched 233 of 2,720 sitemap URLs (8.6%) and analyzed 174 HTML pages, so findings describe a spread sample rather than the full site. Observed errors and slow responses were more numerous than in the previous run, but the previous crawl covered only 19 pages, so this difference does not establish a sitewide regression.

## Action plan

| # | Priority | Action | Pages / template | Owner | Effort | Impact |
|---|---|---|---|---|---|---|
| 1 | p1 | Investigate and resolve the origin, CDN, application, or rate-limit cause of the sampled 5xx responses, then retest under controlled low concurrency. | https://www.machinoai.in/jobs/location/london, https://www.machinoai.in/concepts/ai-agents/how-do-you-safely-garbage-collect-ai-agent-memory-tombstones-after-cross-region-replication-and-failback, https://www.machinoai.in/calculators/writing-goal | developer | large | high |
| 2 | p1 | Connect Search Console and establish a query and page performance baseline for the site. | https://www.machinoai.in/models, https://www.machinoai.in/ai-tools/token-calculator, https://www.machinoai.in/concepts/rag/a-traffic-spike-causes-embedding-api-rate-limits-and-cascading-retries-how-would-you-introduce-backpressure-and-retry-budgets | seo | small | high |
| 3 | p2 | Add a PageSpeed API key and rerun measurements for the five priority pages. | https://www.machinoai.in/concepts, https://www.machinoai.in/research, https://www.machinoai.in/models | seo | small | medium |
| 4 | p2 | After resolving the server errors, recheck reported internal-link destinations and restore failing pages or correct their source links. | https://www.machinoai.in/research/papers, https://www.machinoai.in/models, https://www.machinoai.in/jobs/remote | seo | medium | medium |
| 5 | p2 | Review origin and CDN response times for the slow sampled templates and retest after addressing the server errors. | https://www.machinoai.in/concepts/rag/a-model-starts-producing-invented-source-urls-despite-receiving-valid-document-ids-how-would-you-make-citation-generation-deterministic-and-verifiable, https://www.machinoai.in/blogs, https://www.machinoai.in/research/memgpt-llms-as-operating-systems | developer | large | medium |
| 6 | p2 | Make the /post/* template consistently emit a visible H1, unique title and description, canonical, and the expected article structured data and language attribute. | /post/* | developer | medium | medium |
| 7 | p2 | Add one descriptive visible H1 to the /topic/* template. | /topic/* | developer | small | medium |
| 8 | p2 | Serve the intended homepage at the canonical www root rather than redirecting it to /concepts. | https://machinoai.in/, https://www.machinoai.in/ | developer | medium | medium |
| 9 | p2 | Improve /models as a sourced comparison hub, covering relevant model attributes, use cases, and benchmarks without unsupported rankings. | https://www.machinoai.in/models | content | medium | medium |
| 10 | p2 | Clarify the token calculator’s supported inputs, calculation method, limitations, and relevant links on the tool page. | https://www.machinoai.in/ai-tools/token-calculator | content | small | medium |
| 11 | p2 | Put a concise answer to the backpressure question near the start of the RAG page and organize the explanation into actionable implementation sections. | https://www.machinoai.in/concepts/rag/a-traffic-spike-causes-embedding-api-rate-limits-and-cascading-retries-how-would-you-introduce-backpressure-and-retry-budgets | content | medium | medium |

**1. Investigate and resolve the origin, CDN, application, or rate-limit cause of the sampled 5xx responses, then retest under controlled low concurrency.**
- Why: The crawl observed 59 server errors, including 53 HTTP 503s and 6 HTTP 500s, began encountering errors after 102 pages, and stopped with 267 pages uncrawled.
- Pages: https://www.machinoai.in/jobs/location/london, https://www.machinoai.in/concepts/ai-agents/how-do-you-safely-garbage-collect-ai-agent-memory-tombstones-after-cross-region-replication-and-failback, https://www.machinoai.in/calculators/writing-goal, https://www.machinoai.in/research/longharness-stateful-evidence-management-agentic-reasoning, https://www.machinoai.in/concepts/mlops/how-do-you-validate-numerical-parity-and-decision-consistency-when-migrating-production-ml-inference-runtimes-or-hardware
- Done when: Under a controlled low-concurrency recrawl, the cited URLs and representative pages from affected templates return successful HTML responses, and origin/CDN logs show no corresponding 5xx errors.

**2. Connect Search Console and establish a query and page performance baseline for the site.**
- Why: Search Console is not configured, leaving impressions, clicks, CTR, positions, and measured keyword opportunities unavailable.
- Pages: https://www.machinoai.in/models, https://www.machinoai.in/ai-tools/token-calculator, https://www.machinoai.in/concepts/rag/a-traffic-spike-causes-embedding-api-rate-limits-and-cascading-retries-how-would-you-introduce-backpressure-and-retry-budgets
- Done when: Search Console is connected and verified, and a dated baseline can be retrieved for the cited pages with query impressions, clicks, CTR, and position where available.

**3. Add a PageSpeed API key and rerun measurements for the five priority pages.**
- Why: PageSpeed measured 0 of 5 priority pages because requests returned HTTP 429 and no PAGESPEED_API_KEY was configured.
- Pages: https://www.machinoai.in/concepts, https://www.machinoai.in/research, https://www.machinoai.in/models, https://www.machinoai.in/jobs, https://www.machinoai.in/blogs
- Done when: PageSpeed results are available for all five cited pages and the report records the measurement date and results.

**4. After resolving the server errors, recheck reported internal-link destinations and restore failing pages or correct their source links.**
- Why: The crawl reported 66 source pages linking to destinations that returned 4xx/5xx responses, and many destinations may overlap with the load-associated server errors.
- Pages: https://www.machinoai.in/research/papers, https://www.machinoai.in/models, https://www.machinoai.in/jobs/remote, https://www.machinoai.in/jobs/location/bangalore, https://www.machinoai.in/calculators
- Done when: All 66 reported source-to-destination links are checked after the server issue is addressed, and every destination returns a valid page or its source link is corrected.

**5. Review origin and CDN response times for the slow sampled templates and retest after addressing the server errors.**
- Why: HTML downloads exceeded 1,500 ms on 92 sampled pages, with sampled medians of 1,966 ms for /concepts/*/*, 1,942 ms for /jobs/*, and 1,933 ms for /research/*.
- Pages: https://www.machinoai.in/concepts/rag/a-model-starts-producing-invented-source-urls-despite-receiving-valid-document-ids-how-would-you-make-citation-generation-deterministic-and-verifiable, https://www.machinoai.in/blogs, https://www.machinoai.in/research/memgpt-llms-as-operating-systems, https://www.machinoai.in/jobs/d835b86a-200e-4c47-a87c-688958183f36, https://www.machinoai.in/topic/artificial-intelligence
- Done when: A controlled recrawl records HTML response times under 1,500 ms for the cited URLs and representative pages, with no crawl-induced slowdown or server errors.

**6. Make the /post/* template consistently emit a visible H1, unique title and description, canonical, and the expected article structured data and language attribute.**
- Why: Among sampled /post/* pages, 9 lacked an H1, 9 lacked a title, 9 lacked a meta description, and 9 lacked a canonical; two cited pages also lacked structured data and an html lang attribute.
- Pages: https://www.machinoai.in/post/the-global-it-bloodbath-why-wall-street-is-finally-mll1vbgf, https://www.machinoai.in/post/the-small-business-revolution-why-generative-ai-is-mljly9y2, https://www.machinoai.in/post/the-dawn-of-physical-ai-moving-from-chatbots-to-co-mljllit1, https://www.machinoai.in/post/the-death-of-the-static-image-how-nerf-is-building-mljkp7vv, https://www.machinoai.in/post/the-great-decoupling-ethical-guardrails-vs-open-so-mljjsdci
- Done when: The affected sampled article pages return rendered HTML with one relevant H1, a unique non-empty title and description, a canonical to the preferred final URL, appropriate language markup, and valid BlogPosting and BreadcrumbList data where applicable.

**7. Add one descriptive visible H1 to the /topic/* template.**
- Why: All 6 sampled /topic/* pages lacked an H1, and the template’s sampled median content was 64 words.
- Pages: https://www.machinoai.in/topic/artificial-intelligence, https://www.machinoai.in/topic/machine-learning, https://www.machinoai.in/topic/deep-learning
- Done when: All six sampled /topic/* pages show exactly one relevant H1 in rendered HTML and view-source.

**8. Serve the intended homepage at the canonical www root rather than redirecting it to /concepts.**
- Why: The bare homepage currently resolves through the www root and then to /concepts, while the final URL returns 200.
- Pages: https://machinoai.in/, https://www.machinoai.in/
- Done when: https://machinoai.in/ reaches the intended homepage in one redirect or fewer, and https://www.machinoai.in/ serves that homepage with status 200.

**9. Improve /models as a sourced comparison hub, covering relevant model attributes, use cases, and benchmarks without unsupported rankings.**
- Why: Keyword research identified comparison, RAG suitability, deployment, and benchmark topics for this page, but Search Console metrics are unavailable and the opportunities remain unvalidated.
- Pages: https://www.machinoai.in/models
- Done when: The page contains a useful comparison with verifiable attributes and sourced benchmark context, links to relevant model details, and its query baseline is recorded in Search Console.

**10. Clarify the token calculator’s supported inputs, calculation method, limitations, and relevant links on the tool page.**
- Why: The content recommendation identifies a direct tool-page match for “AI token calculator,” but search demand and current performance are unknown.
- Pages: https://www.machinoai.in/ai-tools/token-calculator
- Done when: The page explains its inputs, calculation method, and limitations, the tool is QA-tested, and its index status and pre-publication Search Console baseline are recorded.

**11. Put a concise answer to the backpressure question near the start of the RAG page and organize the explanation into actionable implementation sections.**
- Why: The sampled RAG page is a specific match for the proposed backpressure and retry-budget topic, but keyword demand and page performance are unavailable.
- Pages: https://www.machinoai.in/concepts/rag/a-traffic-spike-causes-embedding-api-rate-limits-and-cascading-retries-how-would-you-introduce-backpressure-and-retry-budgets
- Done when: The page has a direct answer, clearly labeled implementation sections, attributed sources, at least two contextual internal links, validated structured data, and a recorded Search Console baseline.

## Alerts

| Severity | Type | Detail |
|---|---|---|
| high | critical_issue | The crawl observed 59 server errors (53 HTTP 503s and 6 HTTP 500s), paused, and stopped early; affected URLs may be load- or rate-limit-related and should be retested under lighter load. |
| medium | regression | Observed server errors rose from one in the previous audit to 59, and slow responses were observed on 92 pages versus 17 previously. The previous crawl covered 19 pages compared with 233 fetched this run, so these larger observed counts do not by themselves establish a sitewide regression. |
| medium | data_source_failure | Search Console is not configured, so search metrics and measured keyword opportunities are unavailable. |
| medium | data_source_failure | PageSpeed measured 0 of 5 priority pages because of HTTP 429 responses and no configured PAGESPEED_API_KEY. |

## Template health

| Template | Pages | Errors | Median response | Max response | Median words | No H1 | Structured data |
|---|---|---|---|---|---|---|---|
| /research/* | 35 | 15 | 1933 ms | 3864 ms | 1512 | 0 | BreadcrumbList, Organization, WebSite, ScholarlyArticle, SiteNavigationElement, CollectionPage |
| /jobs/* | 34 | 15 | 1942 ms | 3788 ms | 210 | 0 | BreadcrumbList, Organization, SiteNavigationElement, WebSite, WebPage, CollectionPage |
| /models/* | 34 | 6 | 574 ms | 3464 ms | 1355 | 0 | BreadcrumbList, FAQPage, Organization, SiteNavigationElement, SoftwareApplication, TechArticle, WebSite |
| /concepts/*/* | 34 | 16 | 1966 ms | 4308 ms | 3029 | 0 | BreadcrumbList, Organization, QAPage, SiteNavigationElement, TechArticle, WebSite |
| /post/* | 34 | 5 | 666 ms | 2841 ms | 963 | 9 | Organization, WebSite, BlogPosting, BreadcrumbList |
| /calculators/* | 16 | 1 | 520 ms | 2353 ms | 844 | 0 | BreadcrumbList, FAQPage, Organization, SiteNavigationElement, WebApplication, WebSite |
| /jobs/*/* | 10 | 1 | 494 ms | 2262 ms | 730 | 0 | BreadcrumbList, CollectionPage, Organization, SiteNavigationElement, WebSite |
| /ai-tools/* | 10 | 0 | 518 ms | 1212 ms | 444 | 0 | BreadcrumbList, FAQPage, Organization, SiteNavigationElement, WebApplication, WebSite, SoftwareApplication |
| /topic/* | 6 | 0 | 2682 ms | 3629 ms | 64 | 6 | Organization, WebSite |
| /concepts/* | 6 | 0 | 1593 ms | 1837 ms | 3839 | 0 | BreadcrumbList, FAQPage, Organization, SiteNavigationElement, TechArticle, WebSite |
| /search | 1 | 0 | 328 ms | 328 ms | 280 | 0 | BreadcrumbList, CollectionPage, Organization, SiteNavigationElement, WebSite |
| /concepts | 1 | 0 | 1014 ms | 1014 ms | 142 | 0 | CollectionPage, Organization, SiteNavigationElement, WebSite |
| /research | 1 | 0 | 1758 ms | 1758 ms | 1495 | 0 | BreadcrumbList, CollectionPage, Organization, SiteNavigationElement, WebSite |
| /models | 1 | 0 | 707 ms | 707 ms | 3576 | 0 | BreadcrumbList, CollectionPage, Organization, SiteNavigationElement, WebPage, WebSite |
| /jobs | 1 | 0 | 866 ms | 866 ms | 715 | 0 | BreadcrumbList, CollectionPage, Organization, SiteNavigationElement, WebSite |
| /ai-tools | 1 | 0 | 567 ms | 567 ms | 306 | 0 | BreadcrumbList, CollectionPage, Organization, SiteNavigationElement, WebPage, WebSite |
| /calculators | 1 | 0 | 528 ms | 528 ms | 338 | 0 | BreadcrumbList, CollectionPage, Organization, SiteNavigationElement, WebSite |
| /about | 1 | 0 | 490 ms | 490 ms | 332 | 0 | Organization, WebSite |
| /help | 1 | 0 | 917 ms | 917 ms | 285 | 0 | Organization, WebSite |
| /blogs | 1 | 0 | 3888 ms | 3888 ms | 606 | 0 | BreadcrumbList, CollectionPage, Organization, SiteNavigationElement, WebSite |
| /membership | 1 | 0 | 563 ms | 563 ms | 52 | 0 | Organization, WebSite |
| /teams | 1 | 0 | 500 ms | 500 ms | 46 | 0 | Organization, WebSite |
| /privacy | 1 | 0 | 769 ms | 769 ms | 789 | 0 | Organization, WebSite |
| /terms | 1 | 0 | 500 ms | 500 ms | 657 | 0 | Organization, WebSite |

## Technical findings

| Severity | Issue | Pages | Examples (measured) | Fix | Owner | Done when |
|---|---|---|---|---|---|---|
| high | http_errors | 59 | https://www.machinoai.in/jobs/location/london (HTTP 503 after 2262 ms); https://www.machinoai.in/concepts/ai-agents/how-do-you-safely-garbage-collect-ai-agent-memory-tombstones-after-cross-region-replication-and-failback (HTTP 503 after 2816 ms); https://www.machinoai.in/calculators/writing-goal (H… | Check origin and CDN logs for the crawl window, identify whether capacity, caching, application errors or rate-limit rules caused the 503/500 responses, and address the root cause. Retest the affected URLs under light load before treating individual pages as broken; ensure legitimate search and AI-… | developer | Under a controlled low-concurrency recrawl, the cited URLs and representative pages from the affected templates return successful HTML responses, and server/CDN logs show no corresponding 5xx errors. |
| medium | broken_internal_links | 66 | https://www.machinoai.in/research/papers (links to https://www.machinoai.in/research/longharness-stateful-evidence-management-agentic-reasoning); https://www.machinoai.in/research (links to https://www.machinoai.in/research/longharness-stateful-evidence-management-agentic-reasoning); https://www.ma… | After resolving the server-error/capacity issue, recrawl the reported destinations. For any destination still returning an error, restore the page or update/remove the source link; do not classify transient 5xx responses as permanently broken without a light-load check. | seo | All 66 reported source-to-destination links have been checked after the server issue is addressed, and each destination returns a valid page or the source link has been corrected. |
| medium | slow_server_response | 92 | https://www.machinoai.in/concepts/rag/a-model-starts-producing-invented-source-urls-despite-receiving-valid-document-ids-how-would-you-make-citation-generation-deterministic-and-verifiable (4308 ms); https://www.machinoai.in/blogs (3888 ms); https://www.machinoai.in/research/memgpt-llms-as-operatin… | Review origin/CDN logs, capacity, cache hit rates, application/database response time and rate-limit behavior for slow responses. Prioritize the slow sampled templates, and measure TTFB again under controlled, low-concurrency conditions after addressing the crawl-associated server errors. | developer | A controlled recrawl records HTML response times under 1500 ms for the cited URLs and representative pages, with no crawl-induced slowdown or server errors. |
| medium | missing_h1 | 15 | https://www.machinoai.in/topic/artificial-intelligence (64 words on page); https://www.machinoai.in/topic/machine-learning (64 words on page); https://www.machinoai.in/topic/deep-learning (64 words on page) | Add a single descriptive, visible H1 to the /topic/* and affected /post/* templates. For post pages with very little HTML content, first confirm that the article content is rendered and available to crawlers rather than only checking the heading in isolation. | developer | The cited pages and representative pages from both templates show exactly one relevant H1 in rendered HTML and view-source. |
| medium | missing_title | 9 | https://www.machinoai.in/post/the-global-it-bloodbath-why-wall-street-is-finally-mll1vbgf; https://www.machinoai.in/post/the-small-business-revolution-why-generative-ai-is-mljly9y2; https://www.machinoai.in/post/the-dawn-of-physical-ai-moving-from-chatbots-to-co-mljllit1 | Fix the /post/* metadata generation so every article emits a unique, descriptive title in the initial HTML. Check whether the affected pages share a rendering or data-population failure, since several also have missing H1s and very little HTML text. | developer | Each of the 9 affected URLs returns HTML with a non-empty, page-specific <title>. |
| medium | missing_meta_description | 9 | https://www.machinoai.in/post/the-global-it-bloodbath-why-wall-street-is-finally-mll1vbgf; https://www.machinoai.in/post/the-small-business-revolution-why-generative-ai-is-mljly9y2; https://www.machinoai.in/post/the-dawn-of-physical-ai-moving-from-chatbots-to-co-mljllit1 | Update the /post/* template or article data pipeline to emit a unique, accurate meta description in the initial HTML for each article; investigate overlap with the other missing metadata on these URLs. | developer | Each of the 9 affected URLs has a non-empty, page-specific meta description in the HTML source. |
| medium | homepage_redirects_to_inner_page | 1 | https://machinoai.in/ (https://www.machinoai.in/ -> https://www.machinoai.in/concepts) | Serve a real homepage at the canonical www root. If redirecting the bare domain to www is intended, make it a single direct redirect to https://www.machinoai.in/ rather than forwarding the root to /concepts. | developer | https://machinoai.in/ reaches the intended homepage in one redirect or fewer, and https://www.machinoai.in/ serves the homepage with status 200. |
| low | title_too_long | 103 | https://www.machinoai.in/research (75 chars: AI Research Papers Explained — RAG, Agents, Transformers & LLMs \| MachinoAI); https://www.machinoai.in/models (84 chars: AI Foundation Models Directory — LLM Benchmarks, Specs & RAG Suitability \| MachinoAI); https://www.machinoai.in/jobs/remote (65 cha… | Shorten titles in the affected templates, retaining the primary page topic and brand while removing redundant modifiers. Prioritize extremely long titles and apply template-level limits without forcing every title to the same wording. | seo | Titles on affected sampled pages are concise, unique and within the team’s agreed display-length target; the cited 172-character title is materially shortened. |
| low | description_too_long | 61 | https://www.machinoai.in/concepts (163 chars); https://www.machinoai.in/research (231 chars); https://www.machinoai.in/models (233 chars) | Rewrite affected descriptions to state the page’s main value clearly and concisely; fix generation rules on templates that produce excessively long descriptions, especially the research detail template. | seo | The cited descriptions and representative affected pages have unique, accurate descriptions within the team’s agreed snippet-length target, with the 669-character description replaced. |
| low | thin_content | 20 | https://www.machinoai.in/concepts (142 words); https://www.machinoai.in/membership (52 words); https://www.machinoai.in/topic/artificial-intelligence (64 words) | Inspect the affected pages in rendered browsers and compare rendered text with the HTML response. Restore missing article content if rendering or data is failing; add useful explanatory copy only where a page’s purpose is not adequately served by its current content. | content | The affected sampled pages have been reviewed against their page purpose, and any missing article content is present in rendered HTML; no page has been expanded solely to meet a word-count threshold. |
| low | missing_canonical | 9 | https://www.machinoai.in/post/the-global-it-bloodbath-why-wall-street-is-finally-mll1vbgf; https://www.machinoai.in/post/the-small-business-revolution-why-generative-ai-is-mljly9y2; https://www.machinoai.in/post/the-dawn-of-physical-ai-moving-from-chatbots-to-co-mljllit1 | Ensure the /post/* template emits a self-referencing canonical URL for each indexable article, using the preferred HTTPS www URL and avoiding canonicals to redirects or unrelated pages. | developer | Each of the 9 affected article pages contains one canonical tag pointing to its preferred final URL. |
| low | missing_structured_data | 2 | https://www.machinoai.in/post/the-death-of-the-static-image-how-nerf-is-building-mljkp7vv; https://www.machinoai.in/post/the-great-decoupling-ethical-guardrails-vs-open-so-mljjsdci | Check why these articles do not receive the structured data emitted on other /post/* pages and make the article template consistently output valid BlogPosting and BreadcrumbList markup. | developer | Both cited pages expose valid BlogPosting and BreadcrumbList markup in their rendered HTML, consistent with other article pages. |
| medium | missing_expected_schema | 2 | https://www.machinoai.in/post/the-death-of-the-static-image-how-nerf-is-building-mljkp7vv, https://www.machinoai.in/post/the-great-decoupling-ethical-guardrails-vs-open-so-mljjsdci | Use the /post/* article template to emit accurate BlogPosting schema, including properties supported by the page content, and validate it alongside BreadcrumbList markup. | developer | Both URLs expose valid BlogPosting structured data in rendered HTML and pass Schema.org or Google Rich Results validation without errors. |
| medium | missing_expected_schema | 10 | https://www.machinoai.in/jobs/74389405-9c39-4e55-a18e-b98e21fd5c80, https://www.machinoai.in/jobs/28145b47-978e-4c29-8dea-b1d10c461dff, https://www.machinoai.in/jobs/56e39d8d-4f6a-4029-9de7-5214de2d1e3b | For valid, active job-detail pages in the /jobs/* template, emit JobPosting structured data with accurate job title, hiring organization, location, employment type, date posted and any supported expiry details. Do not apply JobPosting to job listings or location pages. | developer | Every sampled active job-detail page that qualifies exposes valid JobPosting data, while listing and location pages do not incorrectly use JobPosting. |
| low | missing_lang | 2 | https://www.machinoai.in/post/the-death-of-the-static-image-how-nerf-is-building-mljkp7vv; https://www.machinoai.in/post/the-great-decoupling-ethical-guardrails-vs-open-so-mljjsdci | Add the correct document language attribute to the /post/* template and check whether these pages use a different rendering path from other sampled articles. | developer | Both cited pages have an appropriate lang attribute on the root <html> element. |
| low | robots_missing_sitemap | 1 | https://www.machinoai.in/robots.txt (no Sitemap: line) | Add a Sitemap: https://www.machinoai.in/sitemap.xml directive to robots.txt. This is a discovery convenience; the sitemap itself was accessible. | seo | A request to robots.txt returns a Sitemap: directive pointing to the working canonical sitemap URL. |

## Keyword opportunities

| Keyword | Category | Impr. | Clicks | Pos. | Score | Target URL | Action |
|---|---|---|---|---|---|---|---|
| AI model comparison | expand_cluster |  |  |  |  | https://www.machinoai.in/models | Make the /models page a useful comparison hub: add a concise comparison table with verifiable model attributes, explain how to choose by use case, and link to the relevant model detail pages. Add the phrase naturally to the title and H1 if it accurately describes the page. |
| LLM RAG suitability | expand_cluster |  |  |  |  | https://www.machinoai.in/models | On /models, add a clearly labeled RAG-use-case comparison that distinguishes model capabilities using sourced evidence, and link to the model pages. Avoid repeating a generic suitability section without model-specific support. |
| LLM inference latency and throughput | expand_cluster |  |  |  |  | https://www.machinoai.in/models/anthropic-claude-5-5-opus-202609 | On the target model page, add a distinct latency-and-throughput section that states the measurement conditions and sources, or explicitly notes when comparable measurements are unavailable. Link to related model pages and avoid unsupported performance claims. |
| LLM hardware requirements | expand_cluster |  |  |  |  | https://www.machinoai.in/models/anthropic-claude-5-5-opus-202609 | Add a hardware-requirements section to the target page with only verifiable deployment or execution details, clearly separating published specifications from estimates. Link to a broader hardware-sizing guide if the site can support one. |
| LLM deployment architecture | expand_cluster |  |  |  |  | https://www.machinoai.in/models | Add a practical deployment comparison to /models that explains supported deployment options only where verified, and link to model-specific details. Use a separate guide for general deployment architecture rather than duplicating generic copy across every model page. |
| AI model benchmarks | expand_cluster |  |  |  |  | https://www.machinoai.in/models | On /models, explain which benchmarks are reported, their sources, dates, and limitations, and link to model-specific results. Do not present incomparable scores as a direct ranking. |
| AI token calculator | optimize_existing |  |  |  |  | https://www.machinoai.in/ai-tools/token-calculator | On the token-calculator page, make the tool’s purpose and supported inputs clear in the title, H1, and opening paragraph; explain how the result is calculated and link to relevant model pages. Validate the tool’s behavior and terminology before expanding the copy. |
| Claude model comparison | expand_cluster |  |  |  |  | https://www.machinoai.in/models | If the listed Claude pages contain verified, distinct information, add a Claude comparison section to /models with links to each model page and clear criteria. Do not imply that model names, availability, or specifications are current without verification. |
| RAG backpressure and retry budgets | optimize_existing |  |  |  |  | https://www.machinoai.in/concepts/rag/a-traffic-spike-causes-embedding-api-rate-limits-and-cascading-retries-how-would-you-introduce-backpressure-and-retry-budgets | On the concept page, state the problem and answer the backpressure question near the start, then structure the explanation with actionable steps and a concise FAQ. Add internal links from related RAG and architecture pages where contextually useful. |
| LLM architecture and engineering capabilities | expand_cluster |  |  |  |  | https://www.machinoai.in/models | Make /models explain the specific, verifiable criteria used to describe model capabilities and link to evidence on each model page. Replace repeated generic headings with content that differentiates models. |

## Content recommendations

| Priority | Action | Topic | Target URL | Proposed title | Success criteria |
|---|---|---|---|---|---|
| p1 | update | AI token calculator | https://www.machinoai.in/ai-tools/token-calculator | AI Token Calculator: Estimate Tokens for Your Text \| Machinoai | Complete and QA the documented inputs, calculation method, limitations, and links; confirm the page is indexed. By day 90, compare the final 28 days with the pre-publication 28-day baseline and target at least 10% growth in non-brand impressions for relevant calculator queries, while monitoring cli… |
| p2 | update | RAG backpressure and retry budgets | https://www.machinoai.in/concepts/rag/a-traffic-spike-causes-embedding-api-rate-limits-and-cascading-retries-how-would-you-introduce-backpressure-and-retry-budgets | RAG API Rate Limits: Backpressure and Retry Budgets \| MachinoAI | Add a direct answer, clearly labeled implementation sections, attributed sources, and at least two contextual internal links; verify structured data and indexing. By day 90, compare the final 28 days with the pre-publication baseline and target at least 10% growth in impressions for relevant non-br… |
| p2 | update | LLM inference latency and throughput | https://www.machinoai.in/models/anthropic-claude-5-5-opus-202609 | Claude Opus 5.5: Specifications and Inference Performance \| MachinoAI | Publish a verified performance section with attributed sources and measurement conditions, or clearly state which comparable data is unavailable; add contextual internal links and validate structured data. By day 90, compare the final 28 days with the pre-publication baseline and report impressions… |

_Full briefs (outline, questions, internal links, schema) are in the `agent_content_strategy` JSON file in this folder._

## Details

### Technical health

The spread sample fetched 233 of 2,720 sitemap URLs (8.6%) and analyzed 174 HTML pages; 59 responses were errors, and the crawl stopped early with 267 pages uncrawled. Sampled errors were most frequent on /concepts/*/* (16/34), /research/* (15/35), and /jobs/* (15/34). The homepage redirected to /concepts, and all six sampled /topic/* pages lacked an H1.

### Performance

PageSpeed returned HTTP 429 for all five priority pages; no PAGESPEED_API_KEY was configured, so no PageSpeed results are available. Crawler HTML downloads exceeded 1,500 ms on 92 sampled pages; these are crawler-observed timings, not real-user speed measurements.

### Search performance

Search Console is not configured, so impressions, clicks, CTR, positions, and measured search trends are unavailable. No search performance comparison can be made.

### Keyword opportunities

Research suggested opportunities around model comparisons, RAG suitability, model performance, and the token calculator, but all are unvalidated candidates without Search Console metrics.

### Content opportunities

The recommendations focus on improving the existing token calculator, a focused RAG engineering page, and a model detail page. Their search demand and current performance are unknown.

### Ai answer visibility

No AI answer visibility measurements were provided. The audit reported that search and AI-answer crawlers were allowed and observed no bot challenges.

## Data gaps

- PageSpeed failed (http_429) (no PAGESPEED_API_KEY: anonymous quota) for 5 page(s): https://www.machinoai.in/concepts, https://www.machinoai.in/research, https://www.machinoai.in/models, https://www.machinoai.in/jobs, https://www.machinoai.in/blogs
- No trend data source is configured; trend analysis is unavailable.
- Search Console not configured: impressions, clicks, CTR and positions are unavailable.

## Files in this run

- `action_plan.csv`
- `findings.csv`
- `pages.csv`

## Run details

| Agent | Status | Model | Reasoning | Prompt | LLM calls | Input tokens | Output tokens | Est. cost |
|---|---|---|---|---|---|---|---|---|
| seo_audit | succeeded | gpt-6-luna | medium | seo_audit@v4 | 1 | 13,047 | 8,867 | $0.0057 |
| keyword_research | succeeded | gpt-6-luna | medium | keyword_research@v3 | 1 | 4,501 | 3,454 | $0.0022 |
| content_strategy | succeeded | gpt-6-luna | medium | content_strategy@v2 | 1 | 15,689 | 4,344 | $0.0037 |
| performance_reporting | succeeded | gpt-6-luna | medium | performance_reporting@v3 | 1 | 9,895 | 5,023 | $0.0035 |
| **Total** |  |  |  |  | 4 | 43,132 | 21,688 | **$0.0152** |

_Costs are estimates from token counts and list prices (see `llm/pricing.py`); the provider's invoice is authoritative. Observed metrics come from the tools recorded in this run folder; recommendations and expected outcomes are estimates, not guarantees._
