"""Remaining blind tests — run one at a time with spacing to avoid rate limits."""
import json, time, sys, urllib.request, functools

print = functools.partial(print, flush=True)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3336
BASE = f"http://localhost:{PORT}"

TESTS = [
    ("YouTube transcript (retest)",
     "Get me the transcript of this YouTube video: https://www.youtube.com/watch?v=7UaQB325EqU"),
    ("Multi-part repo comparison (retest)",
     "Compare these two GitHub repos: langchain-ai/langchain and run-llama/llama_index. "
     "Tell me: 1) Which has more stars? 2) What language is each primarily written in? 3) When was each created?"),
    ("Word frequency (retest)",
     "Go to https://www.gutenberg.org/files/11/11-0.txt (Alice in Wonderland) and tell me the 10 most frequently used words (excluding common stop words like the, a, an, is, etc)."),
    ("Weather data (retest)",
     "What is the current weather in Tokyo, London, and New York? Give me temperature and conditions for each city."),
]


def api(method, path, data=None):
    body = json.dumps(data).encode() if data is not None else b"{}"
    req = urllib.request.Request(f"{BASE}{path}", data=body,
                                headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


for i, (name, prompt) in enumerate(TESTS):
    print(f"\n{'='*60}")
    print(f"TEST {i+1}/{len(TESTS)}: {name}")
    print(f"{'='*60}")

    api("POST", "/api/chat/clear")
    time.sleep(2)

    resp = api("POST", "/api/chat/send", {"message": prompt})
    mid = resp["message_id"]
    print(f"  ID: {mid}")

    start = time.time()
    while time.time() - start < 180:
        time.sleep(10)
        st = api("GET", f"/api/chat/status/{mid}")
        s = st["status"]
        steps = len(st.get("steps", []))
        elapsed = st.get("elapsed", 0)
        print(f"  ... {s} ({steps} steps, {elapsed:.0f}s)")
        if s in ("complete", "error", "cancelled"):
            break

    result = st.get("result", "") or ""
    tools = [x["tool"] for x in st.get("steps", [])]
    print(f"\n  STATUS: {s} | STEPS: {steps} | ELAPSED: {elapsed:.1f}s")
    print(f"  TOOLS: {tools}")
    print(f"  RESULT: {result[:600]}")

    if i < len(TESTS) - 1:
        print(f"\n  Waiting 45s before next test (rate limit spacing)...")
        time.sleep(45)

print("\nDone.")
