from __future__ import annotations

import sys
import time

from playwright.sync_api import Page, TimeoutError, sync_playwright

WEB_URL = "http://127.0.0.1:8080"


def _wait_for_route(page: Page) -> None:
    page.wait_for_function(
        "document.querySelector('#storeMap.leaflet-container') || document.querySelector('#storeMap svg')",
        timeout=12_000,
    )
    page.wait_for_function(
        "document.querySelector('#storeMap .road-route-line') || document.querySelector('#storeMap .approx-route-line')",
        timeout=18_000,
    )


def _generate_plan(page: Page, *, budget: str = "46", max_items: str = "8") -> None:
    page.goto(f"{WEB_URL}/index.html", wait_until="domcontentloaded")
    page.wait_for_selector("#budget", timeout=10_000)
    page.fill("#budget", budget)
    # Older UI used a details panel (#prefsBody); newer UI shows fields directly.
    if page.locator("#prefsBody").count() > 0:
        page.locator("#prefsBody").evaluate("element => { element.open = true; }")
    page.fill("#maxItems", max_items)
    page.fill("#postalCode", "H3A1A1")
    page.fill("#requiredCategories", "produce,protein")
    page.fill("#healthGoals", "high protein, savings")
    page.click("#generateBtn")
    page.wait_for_selector("#result:not(.hidden)", timeout=20_000)
    page.wait_for_selector("#savingsCelebration:not(.hidden)", timeout=5_000)
    page.wait_for_selector("#chefWidget:not(.hidden)", timeout=8_000)
    _wait_for_route(page)


def main() -> int:
    errors: list[str] = []
    stamp = int(time.time() * 1000)
    email = f"pw-integration-{stamp}@example.com"
    password = "Password123"
    label = f"Integration Plan {stamp}"
    saved_count = 0
    current_step = "browser startup"
    expected_unauthorized = False

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 920})
        page = context.new_page()

        def collect_console(msg) -> None:
            if msg.type == "error" and not (expected_unauthorized and "401" in msg.text):
                errors.append(f"console:error:{msg.text}")

        page.on("console", collect_console)
        page.on("pageerror", lambda exc: errors.append(f"pageerror:{exc}"))

        try:
            current_step = "About page"
            page.goto(f"{WEB_URL}/about.html", wait_until="domcontentloaded")
            page.wait_for_selector("text=Make every grocery dollar work harder", timeout=5_000)
            assert page.locator('nav a[href="about.html"]').count() == 1

            current_step = "account creation"
            page.goto(f"{WEB_URL}/account.html", wait_until="domcontentloaded")
            page.fill("#createName", "Playwright User")
            page.fill("#createEmail", email)
            page.fill("#createPassword", password)
            page.click("#createAccountBtn")
            page.wait_for_selector("#welcomeCard:not(.hidden)", timeout=10_000)
            current_step = "logout"
            page.click("#logoutBtn")
            page.wait_for_function("document.querySelector('#welcomeCard')?.classList.contains('hidden')", timeout=5_000)
            current_step = "invalid login"
            page.fill("#loginEmail", email)
            page.fill("#loginPassword", "Wrongpass123")
            expected_unauthorized = True
            page.click("#loginBtn")
            page.wait_for_selector(".status.error", timeout=5_000)
            expected_unauthorized = False
            current_step = "valid login"
            page.fill("#loginPassword", password)
            page.click("#loginBtn")
            page.wait_for_selector("#welcomeCard:not(.hidden)", timeout=10_000)

            current_step = "initial plan generation"
            _generate_plan(page)
            current_step = "plan save"
            page.click("#savePlanBtn")
            page.wait_for_selector("#saveModal.active", timeout=5_000)
            page.fill("#savePlanName", label)
            page.click("#saveModalConfirm")
            page.wait_for_function(
                "document.querySelector('#statusBanner')?.textContent.includes('Plan saved')",
                timeout=10_000,
            )

            current_step = "saved-plan library"
            page.goto(f"{WEB_URL}/saved.html", wait_until="domcontentloaded")
            page.wait_for_selector(".saved-plan", timeout=10_000)
            page.fill("#planSearch", label)
            page.wait_for_function("document.querySelectorAll('.saved-plan:not(.hidden-by-search)').length >= 1")
            saved_count = page.locator(".saved-plan:not(.hidden-by-search)").count()
            first_plan = page.locator(".saved-plan:not(.hidden-by-search)").first
            current_step = "saved-plan detail"
            first_plan.locator('[data-action="open"]').click()
            page.wait_for_selector("#planDetail:not(.hidden)", timeout=8_000)
            page.click("#backToListBtn")
            page.wait_for_selector("#plansList:not(.hidden)", timeout=5_000)
            current_step = "saved-plan reuse"
            page.locator(".saved-plan:not(.hidden-by-search)").first.locator('[data-action="reuse"]').click()

            current_step = "reused plan generation"
            page.wait_for_url("**/index.html", timeout=8_000)
            page.wait_for_function("document.querySelector('#postalCode')?.value === 'H3A1A1'", timeout=8_000)
            page.click("#generateBtn")
            page.wait_for_selector("#result:not(.hidden)", timeout=20_000)
            _wait_for_route(page)

            current_step = "Chef response"
            page.click("#chefLauncher")
            page.fill("#assistantInput", "Give me two fast meals from this exact plan.")
            page.click("#assistantSendBtn")
            page.wait_for_function("document.querySelectorAll('.assistant-message').length >= 2", timeout=25_000)

            route_stop_count = page.locator(".route-stop").count()
            route_line_count = page.locator("#storeMap .road-route-line, #storeMap .approx-route-line").count()
            chef_message_count = page.locator(".assistant-message").count()
            nearby_store_count = page.locator(".nearby-store-row").count()
        except TimeoutError as exc:
            errors.append(f"timeout:{current_step}:{exc}")
            route_stop_count = route_line_count = chef_message_count = nearby_store_count = saved_count = 0
        except AssertionError as exc:
            errors.append(f"assertion:{exc}")
            route_stop_count = route_line_count = chef_message_count = nearby_store_count = saved_count = 0
        finally:
            browser.close()

    if errors:
        print("Playwright integration failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Playwright integration passed")
    print(f"- saved plans visible: {saved_count}")
    print(f"- route stops: {route_stop_count}")
    print(f"- route lines: {route_line_count}")
    print(f"- chef messages: {chef_message_count}")
    print(f"- nearby stores listed: {nearby_store_count}")
    if route_stop_count < 1 or route_line_count < 1 or chef_message_count < 2 or nearby_store_count < 2:
        print("Playwright integration failed: expected route, nearby-store, or Chef evidence was missing")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
