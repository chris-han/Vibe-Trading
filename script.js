const http = require('http');
const WebSocket = require('ws');

async function getBrowserTabs() {
  return new Promise((resolve, reject) => {
    http.get('http://127.0.0.1:9222/json/list', (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => resolve(JSON.parse(data)));
    }).on('error', reject);
  });
}

async function run() {
  try {
    const tabs = await getBrowserTabs();
    const tab = tabs.find(t => t.url && t.url.includes('localhost:3000/chat'));
    if (!tab) {
      console.error('Target tab not found');
      process.exit(1);
    }

    const ws = new WebSocket(tab.webSocketDebuggerUrl);
    let id = 1;

    const send = (method, params = {}) => {
      return new Promise((resolve) => {
        const msgId = id++;
        const onMessage = (data) => {
          const res = JSON.parse(data);
          if (res.id === msgId) {
            ws.removeListener('message', onMessage);
            resolve(res.result);
          }
        };
        ws.on('message', onMessage);
        ws.send(JSON.stringify({ id: msgId, method, params }));
      });
    };

    ws.on('open', async () => {
      await send('Runtime.enable');
      
      const expression = `
        (() => {
          function getStyles(text) {
            const elements = Array.from(document.querySelectorAll('*'));
            const el = elements.find(e => e.textContent.includes(text) && Array.from(e.childNodes).some(node => node.nodeType === Node.TEXT_NODE && node.textContent.includes(text)));
            if (!el) return null;
            const style = window.getComputedStyle(el);
            return {
              text: el.textContent.trim().substring(0, 100),
              color: style.color,
              backgroundColor: style.backgroundColor,
              border: style.border,
              font: style.font || style.fontFamily + ' ' + style.fontSize
            };
          }
          return {
            heading: getStyles("Welcome! Let's connect your backend"),
            button: getStyles("Auto-Start Hermes Gateway")
          };
        })()
      `;

      const result = await send('Runtime.evaluate', { expression, returnByValue: true });
      console.log(JSON.stringify(result.result.value, null, 2));
      ws.close();
    });

  } catch (err) {
    console.error(err);
  }
}

run();
