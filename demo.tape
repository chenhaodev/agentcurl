# VHS tape — records docs/demo.gif for the README.
#   brew install vhs && vhs demo.tape
# Needs DEEPSEEK_API_KEY in .env for the JSON-extraction beat.
# If vhs can't download its own Chrome (rod), point it at a local one, e.g. macOS:
#   ROD_BROWSER_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" vhs demo.tape
# Three short, representative beats: markdown · JSON extract · backend switch.

Output docs/demo.gif

Set Shell bash
Set FontSize 17
Set Width 1180
Set Height 640
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms

# --- setup (hidden): env + clean prompt so the GIF only shows the good part ---
Hide
Type 'cd /Users/chenhao/ClaudeCode/focus/agentcurl' Enter
Type 'export PYTHONPATH=src; export PS1="$ "' Enter
Type 'set -a; [ -f .env ] && . ./.env; set +a' Enter
Type 'export SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())")' Enter
Type 'clear' Enter
Show

# --- 1) static fetch -> clean markdown (fast) ---
Type '# agentcurl: 网页 → markdown / JSON，一个环境变量切换引擎' Sleep 1.2s Enter
Type 'python -m agentcurl https://example.com' Sleep 400ms Enter
Sleep 5s

# --- 2) page -> structured JSON via DeepSeek ---
Type '# 网页 → 结构化 JSON（DeepSeek 抽取）' Sleep 1s Enter
Type 'python -m agentcurl https://en.wikipedia.org/wiki/Web_scraping --extract "title and key topics" --json' Sleep 400ms Enter
Sleep 9s

# --- 3) switch engine with one env var (jina remote reader) ---
Type '# 换引擎只需改一个环境变量（jina = 零安装远程阅读器）' Sleep 1s Enter
Type 'CRAWL_BACKEND=jina python -m agentcurl https://example.com' Sleep 400ms Enter
Sleep 6s

Sleep 2s
