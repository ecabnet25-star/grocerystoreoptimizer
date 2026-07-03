from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright


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
        page.goto("http://127.0.0.1:8080/account.html", wait_until="networkidle")
        page.fill("#createName", "Browser Smoke")
        page.fill("#createEmail", smoke_email)
        page.fill("#createPassword", "Password123")
        page.click("#createAccountBtn")
        page.wait_for_selector("#welcomeCard:not(.hidden)", timeout=10_000)
        page.goto("http://127.0.0.1:8080/index.html", wait_until="networkidle")
        page.fill("#postalCode", "H3A1A1")
        page.click("#generateBtn")
        page.wait_for_selector("#result:not(.hidden)", timeout=15_000)
        page.wait_for_selector("#planActionBoard", timeout=5_000)
        page.wait_for_selector("#savingsCelebration:not(.hidden)", timeout=5_000)
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

        action_count = page.locator(".action-tile").count()
        chef_message_count = page.locator(".assistant-message").count()
        route_stop_count = page.locator(".route-stop").count()
        leaflet_map_count = page.locator("#storeMap.leaflet-container").count()
        fallback_map_count = page.locator("#storeMap.fallback-map svg").count()
        directions_count = page.locator("#openDirectionsLink:not(.hidden)").count()
        route_marker_count = page.locator(".route-stop-marker").count()
        road_route_count = page.locator("#storeMap .road-route-line").count()
        approx_route_count = page.locator("#storeMap .approx-route-line").count()
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
    if leaflet_map_count < 1 and fallback_map_count < 1:
        print("Browser smoke failed: no map renderer was visible")
        return 1
    if directions_count < 1:
        print("Browser smoke failed: directions link was not available")
        return 1
    if road_route_count < 1 and approx_route_count < 1:
        print("Browser smoke failed: no route line was drawn")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
