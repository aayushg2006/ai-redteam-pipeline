const { Builder } = require("selenium-webdriver");
const chrome = require("selenium-webdriver/chrome");
const { setTimeout: delay } = require("node:timers/promises");

// Bound each download attempt so three attempts fit the UI suite's setup timeout.
process.env.SE_TIMEOUT ||= "45";

async function createChromeDriver() {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const options = new chrome.Options().addArguments("--headless=new", "--window-size=1280,900");
      return await new Builder().forBrowser("chrome").setChromeOptions(options).build();
    } catch (error) {
      console.error(`Chrome setup attempt ${attempt}/3 failed: ${error.message}`);
      // Retry driver acquisition only; browser crashes and test failures must surface.
      if (attempt === 3 || !error.message.includes("Unable to obtain browser driver")) {
        throw error;
      }
      await delay(attempt * 2000);
    }
  }
}

module.exports = { createChromeDriver };

// Jenkins runs this after npm ci, before building/deploying the candidate.
if (require.main === module) {
  (async () => {
    const driver = await createChromeDriver();
    try {
      await driver.get("data:text/html,<title>Chrome readiness check</title>");
      if (await driver.getTitle() !== "Chrome readiness check") {
        throw new Error("Chrome readiness check failed");
      }
      console.log("Headless Chrome and ChromeDriver are ready.");
    } finally {
      await driver.quit();
    }
  })().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
