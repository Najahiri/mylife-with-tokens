import asyncio, base64, json, subprocess, sys, time, urllib.request
import websockets
SP, QUERY = sys.argv[1], sys.argv[2]
OUT = f"{SP}/rec"
chrome = subprocess.Popen(["chromium", "--headless=new", "--hide-scrollbars", "--remote-debugging-port=9334",
                           f"--user-data-dir={OUT}/profile", "--window-size=1280,800", "about:blank"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
log = []
try:
    for _ in range(50):
        try:
            tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9334/json")); break
        except Exception: time.sleep(0.2)
    ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
    async def main():
        async with websockets.connect(ws_url, max_size=2**28) as ws:
            n = 0; pending = {}
            async def reader():
                async for raw in ws:
                    m = json.loads(raw)
                    if "id" in m and m["id"] in pending: pending.pop(m["id"]).set_result(m.get("result", m))
            rt = asyncio.create_task(reader())
            async def cmd(method, **params):
                nonlocal n; n += 1; f = asyncio.get_running_loop().create_future(); pending[n] = f
                await ws.send(json.dumps({"id": n, "method": method, "params": params})); return await f
            await cmd("Emulation.setDeviceMetricsOverride", width=1280, height=800, deviceScaleFactor=1.5, mobile=False)
            await cmd("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
            await cmd("Page.navigate", url="http://localhost:5173/")
            await asyncio.sleep(4)
            state = {"phase": "idle", "stop": False}; frames = []
            async def capture():
                i = 0
                while not state["stop"]:
                    t = time.time()
                    r = await cmd("Page.captureScreenshot", format="jpeg", quality=85)
                    open(f"{OUT}/frames/{i:05d}.jpg", "wb").write(base64.b64decode(r["data"]))
                    frames.append((i, t, state["phase"])); i += 1
                    await asyncio.sleep(max(0, (0.12 if state["phase"] in ("idle", "typing", "sent") else 0.45) - (time.time() - t)))
            cap = asyncio.create_task(capture())
            await asyncio.sleep(1.5)
            await cmd("Runtime.evaluate", expression="document.querySelector('textarea').focus()")
            state["phase"] = "typing"
            for ch in QUERY:
                await cmd("Input.insertText", text=ch); await asyncio.sleep(0.07)
            await asyncio.sleep(0.6)
            await cmd("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
            await cmd("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
            state["phase"] = "sent"; t_sent = time.time()
            while time.time() - t_sent < 600:
                await asyncio.sleep(1)
                if time.time() - t_sent > 2.5: state["phase"] = "working"
                r = await cmd("Runtime.evaluate", expression="document.body.innerText.includes('answered in')", returnByValue=True)
                if r.get("result", {}).get("value"): break
            state["phase"] = "done"; await asyncio.sleep(5)
            state["stop"] = True; await cap
            json.dump(frames, open(f"{OUT}/frames.json", "w"))
            print("frames", len(frames), "run", round(time.time() - t_sent), "s")
            rt.cancel()
    asyncio.run(main())
finally:
    chrome.terminate()
