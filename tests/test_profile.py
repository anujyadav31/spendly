import os
import re
from urllib.parse import urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def post_login(client, email="demo@spendly.com", password="demo123", **kwargs):
    return client.post("/login", data={"email": email, "password": password}, **kwargs)


def body(response):
    return response.get_data(as_text=True)


def redirect_path(response):
    return urlparse(response.headers["Location"]).path


def read_project_file(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def profile_html(client):
    post_login(client)
    return body(client.get("/profile"))


# --- Access control -------------------------------------------------- #

def test_profile_requires_login_redirects(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert redirect_path(response) == "/login"


def test_profile_signed_in_returns_200(client):
    post_login(client)
    assert client.get("/profile").status_code == 200


def test_login_lands_on_profile(client):
    response = post_login(client, follow_redirects=True)
    assert response.request.path == "/profile"
    html = body(response)
    assert "Your profile" in html
    assert "Welcome back" not in html


def test_profile_after_logout_redirects(client):
    post_login(client)
    client.get("/logout")
    response = client.get("/profile")
    assert response.status_code == 302
    assert redirect_path(response) == "/login"


# --- Page content ---------------------------------------------------- #

def test_profile_shows_user_card(client):
    html = profile_html(client)
    assert "profile-user" in html
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert "Member since" in html
    avatar = re.search(r'class="profile-avatar"[^>]*>\s*(\w+)\s*<', html)
    assert avatar and avatar.group(1) == "DU"


def test_profile_shows_three_stats(client):
    html = profile_html(client)
    assert html.count('class="profile-card profile-stat"') >= 3
    for label in ("Total spent", "Transactions", "Top category"):
        assert label in html


def test_profile_table_has_at_least_three_rows(client):
    html = profile_html(client)
    tbody = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    assert tbody, "transaction table body missing"
    assert tbody.group(1).count("<tr>") >= 3


def test_profile_category_badges_use_classes(client):
    html = profile_html(client)
    assert 'class="cat-badge cat-bills"' in html
    assert 'class="cat-badge cat-food"' in html


def test_profile_shows_category_breakdown(client):
    html = profile_html(client)
    assert len(re.findall(r'<progress class="cat-bar cat-\w+"', html)) >= 3


def test_profile_amounts_use_rupee(client):
    html = profile_html(client)
    assert "₹5,488.50" in html
    assert "₹1,850.00" in html
    assert "$" not in html


def test_profile_navbar_signed_in(client):
    html = profile_html(client)
    assert 'class="nav-user"' in html
    assert 'href="/profile"' in html
    assert "Sign out" in html
    assert "Get started" not in html


def test_profile_links_page_stylesheet(client):
    html = profile_html(client)
    assert "css/profile.css" in html


# --- Constraints ----------------------------------------------------- #

def test_profile_template_has_no_hex_or_inline_styles():
    template = read_project_file("templates", "profile.html")
    assert not HEX_COLOUR.search(template)
    assert "style=" not in template
    assert "<style" not in template


def test_profile_css_uses_variables_only():
    css = read_project_file("static", "css", "profile.css")
    assert not HEX_COLOUR.search(css)
