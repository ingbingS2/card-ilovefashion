from pathlib import Path

from playwright.sync_api import sync_playwright


draft = Path(__file__).resolve().parent

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        headless=True,
    )
    context = browser.new_context(
        viewport={"width": 1200, "height": 900}, device_scale_factor=2
    )
    page = context.new_page()
    page.goto((draft / "index.html").as_uri())
    page.wait_for_load_state("networkidle")
    for index in range(7):
        page.evaluate(
            "(index) => { const card = document.querySelector(`#card${index}`); "
            "card.style.cssText += ';position:fixed;left:0;top:0;transform:none;z-index:9999'; }",
            index,
        )
        page.screenshot(
            path=str(draft / f"{index + 1}.jpg"),
            type="jpeg",
            quality=95,
            clip={"x": 0, "y": 0, "width": 540, "height": 675},
        )
        page.evaluate(
            "(index) => { const card = document.querySelector(`#card${index}`); "
            "card.style.position = 'relative'; card.style.zIndex = ''; }",
            index,
        )

    browser.close()
