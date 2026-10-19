"""The About page (B42, #80): the landing page inside the app is a page like the others, so the chat's page context
may name it. Check ids: B42.n."""
from app import page_context


def test_b42_5_the_about_page_is_a_page_the_chat_may_name():
    def resolve(_: str) -> None:
        return None

    assert page_context.validate({"page": "about"}, resolve) == ({"page": "about"}, [])
    assert page_context.validate({"page": "nope"}, resolve) == ({}, ["page=nope"])  # still a fixed list
