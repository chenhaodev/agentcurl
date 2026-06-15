"""Watch-the-user-log-in-once capture.

Opens a real, visible Chromium window at `url`, hands control to the user to log
in (solve a captcha, click through SSO, whatever), and when they press Enter in
the terminal it snapshots the authenticated session — Playwright `storage_state`
(cookies + localStorage) plus a plain cookie dict — into the domain's recipe.

After that, the browser backend replays the storage_state and static/jina send
the cookies, so the same domain crawls *as the logged-in user* next time. This
is the human-in-the-loop half of the meta layer; everything else is automatic.

Live-only by nature (needs a display + Playwright). Requires:
    pip install "agentcurl[browser]" && playwright install chromium
"""

from __future__ import annotations

import os

from .config import Config
from .fetch_utils import domain_of
from .recipes import Recipe, RecipeStore


def record_login(
    url: str,
    config: Config,
    store: RecipeStore,
    *,
    prompt=input,
) -> Recipe:
    """Drive a manual login and persist the captured session into the recipe.

    `prompt` is the blocking "press Enter when done" call (injectable for tests).
    Returns the saved Recipe. Raises ImportError if Playwright isn't installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ImportError(
            "login capture needs Playwright. Run: "
            'pip install "agentcurl[browser]" && playwright install chromium'
        ) from e

    domain = domain_of(url)
    os.makedirs(config.recipes_dir, exist_ok=True)
    state_path = os.path.join(config.recipes_dir, f"{domain}.state.json")

    with sync_playwright() as p:
        # headed on purpose — the user needs to see and drive the page
        browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context(user_agent=config.user_agent)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=config.browser_timeout * 1000)
            prompt(
                f"\nA browser opened at {url}.\n"
                "Log in / navigate to the authenticated state you want to capture, "
                "then press Enter here to save the session... "
            )
            context.storage_state(path=state_path)  # cookies + localStorage to disk
            cookies = {
                c["name"]: c["value"]
                for c in context.cookies()
                if c.get("name")
            }
        finally:
            browser.close()

    recipe = store.get(domain) or Recipe(domain=domain)
    recipe.storage_state = state_path
    recipe.cookies = cookies
    if recipe.best_backend is None:
        recipe.best_backend = "browser"  # logged-in sessions replay best in a browser
    recipe.notes = (recipe.notes + " " if recipe.notes else "") + "session captured via login"
    store.save(recipe)
    return recipe
