// CDP debug script - test mermaid rendering in browser
const WebSocket = require('./node_modules/ws');
const ws = new WebSocket('ws://localhost:9222/devtools/page/6997809111CA7D838EDDEBD6BDBC81F5');

function sendEval(id, code) {
  ws.send(JSON.stringify({
    id,
    method: 'Runtime.evaluate',
    params: { expression: code, awaitPromise: true, returnByValue: true }
  }));
}

ws.on('open', () => {
  // Step 1: find mermaid module URL
  sendEval(1, `
    (function() {
      var entries = performance.getEntriesByType("resource");
      var mermaidUrls = [];
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].name.indexOf("mermaid") !== -1) {
          mermaidUrls.push(entries[i].name);
        }
      }
      return JSON.stringify(mermaidUrls);
    })()
  `);
});

ws.on('message', (data) => {
  const msg = JSON.parse(data);

  if (msg.id === 1) {
    console.log('Mermaid URLs:', msg.result?.result?.value || JSON.stringify(msg.result));

    // Step 2: test mermaid render using dynamic import
    sendEval(2, `
      (async function() {
        try {
          var mod = await import("http://localhost:5900/node_modules/.vite/deps/mermaid.js?v=72d0b4a9");
          var m = mod.default;
          m.initialize({ startOnLoad: false, securityLevel: "loose", theme: "neutral" });
          var chart = "flowchart TD" + String.fromCharCode(10) + "    A[Start] --> B[End]";
          var result = await m.render("dbg-test-1", chart);
          var svg = result.svg;
          var checks = {
            hasSyntaxError: svg.indexOf("Syntax error") !== -1,
            hasErrorText: svg.indexOf("error-text") !== -1,
            hasErrorIcon: svg.indexOf("error-icon") !== -1,
            hasBomb: svg.indexOf("#bomb") !== -1,
            svgLen: svg.length,
            // Find where error-text appears
            errorTextContext: (function() {
              var idx = svg.indexOf("error-text");
              if (idx === -1) return "not found";
              return svg.substring(Math.max(0, idx - 40), idx + 60);
            })(),
            errorIconContext: (function() {
              var idx = svg.indexOf("error-icon");
              if (idx === -1) return "not found";
              return svg.substring(Math.max(0, idx - 40), idx + 60);
            })()
          };
          var el = document.getElementById("dbg-test-1");
          if (el) el.remove();
          var del = document.getElementById("ddbg-test-1");
          if (del) del.remove();
          return JSON.stringify(checks, null, 2);
        } catch(e) {
          return "ERROR: " + e.message + " | " + e.stack;
        }
      })()
    `);
  }

  if (msg.id === 2) {
    console.log('Render test:', msg.result?.result?.value || JSON.stringify(msg.result));
    ws.close();
    process.exit(0);
  }
});

setTimeout(() => { console.log('timeout'); ws.close(); process.exit(1); }, 10000);
