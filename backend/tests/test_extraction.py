from scrapling.parser import Selector

from app.models.schemas import AIChoice
from app.services.extraction import build_prompt_candidates, generate_candidates, select_verified_element


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
    assert len(str(prompt)) <= 500


def test_invalid_candidate_index_is_not_trusted():
    page = Selector(content="<html><body><div id='price'>$29.99</div></body></html>", url="https://example.com")
    candidates = generate_candidates(page, "price", None)
    choice = AIChoice(found=True, candidate_index=999, selector="#price", value="$29.99", value_source="text", confidence=.9, reason="price")
    assert select_verified_element(page, candidates, choice) is None

