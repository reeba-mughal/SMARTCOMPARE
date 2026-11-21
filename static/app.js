
const compareBtn = document.getElementById("compareBtn");
const searchBtn = document.getElementById("searchBtn");

const urlsInput = document.getElementById("urls");
const productNameInput = document.getElementById("productName");

const statusBox = document.getElementById("status");
const searchLinks = document.getElementById("searchLinks");

const resultsSection = document.getElementById("resultsSection");
const resultsContainer = document.getElementById("results");
const highlightsContainer = document.getElementById("highlights");
const errorsContainer = document.getElementById("errors");

// Protect displayed text from HTML injection
function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[char]);
}

// Show errors
function showError(message) {
    statusBox.textContent = message;
    statusBox.style.color = "red";
}

// COMPARE PRODUCTS
compareBtn.addEventListener("click", async () => {

    const urls = urlsInput.value
        .split("\n")
        .map(url => url.trim())
        .filter(url => url.length > 0);

    if (urls.length === 0) {
        showError("Please paste at least one product URL.");
        return;
    }

    if (urls.length > 5) {
        showError("Maximum 5 product links are allowed.");
        return;
    }

    compareBtn.disabled = true;
    compareBtn.textContent = "Comparing...";
    statusBox.textContent = "Please wait. Fetching product information...";
    statusBox.style.color = "#315efb";

    try {
        const response = await fetch("/api/compare", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ urls: urls })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Comparison failed.");
        }

        displayResults(data);

        if (data.products && data.products.length > 0) {
            statusBox.textContent = "Comparison completed!";
            statusBox.style.color = "green";
        } else {
            statusBox.textContent =
                "Products could not be extracted. Check the links or try another store.";
            statusBox.style.color = "red";
        }

    } catch (error) {
        showError("Error: " + error.message);
    } finally {
        compareBtn.disabled = false;
        compareBtn.textContent = "Compare Products →";
    }
});


// DISPLAY COMPARISON RESULTS
function displayResults(data) {

    resultsSection.hidden = false;

    const products = data.products || [];
    const highlights = data.highlights || {};
    const errors = data.errors || [];

    resultsContainer.innerHTML = "";
    highlightsContainer.innerHTML = "";
    errorsContainer.innerHTML = "";

    if (products.length === 0) {
        resultsContainer.innerHTML =
            "<p>No products could be extracted from these links.</p>";
    }

    // Product cards
    products.forEach(product => {

        const reviews = Array.isArray(product.reviews)
            ? product.reviews
            : [];

        const reviewsHTML = reviews.length
            ? reviews.map(review => `
                <div class="review">
                    <b>${escapeHTML(review.author || "Customer")}</b>
                    <span>Rating: ${escapeHTML(review.rating || "N/A")}</span>
                    <p>${escapeHTML(review.text || "")}</p>
                </div>
            `).join("")
            : "<p>No structured customer reviews found.</p>";

        const card = document.createElement("div");
        card.className = "product-card";

        card.innerHTML = `
            ${product.image
                ? `<img src="${escapeHTML(product.image)}"
                    alt="${escapeHTML(product.name)}">`
                : ""
            }

            <h3>${escapeHTML(product.name)}</h3>

            <p><strong>Store:</strong>
                ${escapeHTML(product.store)}
            </p>

            <p class="price">
                ${escapeHTML(product.currency)}
                ${escapeHTML(product.price || "Price unavailable")}
            </p>

            <p><strong>Rating:</strong>
                ${escapeHTML(product.rating || "Not available")}
            </p>

            <p><strong>Review Count:</strong>
                ${escapeHTML(product.review_count || "Not available")}
            </p>

            <p>${escapeHTML(product.description || "No description available.")}</p>

            <a href="${escapeHTML(product.url)}"
               target="_blank"
               rel="noopener noreferrer">
               Visit Store
            </a>

            <br>

            <a href="${escapeHTML(product.review_link)}"
               target="_blank"
               rel="noopener noreferrer">
               Find Customer Reviews
            </a>

            <h4>Customer Reviews</h4>

            ${reviewsHTML}
        `;

        resultsContainer.appendChild(card);
    });

    // Lowest price and highest rating
    highlightsContainer.innerHTML = `
        <div class="highlight">
            Lowest Price:
            ${highlights.lowest_price
                ? escapeHTML(highlights.lowest_price)
                : "Not available"}
        </div>

        <div class="highlight">
            Highest Rating:
            ${highlights.highest_rating
                ? escapeHTML(highlights.highest_rating)
                : "Not available"}
        </div>
    `;

    // Show errors
    if (errors.length > 0) {

        errorsContainer.innerHTML = `
            <h3>Some products could not be processed:</h3>

            ${errors.map(error => `
                <div>
                    <strong>${escapeHTML(error.url)}</strong>
                    <p>${escapeHTML(error.error)}</p>
                </div>
            `).join("")}
        `;
    }

    resultsSection.scrollIntoView({
        behavior: "smooth"
    });
}


// SEARCH PRODUCT
searchBtn.addEventListener("click", async () => {

    const query = productNameInput.value.trim();

    if (!query) {
        alert("Please enter a product name.");
        return;
    }

    searchBtn.disabled = true;
    searchBtn.textContent = "Searching...";

    searchLinks.innerHTML = "<p>Searching for product links...</p>";

    try {

        const response = await fetch("/api/search-links", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ query: query })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Search failed.");
        }

        searchLinks.innerHTML = `
            <h3>Shopping & Review Links</h3>

            ${(data.links || []).map(link => `
                <div class="search-link">
                    <a href="${escapeHTML(link.url)}"
                       target="_blank"
                       rel="noopener noreferrer">
                        ${escapeHTML(link.name)}
                    </a>
                </div>
            `).join("")}
        `;

    } catch (error) {

        searchLinks.innerHTML =
            `<p style="color:red;">${escapeHTML(error.message)}</p>`;

    } finally {

        searchBtn.disabled = false;
        searchBtn.textContent = "Search";
    }
});
