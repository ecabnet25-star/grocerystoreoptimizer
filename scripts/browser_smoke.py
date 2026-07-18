from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright


def _audit_layout(page, page_name: str, errors: list[str]) -> None:
    metrics = page.evaluate(
        """
        () => ({
          horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
          brand: getComputedStyle(document.documentElement).getPropertyValue('--brand').trim(),
          legacyGreen: getComputedStyle(document.documentElement).getPropertyValue('--green-500').trim(),
          favicon: document.querySelector('link[rel="icon"]')?.getAttribute('href') || '',
        })
        """
    )
    if metrics["horizontalOverflow"]:
        errors.append(f"layout:{page_name}:horizontal overflow")
    if metrics["brand"].lower() != "#d20f25":
        errors.append(f"theme:{page_name}:unexpected brand color {metrics['brand']}")
    if metrics["legacyGreen"]:
        errors.append(f"theme:{page_name}:legacy green token remains")
    if "?v=" not in metrics["favicon"]:
        errors.append(f"cache:{page_name}:favicon URL is not versioned")


def main() -> int:
    errors: list[str] = []
    smoke_email = f"browser-smoke-{int(time.time() * 1000)}@example.com"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900})

        def collect_console(message) -> None:
            if message.type in {"error", "warning"}:
                errors.append(f"console:{message.type}:{message.text}")

        page.on("console", collect_console)
        page.on("pageerror", lambda exc: errors.append(f"pageerror:{exc}"))

        page.goto("http://127.0.0.1:8080/about.html", wait_until="networkidle")
        page.wait_for_selector("text=Make every grocery dollar work harder", timeout=5_000)
        _audit_layout(page, "about", errors)
        page.select_option("#languageSelect", "fr")
        page.wait_for_selector("text=Faites travailler chaque dollar", timeout=5_000)
        page.select_option("#languageSelect", "en")
        page.goto("http://127.0.0.1:8080/account.html", wait_until="networkidle")
        _audit_layout(page, "account", errors)
        page.fill("#createName", "Browser Smoke")
        page.fill("#createEmail", smoke_email)
        page.fill("#createPassword", "Password123")
        page.click("#createAccountBtn")
        page.wait_for_selector("#welcomeCard:not(.hidden)", timeout=10_000)
        page.goto("http://127.0.0.1:8080/index.html", wait_until="networkidle")
        _audit_layout(page, "plan", errors)
        page.fill("#locationQuery", "H3A1A1")
        page.fill("#mustHaveItems", "Chicken Breast, 900 g; Romaine Hearts")
        page.click("#generateBtn")
        page.wait_for_selector("#result:not(.hidden)", timeout=20_000)
        page.wait_for_selector("#planActionBoard", timeout=5_000)
        if page.locator("#savingsCelebration:not(.hidden)").count():
            savings_title = page.locator("#savingsCelebrationTitle").inner_text()
            if "congrat" in savings_title.lower():
                errors.append("truthfulness:generic congratulations returned")
        page.wait_for_function(
            "document.querySelector('#storeMap.leaflet-container') || document.querySelector('#storeMap svg')",
            timeout=10_000,
        )
        page.wait_for_function(
            "document.querySelector('#storeMap .road-route-line') || document.querySelector('#storeMap .approx-route-line')",
            timeout=12_000,
        )
        page.click('[data-chef-auto="Give me three fast dinners from this plan."]')
        page.wait_for_selector("#chefPanel:not(.hidden)", timeout=5_000)
        page.wait_for_function("document.querySelectorAll('.assistant-message').length >= 2", timeout=25_000)
        page.click("#dealsViewTab")
        page.wait_for_selector(".deal-card", timeout=10_000)
        page.click("#planViewTab")

        action_count = page.locator(".action-tile").count()
        chef_message_count = page.locator(".assistant-message").count()
        route_stop_count = page.locator(".route-stop").count()
        leaflet_map_count = page.locator("#storeMap.leaflet-container").count()
        fallback_map_count = page.locator("#storeMap.fallback-map svg").count()
        directions_count = page.locator("#openDirectionsLink:not(.hidden)").count()
        route_marker_count = page.locator(".route-stop-marker").count()
        road_route_count = page.locator("#storeMap .road-route-line").count()
        approx_route_count = page.locator("#storeMap .approx-route-line").count()
        nearby_store_count = page.locator(".nearby-store-row").count()

        mobile_context = browser.new_context(viewport={"width": 390, "height": 844})
        mobile_page = mobile_context.new_page()
        for page_name in ("index", "about", "account", "saved"):
            mobile_page.goto(f"http://127.0.0.1:8080/{page_name}.html", wait_until="networkidle")
            _audit_layout(mobile_page, f"{page_name}-mobile", errors)
        mobile_page.goto("http://127.0.0.1:8080/index.html", wait_until="networkidle")
        planner_columns = mobile_page.locator(".quick-plan-grid").evaluate(
            "element => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length"
        )
        if planner_columns != 1:
            errors.append(f"layout:index-mobile:expected one planner column, found {planner_columns}")
        mobile_page.fill("#locationQuery", "H3A1A1")
        mobile_page.fill("#mustHaveItems", "Chicken Breast, 900 g; Romaine Hearts")
        mobile_page.click("#generateBtn")
        mobile_page.wait_for_selector("#result:not(.hidden)", timeout=20_000)
        _audit_layout(mobile_page, "plan-result-mobile", errors)
        item_card_widths = mobile_page.locator("#resultItemsBody tr").evaluate_all(
            "rows => rows.map(row => row.getBoundingClientRect().width)"
        )
        if not item_card_widths or max(item_card_widths) > 358:
            errors.append(f"layout:plan-result-mobile:invalid item card widths {item_card_widths[:3]}")
        mobile_page.goto("http://127.0.0.1:8080/saved.html", wait_until="networkidle")
        footer_gap = mobile_page.evaluate(
            "Math.max(0, window.innerHeight - document.querySelector('.site-footer').getBoundingClientRect().bottom)"
        )
        if footer_gap > 1:
            errors.append(f"layout:saved-mobile:footer leaves {footer_gap}px below it")
        mobile_context.close()
        browser.close()

    if errors:
        print("Browser smoke failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Browser smoke passed")
    print(f"- action tiles: {action_count}")
    print(f"- chef messages: {chef_message_count}")
    print(f"- route stops: {route_stop_count}")
    print(f"- leaflet maps: {leaflet_map_count}")
    print(f"- fallback maps: {fallback_map_count}")
    print(f"- directions links: {directions_count}")
    print(f"- route markers: {route_marker_count}")
    print(f"- road routes: {road_route_count}")
    print(f"- approximate routes: {approx_route_count}")
    print(f"- nearby stores listed: {nearby_store_count}")
    if leaflet_map_count < 1 and fallback_map_count < 1:
        print("Browser smoke failed: no map renderer was visible")
        return 1
    if directions_count < 1:
        print("Browser smoke failed: directions link was not available")
        return 1
    if road_route_count < 1 and approx_route_count < 1:
        print("Browser smoke failed: no route line was drawn")
        return 1
    if nearby_store_count < 2:
        print("Browser smoke failed: nearby store directory was not populated")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
