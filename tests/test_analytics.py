import html as html_lib
import os
import re
from urllib.parse import urlparse

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
ANALYTICS_ANCHOR = re.compile(r'<a\b[^>]*href="/analytics"[^>]*>', re.S)


def post_login(client, email="demo@spendly.com", password="demo123", **kwargs):
    return client.post("/login", data={"email": email, "password": password}, **kwargs)


def body(response):
    return response.get_data(as_text=True)


def redirect_path(response):
    return urlparse(response.headers["Location"]).path


def read_project_file(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def normalised(text):
    """Unescape HTML entities and collapse all whitespace."""
    return re.sub(r"\s+", " ", html_lib.unescape(text))


def analytics_html(client):
    post_login(client)
    return body(client.get("/analytics"))


def analytics_anchor(html):
    match = ANALYTICS_ANCHOR.search(html)
    assert match, "Analytics nav link not found"
    return match.group(0)


# --- Access control -------------------------------------------------- #

def test_analytics_requires_login_redirects(client):
    response = client.get("/analytics")
    assert response.status_code == 302
    assert redirect_path(response) == "/login"


def test_analytics_signed_in_returns_200(client):
    post_login(client)
    assert client.get("/analytics").status_code == 200


def test_analytics_after_logout_redirects(client):
    post_login(client)
    client.get("/logout")
    response = client.get("/analytics")
    assert response.status_code == 302
    assert redirect_path(response) == "/login"


def test_analytics_stale_session_user_redirects_and_clears_session(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 999999
        sess["user_name"] = "Ghost"
    response = client.get("/analytics")
    assert response.status_code == 302
    assert redirect_path(response) == "/login"
    with client.session_transaction() as sess:
        assert "user_id" not in sess, "session should be cleared"
        assert "user_name" not in sess, "session should be cleared"


# --- Page content ---------------------------------------------------- #

def test_analytics_shows_coming_soon_badge(client):
    assert "Coming Soon" in analytics_html(client)


def test_analytics_shows_heading(client):
    html = analytics_html(client)
    assert re.search(r"<h1[^>]*>\s*Advanced Analytics\s*</h1>", html) or (
        "Advanced Analytics" in html
    )
    assert "Advanced Analytics" in html


def test_analytics_shows_body_text_ignoring_line_breaks(client):
    text = normalised(analytics_html(client))
    expected = (
        "We're working on powerful insights and visualizations to help you "
        "understand your spending patterns better."
    )
    assert expected in text


def test_analytics_shows_caption(client):
    text = normalised(analytics_html(client))
    assert "We're crafting something special" in text


def test_analytics_links_page_stylesheet(client):
    assert "css/analytics.css" in analytics_html(client)


def test_analytics_renders_inside_base_layout(client):
    html = analytics_html(client)
    assert "Sign out" in html, "base navbar should be rendered"
    assert "<html" in html


def test_analytics_template_extends_base():
    template = read_project_file("templates", "analytics.html")
    assert re.search(r"{%-?\s*extends\s+[\"']base\.html[\"']\s*-?%}", template)


# --- Navbar ---------------------------------------------------------- #

@pytest.mark.parametrize("path", ["/", "/login", "/register"])
def test_navbar_hides_analytics_link_when_logged_out(client, path):
    html = body(client.get(path))
    assert not ANALYTICS_ANCHOR.search(html), f"Analytics link leaked on {path}"


@pytest.mark.parametrize("path", ["/profile", "/analytics"])
def test_navbar_shows_analytics_link_when_logged_in(client, path):
    post_login(client)
    html = body(client.get(path))
    anchor = analytics_anchor(html)
    assert anchor
    segment = html[html.index(anchor):]
    assert re.match(re.escape(anchor) + r"\s*Analytics\s*</a>", segment)


def test_navbar_analytics_link_disappears_after_logout(client):
    post_login(client)
    client.get("/logout")
    html = body(client.get("/"))
    assert not ANALYTICS_ANCHOR.search(html)


# --- Active state ---------------------------------------------------- #

def test_analytics_link_is_active_on_analytics_page(client):
    anchor = analytics_anchor(analytics_html(client))
    assert re.search(r'class="[^"]*\bactive\b[^"]*"', anchor), anchor
    assert 'aria-current="page"' in anchor, anchor


def test_analytics_link_not_active_on_profile_page(client):
    post_login(client)
    anchor = analytics_anchor(body(client.get("/profile")))
    assert not re.search(r'class="[^"]*\bactive\b[^"]*"', anchor), anchor
    assert "aria-current" not in anchor, anchor


# --- Constraints ----------------------------------------------------- #

def test_analytics_template_has_no_hex_or_inline_styles():
    template = read_project_file("templates", "analytics.html")
    assert not HEX_COLOUR.search(template)
    assert "style=" not in template
    assert "<style" not in template


def test_analytics_css_uses_variables_only():
    css = read_project_file("static", "css", "analytics.css")
    assert not HEX_COLOUR.search(css)
