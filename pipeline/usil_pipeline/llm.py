"""Thin wrapper around the Anthropic Messages API with structured outputs, prompt caching,
on-disk result caching, and token accounting."""
import hashlib, json, os, threading
import anthropic

# USD per million tokens (input, output); update if pricing changes:
# https://platform.claude.com/docs/en/about-claude/pricing
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}


class LLM:
    def __init__(self, cache_dir, client=None):
        self.client = client or anthropic.Anthropic(max_retries=6)
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.lock = threading.Lock()
        self.usage = {}

    def _key(self, *parts):
        h = hashlib.sha256()
        for p in parts:
            h.update(p.encode() if isinstance(p, str) else json.dumps(p, sort_keys=True).encode())
        return h.hexdigest()[:24]

    def _account(self, model, u):
        with self.lock:
            d = self.usage.setdefault(model, {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "calls": 0})
            d["input"] += getattr(u, "input_tokens", 0) or 0
            d["output"] += getattr(u, "output_tokens", 0) or 0
            d["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
            d["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
            d["calls"] += 1

    def cost_estimate(self):
        total = 0.0
        for m, d in self.usage.items():
            pin, pout = PRICES.get(m, (0, 0))
            total += (d["input"] + 1.25 * d["cache_write"] + 0.1 * d["cache_read"]) * pin / 1e6 + d["output"] * pout / 1e6
        return round(total, 2)

    def structured(self, *, stage, paper_key, model, system, user, schema, max_tokens=16000, force=False):
        """Call Claude with a Pydantic schema; cache the parsed result on disk."""
        ck = self._key(stage, model, system, user, schema.__name__, json.dumps(schema.model_json_schema(), sort_keys=True))
        path = os.path.join(self.cache_dir, f"{stage}__{paper_key}__{ck}.json")
        if os.path.exists(path) and not force:
            return json.load(open(path)), True
        resp = self.client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            # the long, shared research context is cached across papers
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        self._account(model, resp.usage)
        if resp.stop_reason == "max_tokens":
            raise RuntimeError(f"{stage}/{paper_key}: output truncated (raise max_tokens)")
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise RuntimeError(f"{stage}/{paper_key}: no parsed output (stop_reason={resp.stop_reason})")
        out = resp.parsed_output.model_dump()
        json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
        return out, False
