from flask import Flask, render_template, request, jsonify
from urllib.parse import urlparse, quote_plus, urljoin
from bs4 import BeautifulSoup
import requests
import json
import re
import socket
import ipaddress
from decimal import Decimal, InvalidOperation

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml"
}

TIMEOUT = 15
MAX_REDIRECTS = 5
MAX_PAGE_SIZE = 3 * 1024 * 1024

def safe_url(url):
    """Allow only public HTTP/HTTPS URLs."""

    try:
        parsed = urlparse(url.strip())

        if parsed.scheme not in ("http", "https"):
            return False

        if not parsed.hostname:
            return False

        if parsed.username or parsed.password:
            return False

        if parsed.port and parsed.port not in (80, 443):
            return False

        hostname = parsed.hostname

        if hostname.lower() == "localhost":
            return False

        addresses = socket.getaddrinfo(
            hostname, None, type=socket.SOCK_STREAM
        )

        if not addresses:
            return False

        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])

            if not ip.is_global:
                return False

        return True

    except (ValueError, socket.gaierror, OSError):
        return False

def clean(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()

def flatten_jsonld(data):
    if isinstance(data, list):
        for item in data:
            yield from flatten_jsonld(item)

    elif isinstance(data, dict):
        if "@graph" in data:
            yield from flatten_jsonld(data["@graph"])

        yield data

def get_page(url):
    """Fetch a page while checking every redirect destination."""

    current_url = url

    for _ in range(MAX_REDIRECTS + 1):

        if not safe_url(current_url):
            raise ValueError("Unsafe or invalid website URL.")

        response = requests.get(
            current_url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=False,
            stream=True
        )

        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()

            if not location:
                raise ValueError("Website returned an invalid redirect.")

            current_url = urljoin(current_url, location)
            continue

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "html" not in content_type:
            response.close()
            raise ValueError("This link does not contain an HTML product page.")

        content_length = response.headers.get("Content-Length")

        if content_length:
            try:
                if int(content_length) > MAX_PAGE_SIZE:
                    response.close()
                    raise ValueError("Product page is too large.")
            except ValueError as error:
                response.close()
                if "too large" in str(error):
                    raise

        chunks = []
        size = 0

        try:
            for chunk in response.iter_content(16384):
                if not chunk:
                    continue

                size += len(chunk)

                if size > MAX_PAGE_SIZE:
                    raise ValueError("Product page is too large.")

                chunks.append(chunk)

            response.encoding = response.encoding or "utf-8"
            content = b"".join(chunks).decode(
                response.encoding, errors="replace"
            )

            return content, current_url

        finally:
            response.close()

    raise ValueError("Too many website redirects.")

def get_meta(soup, *selectors):
    for selector, attribute in selectors:
        element = soup.select_one(selector)

        if element:
            value = (
                element.get(attribute)
                if attribute
                else element.get_text(" ", strip=True)
            )

            if value:
                return clean(value)

    return ""

def get_number(value):
    """Extract a valid decimal number."""

    value = clean(value)

    if not value:
        return None

    match = re.search(r"\d+(?:[.,]\d+)*", value)

    if not match:
        return None

    number = match.group().replace(",", "")

    try:
        return Decimal(number)
    except InvalidOperation:
        return None

def get_product(url):

    if not safe_url(url):
        raise ValueError("Invalid or unsafe product URL.")

    html, final_url = get_page(url)

    soup = BeautifulSoup(html, "html.parser")

    product = None

    scripts = soup.find_all(
        "script",
        attrs={"type": re.compile(r"ld\+json", re.I)}
    )

    for script in scripts:
        try:
            data = json.loads(
                script.string or script.get_text()
            )

            for item in flatten_jsonld(data):

                types = item.get("@type", [])

                if isinstance(types, str):
                    types = [types]

                if any(
                    str(t).lower().endswith("product")
                    for t in types
                ):
                    product = item
                    break

        except (ValueError, TypeError):
            continue

        if product:
            break

    name = ""
    price = ""
    currency = ""
    rating = ""
    review_count = ""
    description = ""
    image = ""
    reviews = []

    if product:

        name = clean(product.get("name"))
        description = clean(product.get("description"))

        image = product.get("image", "")

        if isinstance(image, list):
            image = image[0] if image else ""

        if isinstance(image, dict):
            image = image.get("url", "")

        offers = product.get("offers", {})

        if isinstance(offers, list):
            offers = offers[0] if offers else {}

        if isinstance(offers, dict):
            price = clean(
                offers.get("price")
                or offers.get("lowPrice")
            )

            currency = clean(
                offers.get("priceCurrency")
            )

        aggregate = product.get("aggregateRating", {})

        if isinstance(aggregate, dict):
            rating = clean(aggregate.get("ratingValue"))

            review_count = clean(
                aggregate.get("reviewCount")
                or aggregate.get("ratingCount")
            )

        raw_reviews = product.get("review", [])

        if isinstance(raw_reviews, dict):
            raw_reviews = [raw_reviews]

        if isinstance(raw_reviews, list):
            for review in raw_reviews[:8]:

                if not isinstance(review, dict):
                    continue

                author = review.get("author", {})

                if isinstance(author, dict):
                    author = author.get("name", "Customer")

                review_rating = review.get(
                    "reviewRating", {}
                )

                if isinstance(review_rating, dict):
                    review_rating = review_rating.get(
                        "ratingValue", ""
                    )

                reviews.append({
                    "author": clean(author) or "Customer",
                    "rating": clean(review_rating),
                    "text": clean(
                        review.get("reviewBody")
                        or review.get("description")
                    )
                })

    # Open Graph and standard metadata fallbacks

    name = name or get_meta(
        soup,
        ('meta[property="og:title"]', "content"),
        ('meta[name="twitter:title"]', "content"),
        ("title", None)
    )

    description = description or get_meta(
        soup,
        ('meta[property="og:description"]', "content"),
        ('meta[name="description"]', "content")
    )

    image = image or get_meta(
        soup,
        ('meta[property="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content")
    )

    price = price or get_meta(
        soup,
        ('meta[property="product:price:amount"]', "content"),
        ('meta[itemprop="price"]', "content"),
        ('meta[property="og:price:amount"]', "content")
    )

    currency = currency or get_meta(
        soup,
        ('meta[property="product:price:currency"]', "content"),
        ('meta[itemprop="priceCurrency"]', "content"),
        ('meta[property="og:price:currency"]', "content")
    )

    rating = rating or get_meta(
        soup,
        ('meta[itemprop="ratingValue"]', "content"),
        ('meta[property="product:rating"]', "content")
    )

    review_count = review_count or get_meta(
        soup,
        ('meta[itemprop="reviewCount"]', "content"),
        ('meta[itemprop="ratingCount"]', "content")
    )

    if not name:
        name = urlparse(final_url).netloc

    if image:
        image = urljoin(final_url, image)

    review_link = (
        "https://www.google.com/search?q="
        + quote_plus(name + " reviews")
    )

    return {
        "name": name,
        "url": final_url,
        "store": urlparse(final_url).netloc,
        "price": price,
        "currency": currency.upper(),
        "rating": rating,
        "review_count": review_count,
        "description": description[:500],
        "image": image,
        "reviews": reviews,
        "review_link": review_link
    }

def compare_products(products):
    """Compare prices only when currencies match."""

    prices = []
    ratings = []

    for product in products:

        price_value = get_number(product["price"])

        if price_value is not None:
            prices.append((price_value, product))

        rating_value = get_number(product["rating"])

        if rating_value is not None:
            ratings.append((rating_value, product))

    lowest_price = None
    highest_rating = None
    best_value = None

    if prices:
        currencies = {
            p["currency"] for _, p in prices
        }

        if len(currencies) == 1:
            lowest_price = min(
                prices, key=lambda item: item[0]
            )[1]["url"]

    if ratings:
        highest_rating = max(
            ratings, key=lambda item: item[0]
        )[1]["url"]

    # Best value is calculated only when all compared
    # products have a price and rating in one currency.

    if len(products) >= 2:
        complete = [
            p for p in products
            if get_number(p["price"]) is not None
            and get_number(p["rating"]) is not None
        ]

        currencies = {
            p["currency"] for p in complete
        }

        if len(complete) >= 2 and len(currencies) == 1:

            max_price = max(
                get_number(p["price"]) for p in complete
            )

            max_rating = max(
                get_number(p["rating"]) for p in complete
            )

            if max_price > 0 and max_rating > 0:

                def score(product):
                    price_score = (
                        get_number(product["price"]) / max_price
                    )

                    rating_score = (
                        get_number(product["rating"]) / max_rating
                    )

                    # Equal weight for price and rating.
                    return (
                        (Decimal("1") - price_score) * Decimal("0.5")
                        + rating_score * Decimal("0.5")
                    )

                best_value = max(
                    complete, key=score
                )["url"]

    return {
        "lowest_price": lowest_price,
        "highest_rating": highest_rating,
        "best_value": best_value
    }

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/compare", methods=["POST"])
def compare():

    data = request.get_json(silent=True) or {}

    urls = data.get("urls", [])

    if isinstance(urls, str):
        urls = urls.splitlines()

    if not isinstance(urls, list):
        return jsonify({
            "error": "Invalid product links format."
        }), 400

    urls = list(dict.fromkeys(
        u.strip()
        for u in urls
        if isinstance(u, str) and u.strip()
    ))[:5]

    if not urls:
        return jsonify({
            "error": "Please enter at least one product link."
        }), 400

    products = []
    errors = []

    for url in urls:
        try:
            products.append(get_product(url))

        except requests.exceptions.Timeout:
            errors.append({
                "url": url,
                "error": "Website request timed out."
            })

        except requests.exceptions.RequestException:
            errors.append({
                "url": url,
                "error": "Could not access this website."
            })

        except Exception as error:
            errors.append({
                "url": url,
                "error": str(error)
            })

    highlights = compare_products(products)

    return jsonify({
        "products": products,
        "errors": errors,
        "highlights": highlights,
        "total_submitted": len(urls),
        "total_successful": len(products)
    })

@app.route("/api/search-links", methods=["POST"])
def search_links():

    data = request.get_json(silent=True) or {}

    query = clean(data.get("query"))

    if not query:
        return jsonify({
            "error": "Enter a product name."
        }), 400

    if len(query) > 150:
        return jsonify({
            "error": "Search query is too long."
        }), 400

    q = quote_plus(query)

    return jsonify({
        "links": [
            {
                "name": "Google Shopping",
                "url": f"https://www.google.com/search?tbm=shop&q={q}"
            },
            {
                "name": "Google Reviews",
                "url": f"https://www.google.com/search?q={q}+reviews"
            },
            {
                "name": "Bing Shopping",
                "url": f"https://www.bing.com/shop?q={q}"
            }
        ]
    })

@app.errorhandler(413)
def file_too_large(error):
    return jsonify({
        "error": "Request is too large."
    }), 413

@app.errorhandler(404)
def page_not_found(error):
    return jsonify({
        "error": "Requested page was not found."
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "An internal server error occurred."
    }), 500

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )