# prusa-knowledge-crawler
A simple (and slow) crawler for the Prusa Knowledge Base.

A few test crawls are done in CI, and the entire knowledge base is crawled each release and published.
One full crawl should take about 30 minutes.
It is intentionally slow as to not overwhelm the servers.
Output is in Markdown, images are removed because they are many times stored as raw base64.
