---
name: case-review
description: Use at the start of every client case to read the files and decide on trades.
---

1. Read client.json, holdings.json and market.json.
2. Run `python tools/portfolio.py allocation holdings.json` to see current weights by asset class.
3. Compare the weights with `targets` in client.json and decide whether to trade.
4. Write a draft to recommendation.json using the recommendation-format skill.
5. Run `python tools/portfolio.py apply holdings.json recommendation.json` to see the
   holdings your trades would produce, then fix and rewrite the file if needed.
