from scrapling.fetchers import DynamicFetcher

url = input("Enter URL: ")

try:
    page = DynamicFetcher.fetch(
        url,
        headless=True,
        network_idle=True
    )

    text = page.get_all_text(strip=True)

    print("\n========== PAGE TEXT ==========\n")
    print(text)

except Exception as e:
    print("Error:", e)