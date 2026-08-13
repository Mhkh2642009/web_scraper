import requests
from bs4 import BeautifulSoup

url = input('enter the url: ')

response = requests.get(url)

if response.status_code == 200:
    scrap = BeautifulSoup(response.content, 'html.parser')

    for tag in scrap(["script", "style", "noscript"]):
        tag.decompose()

    text = scrap.get_text(" ", strip=True)
    print(text)