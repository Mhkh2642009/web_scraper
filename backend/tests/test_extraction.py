from scrapling.parser import Selector

from app.models.schemas import AIChoice
from app.services.extraction import build_prompt_candidates, build_source_preview, generate_candidates, select_verified_element


def test_dom_candidates_exclude_scripts_and_are_bounded():
    html = """
    <html><body>
      <script>secret()</script><style>.hidden { display: none }</style>
      <div id='price'>$29.99</div><p data-testid='summary'>A useful summary</p>
    </body></html>
    """
    page = Selector(content=html, url="https://example.com")
    candidates = generate_candidates(page, "find the product price", "#old-price")
    assert candidates
    assert all(candidate.tag not in {"script", "style"} for candidate in candidates)
    prompt = build_prompt_candidates(candidates, 300)
    assert prompt
    assert len(prompt) <= 300
    assert "<script" not in prompt
    assert "candidate_index" not in prompt


def test_invalid_candidate_index_is_not_trusted():
    page = Selector(content="<html><body><div id='price'>$29.99</div></body></html>", url="https://example.com")
    candidates = generate_candidates(page, "price", None)
    choice = AIChoice(found=True, candidate_index=999, selector="#price", value="$29.99", value_source="text", confidence=.9, reason="price")
    assert select_verified_element(page, candidates, choice) is None


def test_price_candidates_outrank_feedback_and_review_noise():
    html = """
    <html><body>
      <form id='feedbackForm'><div class='priceavailability'>Price (EGP) Shipping cost (EGP)</div></form>
      <section id='reviewsMedley'><p>Customers mention an amazing price in reviews.</p></section>
      <div id='corePriceDisplay_desktop_feature_div'><span class='a-price'><span class='a-offscreen'>EGP500.29</span></span></div>
    </body></html>
    """
    page = Selector(content=html, url="https://example.com")
    candidates = generate_candidates(page, "Find the product price", ".cost")
    price_candidate = next(candidate for candidate in candidates if candidate.text == "EGP500.29")
    feedback_candidate = next(candidate for candidate in candidates if "Price (EGP)" in candidate.text)
    review_candidate = next(candidate for candidate in candidates if "Customers mention" in candidate.text)
    assert price_candidate.score > feedback_candidate.score
    assert price_candidate.score > review_candidate.score
    assert candidates[0].text == "EGP500.29"


def test_arabic_currency_price_is_ranked_as_a_price():
    page = Selector(
        content="<html><body><nav>Store</nav><div class='card'><div>220 ج.م</div><p>Shipping in 2 days</p></div></body></html>",
        url="https://example.com",
    )
    candidates = generate_candidates(page, "what is the price of the book?", "#price12")
    assert candidates[0].text == "220 ج.م"


def test_source_preview_removes_executable_markup_and_stays_bounded():
    page = Selector(
        content="<html><head><meta name='csrf-token' content='secret'><script>secret()</script></head><body><main><h1>Visible title</h1></main><style>.x{}</style></body></html>",
        url="https://example.com",
    )
    preview = build_source_preview(page, 90)
    assert "Visible title" in preview
    assert "secret" not in preview
    assert "<script" not in preview
    assert len(preview) <= 90
