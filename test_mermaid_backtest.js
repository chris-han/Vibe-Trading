const CDP = require('chrome-remote-interface');
const axios = require('axios');

async function run() {
    let client;
    try {
        const targets = await CDP.List({host: '127.0.0.1', port: 9222});
        if (!targets || targets.length === 0) {
            console.error("No targets found");
            return;
        }
        
        client = await CDP({target: targets[0].webSocketDebuggerUrl});
        const {Page, Runtime, DOM} = client;

        await Promise.all([Page.enable(), Runtime.enable(), DOM.enable()]);

        console.log("Navigating to http://127.0.0.1:8899");
        await Page.navigate({url: 'http://127.0.0.1:8899'});
        await Page.loadEventFired();

        let textareaFound = false;
        for (let i = 0; i < 20; i++) {
            const checkTextarea = await Runtime.evaluate({expression: 'document.querySelector("textarea") !== null'});
            if (checkTextarea.result.value) {
                textareaFound = true;
                break;
            }
            await new Promise(r => setTimeout(r, 1000));
        }

        if (!textareaFound) {
             console.error("Textarea not found");
             return;
        }

        const prompt = 'Backtest BTC-USDT 5-minute MACD strategy, fast=12 slow=26 signal=9, last 30 days.';
        console.log("Entering prompt: " + prompt);
        
        await Runtime.evaluate({
            expression: `
                (function() {
                    const ta = document.querySelector("textarea");
                    ta.value = "${prompt}";
                    ta.dispatchEvent(new Event('input', { bubbles: true }));
                    const btns = Array.from(document.querySelectorAll('button'));
                    const submitBtn = btns.find(b => b.type === 'submit' || b.innerText.toLowerCase().includes('send') || b.querySelector('svg'));
                    if (submitBtn) {
                        submitBtn.click();
                    } else {
                        const form = ta.closest('form');
                        if (form) form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                    }
                })()
            `
        });

        let sessionId = null;
        console.log("Waiting for session ID in URL...");
        for (let i = 0; i < 60; i++) {
            const urlResult = await Runtime.evaluate({expression: 'window.location.href'});
            const url = urlResult.result.value;
            const match = url.match(/\/session\/([^/?#]+)/);
            if (match) {
                sessionId = match[1];
                console.log("Found session ID: " + sessionId);
                break;
            }
            await new Promise(r => setTimeout(r, 2000));
        }

        if (!sessionId) {
            console.error("Session ID never appeared in URL");
            return;
        }

        console.log("Polling for activity...");
        const startTime = Date.now();
        const timeoutMs = 5 * 60 * 1000;
        let finalStatus = {};

        while (Date.now() - startTime < timeoutMs) {
            const scan = await Runtime.evaluate({
                expression: `(function() {
                    const text = document.body.innerText;
                    const syntaxError = text.includes('Syntax error in text');
                    const errorBlocks = document.querySelectorAll('.error-text').length;
                    const mermaidSvgs = document.querySelectorAll('.mermaid-block svg').length;
                    const preBlocks = Array.from(document.querySelectorAll('pre')).map(p => p.innerText.substring(0, 100));
                    const mermaidPre = preBlocks.some(t => t.toLowerCase().includes('graph ') || t.toLowerCase().includes('sequencediagram') || t.toLowerCase().includes('gantt') || t.includes('\`\`\`mermaid'));
                    
                    return {
                        syntaxError,
                        errorBlocks,
                        mermaidSvgs,
                        mermaidPre
                    };
                })()`,
                returnByValue: true
            });

            const findings = scan.result.value;
            
            let latestAssistantContent = "";
            let backendHasMermaid = false;
            try {
                const response = await axios.get(`http://127.0.0.1:8899/api/sessions/${sessionId}/messages?limit=20`);
                const messages = response.data;
                const assistantMsgs = messages.filter(m => m.role === 'assistant');
                if (assistantMsgs.length > 0) {
                    const last = assistantMsgs[assistantMsgs.length - 1];
                    latestAssistantContent = last.content;
                    backendHasMermaid = last.content.includes('```mermaid');
                }
            } catch (e) {
            }

            finalStatus = {
                sessionId,
                frontend: findings,
                backendHasMermaid,
                latestAssistantContent: latestAssistantContent.substring(0, 150).replace(/\n/g, ' ')
            };

            console.log("Status: " + JSON.stringify(finalStatus));

            if (findings.mermaidSvgs > 0 || findings.syntaxError) {
                 break;
            }

            await new Promise(r => setTimeout(r, 10000));
        }

        console.log("FINAL_RESULT: " + JSON.stringify(finalStatus));

    } catch (err) {
        console.error("Error: " + err.stack);
    } finally {
        if (client) await client.close();
    }
}

run();
