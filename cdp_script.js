const CDP = require('chrome-remote-interface');

async function getElementInfo() {
    let client;
    try {
        const targets = await CDP.List();
        const target = targets.find(t => t.url.includes('localhost:3000/chat'));
        if (!target) {
            console.error('Target tab not found');
            return;
        }

        client = await CDP({ target });
        const { Runtime } = client;
        await Runtime.enable();

        const searchTexts = ["Welcome! Let's connect your backend", "Auto-Start Hermes Gateway"];

        for (const text of searchTexts) {
            console.log("\nSearching for: " + text);
            
            const expression = `
                (() => {
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                    let node;
                    const results = [];
                    while (node = walker.nextNode()) {
                        if (node.textContent.includes("${text}")) {
                            const el = node.parentElement;
                            const style = window.getComputedStyle(el);
                            results.push({
                                tagName: el.tagName,
                                className: el.className,
                                inlineStyle: el.getAttribute('style') || '',
                                computed: {
                                    color: style.color,
                                    backgroundColor: style.backgroundColor,
                                    border: style.border
                                },
                                outerHTML: el.outerHTML.substring(0, 300)
                            });
                        }
                    }
                    return JSON.stringify(results);
                })()
            `;

            const { result } = await Runtime.evaluate({ expression });
            const elements = JSON.parse(result.value);

            if (elements.length === 0) {
                console.log('No elements found.');
            } else {
                elements.forEach((el, index) => {
                    console.log("Match " + (index + 1) + ":");
                    console.log(JSON.stringify(el, null, 2));
                });
            }
        }

    } catch (err) {
        console.error(err);
    } finally {
        if (client) {
            await client.close();
        }
    }
}

getElementInfo();
