const CDP = require('chrome-remote-interface');

async function getStyles() {
    let client;
    try {
        const targets = await CDP.List();
        const target = targets.find(t => t.url.includes('localhost:3000/chat'));
        
        if (!target) {
            console.error('Could not find tab with localhost:3000/chat');
            process.exit(1);
        }

        client = await CDP({ target });
        const { Runtime } = client;

        const script = "(function() { " +
            "const btn = document.createElement('button'); " +
            "btn.className = 'bg-indigo-500 px-2 py-1'; " +
            "btn.innerText = 'temp'; " +
            "document.body.appendChild(btn); " +
            "const style = window.getComputedStyle(btn); " +
            "const result = { " +
            "    color: style.color, " +
            "    backgroundColor: style.backgroundColor " +
            "}; " +
            "document.body.removeChild(btn); " +
            "return result; " +
            "})()";

        const result = await Runtime.evaluate({
            expression: script,
            returnByValue: true
        });

        console.log(JSON.stringify(result.result.value, null, 2));
    } catch (err) {
        console.error(err);
    } finally {
        if (client) {
            await client.close();
        }
    }
}

getStyles();
