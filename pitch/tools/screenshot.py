import asyncio, base64, json, subprocess, sys, time, urllib.request
import websockets
SP = sys.argv[1]; OUT = sys.argv[2]
chrome = subprocess.Popen(["chromium", "--headless=new", "--hide-scrollbars", "--remote-debugging-port=9333",
                           f"--user-data-dir={SP}/shot/profile5", "--window-size=1600,1000", "about:blank"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json")); break
        except Exception: time.sleep(0.2)
    ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
    async def main():
        async with websockets.connect(ws_url, max_size=2**28) as ws:
            n = 0
            async def cmd(method, **params):
                nonlocal n; n += 1; my = n
                await ws.send(json.dumps({"id": my, "method": method, "params": params}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == my: return m.get("result", m)
            await cmd("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=2, mobile=False)
            await cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
            await cmd("Page.navigate", url="http://localhost:5173/_shot.html")
            await asyncio.sleep(25)
            r = await cmd("Page.captureScreenshot", format="png")
            open(OUT, "wb").write(base64.b64decode(r["data"]))
    asyncio.run(main())
finally:
    chrome.terminate()
