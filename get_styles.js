const CDP = require('chrome-remote-interface');

async function getStyles() {
    let client;
    try {
        client = await CDP({ host: '127.0.0.1', port: 9222 });
        const { DOM, Runtime, Page, Target } = client;

        const targets = await Target.getTargets();
        const chatTarget = targets.targetInfos.find(t => t.url.includes('localhost:3000/chat'));

        if (!chatTarget) {
            console.error('Chat tab not found');
            return;
        }

        const { sessionId } = await Target.attachToTarget({ targetId: chatTarget.targetId, flatten: true });
        
        async function evaluate(expression) {
            const result = await client.send('Runtime.evaluate', { expression, returnByValue: true }, sessionId);
            return result.result.value;
        }

        const targetsToFind = [
            "Welcome! Let's connect your backend",
            "Auto-Start Hermes Gateway"
        ];

        const script = `
            (() => {
                const results = [];
                const targets = ${JSON.stringify(targetsToFind)};
                
                function findTextNode(root, text) {
                    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
                    let node;
                    while (node = walker.nextNode()) {
                        if (node.textContent.includes(text)) return node.parentElement;
                    }
                    return null;
                }

                targets.forEach(text => {
                    const el = findTextNode(document.body, text);
                    if (el) {
                        const style = window.getComputedStyle(el);
                        results.push({
                            text: text,
                            color: style.color,
                            backgroundColor: style.backgroundColor,
                            className: el.className
                        });
                    } else {
                        results.push({ text: text, error: 'Not found' });
                    }
                });
                return results;
            })()
        `;

        const results = await evaluate(script);
        console.log(JSON.stringify(results, null, 2));

    } catch (err) {
        console.error(err);
    } finally {
        if (client) {
            await client.close();
        }
    }
}

getStyles();
