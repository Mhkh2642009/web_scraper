from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

url = input('enter the url: ')
wanted = input('what you want: ').split(' ')

options = Options()
options.add_argument("--headless")

driver = webdriver.Chrome(options=options)

driver.get(url)

html = driver.page_source

driver.quit()


scrap = BeautifulSoup(html, 'html.parser')

# for i in wanted:
#     block = scrap.find(string=lambda text: text and (i or i.lower() or i.upper()) in text)
#     parent_block = block.parent
#     print('block is')
#     print(parent_block)


for tag in scrap(["script", "style", "noscript"]):
    tag.decompose()

text = scrap.get_text(" ", strip=True)
print('the whole')
print(text)