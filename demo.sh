#!/usr/bin/env bash
# 一键演示 agentcurl 的几个真实场景（README「看它怎么爬」的可复现版）。
#
#   ./demo.sh
#
# 想录成 GIF/视频分享，用 vhs 或 asciinema 包一层即可：
#   asciinema rec demo.cast -c ./demo.sh        # 录成 asciinema cast
#   vhs demo.tape                               # 或写个 .tape 脚本录成 gif/mp4
#
# 需要：pip install -e . ；抽取场景需 .env 里配好 DEEPSEEK_API_KEY。
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && export $(grep -v '^#' .env | xargs) 2>/dev/null || true
export SSL_CERT_FILE="${SSL_CERT_FILE:-$(python3 -c 'import certifi;print(certifi.where())' 2>/dev/null || echo)}"

say() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }

say "① 静态站点 → 干净 markdown（零额外依赖）"
python3 -m agentcurl https://example.com

say "② 网页 → 结构化 JSON（DeepSeek 抽取；没密钥则降级原始 markdown）"
python3 -m agentcurl https://en.wikipedia.org/wiki/Web_scraping \
  --schema '{"title":"str","first_sentence":"str","key_topics":"list"}' --json

say "③ JS 渲染页（YouTube 视频）→ jina 远程阅读器 → 抽取视频信息"
CRAWL_BACKEND=jina python3 -m agentcurl "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --schema '{"video_title":"str","channel":"str","duration":"str"}' --json

say "④ 回退链：static 先试，空了自动落 jina（中文 GBK 站点正确解码）"
CRAWL_BACKEND=static+jina ROUTER_MODE=fallback python3 -m agentcurl https://www.xywy.com/ \
  | head -8

say "演示结束。切换引擎只需改 CRAWL_BACKEND；爬整站加 --crawl。"
