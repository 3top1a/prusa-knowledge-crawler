from bs4 import BeautifulSoup
import html2text
import requests
import xmltodict
import logging
from alive_progress import alive_it
import argparse
import colorlog

# Logging
logging.basicConfig(level=logging.DEBUG)
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter('%(log_color)s%(levelname)s:%(name)s:%(message)s'))
logger = colorlog.getLogger('example')
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Arguments
parser = argparse.ArgumentParser(description='Scrape the prusaknowledge base into a Markdown file.')
parser.add_argument('-o', '--output', type=str, default=None, help='Output file. Overwrites the contents.')
parser.add_argument('--lang', type=str, default='en', help='Language filter for URLs. Use shorthands such as `en` or `cs`.')
parser.add_argument('--images', default=False, action='store_true', help='Also scrape images. Most are encoded as raw base64, beware of file sizes.')
parser.add_argument('--compress', default=False, action='store_true', help='Removes any whitespace.')
parser.add_argument('-l', '--limit', type=int, default=10, help='Maximum number of sites to process. Set to 10 000 to crawl the whole knowledge base.')
args = parser.parse_args()

language_filter = args.lang
site_limit = args.limit
file_output = None
if args.output:
    file_output = open(args.output, 'w')


blog_types = ["article", "guide"] # Basically everything besides categories
session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://help.prusa3d.com/',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'script',
    'Sec-Fetch-Mode': 'no-cors',
    'Sec-Fetch-Site': 'same-site',
}
h = html2text.HTML2Text()
h.ignore_images = not args.images
h.images_to_alt = not args.images
h.ignore_tables = True # Incorrect detection, makes the output wierd
h.body_width = 0 # Do not break up long lines. The detection algo doesn't work well with links

# Parse sitemap and generate list of URLs
sitemap_xml = requests.get("https://help.prusa3d.com/sitemap.xml")
raw_sitemap = xmltodict.parse(sitemap_xml.text)
raw_links = list(map(lambda x: x['xhtml:link'], raw_sitemap['urlset']['url']))

logging.info(f"Starting scrape with max {site_limit} items")

# Filter URLs into `urls` set
urls = set()
for link in raw_links:
    # Filter by language, LLMs are mainly trained on english text so making english the default makes sense
    url_language_filtered = list(filter(lambda x: x['@hreflang'] == language_filter, link))
    url = url_language_filtered[-1]['@href']
    # Check the site type is within whitelist
    url_without_prefix = url[25:]
    if not any([url_without_prefix.startswith(x) for x in blog_types]):
        continue

    # All the filters have been passed
    urls.add(url)

logging.info(f"Found {len(urls)} sites")

# Request each entry (with max limit)
for entry in alive_it(list(urls)[0:site_limit]):
    response = session.get(entry, headers=headers)

    if response.status_code != 200:
        logging.error(f"Failed to retrieve webpage {entry} - status code {response.status_code}")
        continue

    logging.debug(f"Scraping {entry}")

    # Use bs4 to remove footers, headers and nav to clean up the HTML
    soup = BeautifulSoup(response.content, 'html.parser')
    for element in soup.find_all(['footer', 'header', 'nav', 'script']):
        element.decompose()

    # Remove the support section
    soup.find_all(lambda tag: tag.name == "div" and "Still have questions?" in tag.text)[-1].decompose()
    # Remove rating section
    soup.find_all(lambda tag: tag.name == "div" and "helpful?" in tag.text)[-1].decompose()
    # Remove language section
    c = soup.find_all(lambda tag: tag.name == "div" and "This article is also available in following languages:" in tag.text)
    if c:
        c[-1].decompose()
    # Remove comment section
    c = soup.find_all(lambda tag: tag.name == "div" and "Comments" in tag.text)
    if c:
        if c[-1]:
            c[-1].decompose()

    # Remove the search section
    soup.find_all(lambda tag: tag.name == "ul" and "Home" in tag.text)[0].decompose()
    # Remove last updated text
    c = soup.find_all(lambda tag: "Last updated" in tag.text)
    if c:
        c[-1].decompose()
    # Remove relevant for
    relevantfor = soup.find_all(lambda tag: "Relevant for:" in tag.text)
    if relevantfor:
        relevantfor[-1].decompose()
    # Remove emptyish text paragraphs
    target_div = soup.find_all(lambda tag: tag.name == "p" and len(tag.text) < 25)
    for t in target_div:
        t.decompose()
    # Remove the leftmost nav bar
    soup.find_all(lambda tag: tag.name == "ul")[0].decompose()

    # Find the div with the most paragraph headers
    # TODO: does not work for guides as those use nested divs with spans and inline text
    paragraphs = soup.find_all(lambda tag: tag.name == "p")
    parent_scores = {}
    for p in paragraphs:
        parent = p.parent
        if parent in parent_scores:
            parent_scores[parent] += 1
        else:
            parent_scores[parent] = 1

    # Sort
    best = None
    best_v = 0
    for (key, value) in parent_scores.items():
        if value > best_v:
            best_v = value
            best = key
    
    if best is None:
        logging.error(f"Failed to extract any text from {entry}")
        continue

    text = h.handle(str(best))
    text = text.replace("---", "***")
    # Add meta to the start
    title = soup.find('title').string.replace(" | Prusa Knowledge Base", "")
    # text = f"\n---\nURL: {entry}\nTITLE: {title}\n\n" + text.strip() + "\n"
    text = f"\n---\n# [{title}]({entry})\n\n" + text.strip() + "\n"
    
    if args.compress:
        # TODO
        pass

    if file_output:
        file_output.write(text)
    else:
        print(text)
