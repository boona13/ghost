"""
Blind autonomy tests for Ghost — each test in its own isolated chat session.
No hints about implementation, no specific library names, no API URLs.
"""
import json, time, sys, urllib.request, functools

print = functools.partial(print, flush=True)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3336

BASE = f"http://localhost:{PORT}"

TESTS = [
    ("YouTube transcript",
     "Get me the transcript of this YouTube video: https://www.youtube.com/watch?v=7UaQB325EqU"),
    ("Crypto prices",
     "What is the current price of Bitcoin and Ethereum? How many ETH could I buy with 1 BTC right now?"),
    ("GitHub stars",
     "Which GitHub repo has more stars: langchain or llama_index? Give me the exact numbers."),
    ("Bar chart image",
     "I need the top 10 most popular programming languages in 2025. Put the data in a bar chart and save it as an image I can download."),
    ("QR code gen + verify",
     'Generate a QR code that says "Ghost is unstoppable" and save it somewhere I can download it. Then verify it actually contains the right text.'),
    ("PDF extract",
     "Download this PDF https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf and tell me what text is inside it."),
    ("HN top stories",
     "What are the current top 5 stories on Hacker News right now? Give me titles and point counts."),
    ("Multi-part repo comparison",
     "Compare these two GitHub repos: langchain-ai/langchain and run-llama/llama_index. "
     "Tell me: 1) Which has more stars? 2) What language is each primarily written in? 3) When was each created?"),
    ("Word frequency",
     "Go to https://www.gutenberg.org/files/11/11-0.txt (Alice in Wonderland) and tell me the 10 most frequently used words (excluding common stop words like the, a, an, is, etc)."),
    ("Weather data",
     "What is the current weather in Tokyo, London, and New York? Give me temperature and conditions for each city."),
]


def post_json(path, data=None):
    body = json.dumps(data).encode() if data else b"{}"
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_json(path):
    with urllib.request.urlopen(f"{BASE}{path}") as resp:
        return json.loads(resp.read())


def run_test(idx, name, prompt, timeout=120):
    print(f"\n{'='*70}")
    print(f"TEST {idx+1}/10: {name}")
    print(f"{'='*70}")

    # Clear session
    post_json("/api/chat/clear")
    time.sleep(1)

    # Send message
    resp = post_json("/api/chat/send", {"message": prompt})
    mid = resp["message_id"]
    print(f"  Message ID: {mid}")

    # Poll for completion
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(5)
        status = get_json(f"/api/chat/status/{mid}")
        s = status["status"]
        elapsed = status.get("elapsed", 0)
        steps = len(status.get("steps", []))
        if s in ("complete", "error", "cancelled"):
            break
        print(f"  ... {s} ({steps} steps, {elapsed:.0f}s)")

    result = status.get("result", "") or ""
    error = status.get("error", "")
    tools = [st["tool"] for st in status.get("steps", [])]
    elapsed = status.get("elapsed", 0)

    # Evaluate
    has_upsell = any(x in result.lower() for x in
                     ["if you want", "let me know", "i can also", "would you like"])
    gave_up = any(x in result.lower() for x in
                  ["i can't", "i cannot", "i'm unable", "please share", "please provide",
                   "here is how you can", "paste it here", "couldn't extract",
                   "not possible", "not available in", "blocked here",
                   "unable to", "i couldn't"])
    has_substance = len(result) > 50

    if s == "error":
        verdict = "FAIL (error)"
    elif gave_up:
        verdict = "FAIL (gave up)"
    elif not has_substance:
        verdict = "FAIL (empty/short)"
    elif has_upsell:
        verdict = "WARN (upsell)"
    else:
        verdict = "PASS"

    print(f"\n  VERDICT: {verdict}")
    print(f"  Status: {s} | Steps: {steps} | Elapsed: {elapsed:.1f}s")
    print(f"  Tools: {tools}")
    if has_upsell:
        print(f"  ⚠ Contains upsell language")
    if gave_up:
        print(f"  ✗ Ghost gave up / asked user to do it")
    print(f"  Result preview: {result[:300]}")

    return {
        "test": name,
        "verdict": verdict,
        "status": s,
        "steps": steps,
        "elapsed": elapsed,
        "tools": tools,
        "has_upsell": has_upsell,
        "gave_up": gave_up,
    }


if __name__ == "__main__":
    print(f"Running 10 blind autonomy tests against Ghost on port {PORT}")
    print(f"Each test gets its own clean session. No hints. No cheats.\n")

    results = []
    for i, (name, prompt) in enumerate(TESTS):
        r = run_test(i, name, prompt)
        results.append(r)

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    warned = sum(1 for r in results if r["verdict"].startswith("WARN"))
    failed = sum(1 for r in results if r["verdict"].startswith("FAIL"))
    for r in results:
        icon = "✓" if r["verdict"] == "PASS" else "⚠" if r["verdict"].startswith("WARN") else "✗"
        print(f"  {icon} {r['test']:35s} {r['verdict']:20s} ({r['steps']} steps, {r['elapsed']:.1f}s)")
    print(f"\n  PASSED: {passed}/10 | WARNINGS: {warned}/10 | FAILED: {failed}/10")
