from __future__ import annotations

from typing import Any, Callable, Iterable, List

from ..types import Action, Observation


def _format_allowed(actions: Iterable[Action]) -> str:
    return ", ".join(a.name for a in actions)


class LLMAgent:
    """Agent that asks an LLM to choose an action.

    By default, uses an injected `ask_fn(prompt: str) -> str` callable. A convenience
    OpenAI-backed ask function is available via `LLMAgent.openai_ask` if the `openai`
    package is installed and `OPENAI_API_KEY` is set.
    """

    def __init__(
        self,
        ask_fn: Callable[[str], str] | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        prompt_mode: str = "rules_lite",  # one of: minimal, rules_lite, verbose
        debug_log: bool = False,
        retries: int = 2,
        retry_backoff: float = 1.5,
    ):
        if ask_fn is None and provider == "openai":
            ask_fn = self.openai_ask(model=model or "gpt-4o-mini", temperature=temperature)
        if ask_fn is None and provider == "ollama":
            ask_fn = self.ollama_ask(model=model or "llama3.1", temperature=temperature)
        # Google Gemini (official SDK)
        if ask_fn is None and provider in {"gemini", "google", "googleai", "google-genai"}:
            ask_fn = self.gemini_api_ask(model=model or "gemini-1.5-flash", temperature=temperature)
        if ask_fn is None and provider in {"openrouter", "openrouter.ai"}:
            ask_fn = self.openrouter_ask(model=model or "openrouter/sonoma-sky-alpha", temperature=temperature)
        if ask_fn is None:
            raise ValueError("LLMAgent requires ask_fn or provider='openai' with OpenAI installed and API key set.")
        self.ask_fn = ask_fn
        if prompt_mode not in {"minimal", "rules_lite", "verbose"}:
            raise ValueError("prompt_mode must be one of: minimal, rules_lite, verbose")
        self.prompt_mode = prompt_mode
        self.debug_log = debug_log
        self.retries = max(0, int(retries))
        self.retry_backoff = max(1.0, float(retry_backoff))

    def act(self, observation: Observation, info: Any) -> Action:
        import time as _time
        prompt = self._build_prompt(observation)
        text = ""
        err_msg = None
        attempts = 0
        for attempt in range(self.retries + 1):
            attempts = attempt + 1
            try:
                raw = self.ask_fn(prompt)
                text = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
                if text is None:
                    text = ""
                text = str(text)
                if text.strip():
                    break
                # empty response; retry if attempts remain
            except Exception as e:  # noqa: BLE001
                err_msg = f"{type(e).__name__}: {e}"
            # backoff if we have more attempts
            if attempt < self.retries:
                _time.sleep(self.retry_backoff ** attempt * 0.5)
        # Always record the raw LLM output and status in meta if possible
        if isinstance(info, dict):
            info["llm_raw"] = text
            info["llm_attempts"] = attempts
            if err_msg is not None:
                info["llm_status"] = "error"
                info["llm_error"] = err_msg
            elif not text.strip():
                info["llm_status"] = "empty"
            else:
                info["llm_status"] = "ok"
            if self.debug_log:
                info["llm_prompt_mode"] = self.prompt_mode
                info["llm_prompt"] = prompt
        out = text.strip().upper()
        # Allow variants like "HIT", "Action: HIT", or JSON-like outputs
        for a in observation.allowed_actions:
            if a.name in out:
                return a
        # last-ditch simple mapping by first token
        token = (out.split()[0] if out else "")
        token = token.strip(",.;:!{}[]()\"'")
        try:
            cand = Action[token]
            if cand in observation.allowed_actions:
                return cand
        except Exception:
            pass
        # If still invalid, pick a conservative legal default
        return observation.allowed_actions[0]

    def _ranks(self, cards: List[str]) -> str:
        return ",".join(c[:-1] for c in cards)

    def _build_prompt(self, obs: Observation) -> str:
        p = obs.player
        up = obs.dealer_upcard[:-1]
        if self.prompt_mode == "minimal":
            return (
                "Blackjack.\n"
                f"Dealer upcard: {up}.\n"
                f"Your hand: {self._ranks(p.cards)}.\n"
                "Reply with exactly one word: HIT, STAND, DOUBLE, SPLIT, or SURRENDER. No explanations."
            )
        if self.prompt_mode == "rules_lite":
            return (
                "Blackjack. Rules: 6 decks, dealer hits soft 17 (H17), blackjack pays 3:2, double on any two, "
                "double after split allowed, resplit to 3 hands, split aces one-card, no surrender.\n"
                f"Dealer upcard: {up}.\n"
                f"Your hand: {self._ranks(p.cards)}.\n"
                "Reply with exactly one word: HIT, STAND, DOUBLE, SPLIT, or SURRENDER. No explanations."
            )
        # verbose
        return (
            "You are playing Blackjack. Return one word: a legal action.\n"
            f"Dealer upcard: {up}.\n"
            f"Player cards: {self._ranks(p.cards)} (total={p.total}, soft={p.is_soft}).\n"
            f"Allowed actions: {_format_allowed(obs.allowed_actions)}.\n"
            "Respond with exactly one of: HIT, STAND, DOUBLE, SPLIT, SURRENDER."
        )

    @staticmethod
    def openai_ask(*, model: str, temperature: float = 0.0) -> Callable[[str], str]:
        """Create an ask_fn that queries OpenAI's Chat Completions API.

        Supports both the new `openai` client (OpenAI()) and the legacy
        `openai.ChatCompletion.create` if present. Requires OPENAI_API_KEY.
        """
        try:
            # New style client
            from openai import OpenAI  # type: ignore

            client = OpenAI()

            def _ask(prompt: str) -> str:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a concise assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=4,
                )
                return resp.choices[0].message.content or ""

            return _ask
        except ImportError:
            pass

        # Legacy fallback
        try:
            import openai  # type: ignore

            def _ask(prompt: str) -> str:
                resp = openai.ChatCompletion.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a concise assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=4,
                )
                return resp["choices"][0]["message"]["content"]

            return _ask
        except ImportError as e:
            raise RuntimeError("OpenAI client not available. Install 'openai' and set OPENAI_API_KEY.") from e

    @staticmethod
    def ollama_ask(*, model: str, temperature: float = 0.0, host: str = "http://127.0.0.1:11434") -> Callable[[str], str]:
        """Create an ask_fn that queries a local Ollama server via /api/generate.
        
        Uses requests if available, else falls back to urllib.
        """
        try:
            import requests  # type: ignore

            def _ask(prompt: str) -> str:
                r = requests.post(
                    f"{host}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": temperature},
                    },
                    timeout=120,
                )
                r.raise_for_status()
                data = r.json()
                return data.get("response", "")

            return _ask
        except Exception:
            # urllib fallback
            import json as _json
            from urllib import request as _ur, error as _err

            def _ask(prompt: str) -> str:
                payload = _json.dumps({
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature},
                }).encode("utf-8")
                req = _ur.Request(f"{host}/api/generate", data=payload, headers={"Content-Type": "application/json"}, method="POST")
                try:
                    with _ur.urlopen(req, timeout=120) as resp:  # type: ignore
                        data = _json.loads(resp.read().decode("utf-8"))
                        return data.get("response", "")
                except _err.URLError:
                    return ""

            return _ask

    @staticmethod
    def gemini_api_ask(*, model: str = "gemini-1.5-flash", temperature: float = 0.0) -> Callable[[str], str]:
        """Create an ask_fn using Google's Gemini API via google-generativeai.

        Requires the `google-generativeai` package and an API key in either
        GOOGLE_API_KEY or GEMINI_API_KEY.
        """
        import os

        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Set GOOGLE_API_KEY or GEMINI_API_KEY for --llm-provider gemini/google")
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as e:
            raise RuntimeError("Install 'google-generativeai' to use --llm-provider gemini/google") from e

        genai.configure(api_key=api_key)
        gmodel = genai.GenerativeModel(model)

        def _ask(prompt: str) -> str:
            try:
                resp = gmodel.generate_content(
                    prompt,
                    generation_config={
                        "temperature": temperature,
                        "max_output_tokens": 8,
                    },
                )
                # Prefer .text; fall back to empty string on safety blocks
                return getattr(resp, "text", "") or ""
            except Exception:
                return ""

        return _ask

    @staticmethod
    def openrouter_ask(*, model: str, temperature: float = 0.0, base_url: str = "https://openrouter.ai/api/v1") -> Callable[[str], str]:
        """Create an ask_fn that queries OpenRouter's chat completions API.

        Requires the env var OPENROUTER_API_KEY. Honors temperature and limits output tokens.
        """
        import os
        import json as _json
        headers_extra = {}
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("Set OPENROUTER_API_KEY for --llm-provider openrouter")

        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # Optional headers recommended by OpenRouter
        if os.environ.get("OPENROUTER_HTTP_REFERER"):
            headers["HTTP-Referer"] = os.environ["OPENROUTER_HTTP_REFERER"]
        if os.environ.get("OPENROUTER_X_TITLE"):
            headers["X-Title"] = os.environ["OPENROUTER_X_TITLE"]

        def _ask_req(prompt: str) -> str:
            try:
                import requests  # type: ignore
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a concise assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": 4,
                }
                r = requests.post(url, headers=headers, json=payload, timeout=120)
                r.raise_for_status()
                data = r.json()
                choices = data.get("choices") or []
                if choices:
                    msg = choices[0].get("message", {}).get("content", "")
                    return msg or ""
                return ""
            except Exception:
                return ""

        def _ask_fallback(prompt: str) -> str:
            from urllib import request as _ur, error as _err
            payload = _json.dumps({
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a concise assistant."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": 4,
            }).encode("utf-8")
            req = _ur.Request(url, data=payload, headers=headers, method="POST")
            try:
                with _ur.urlopen(req, timeout=120) as resp:  # type: ignore
                    data = _json.loads(resp.read().decode("utf-8"))
                    choices = data.get("choices") or []
                    if choices:
                        return choices[0].get("message", {}).get("content", "") or ""
                    return ""
            except _err.URLError:
                return ""

        def _ask(prompt: str) -> str:
            out = _ask_req(prompt)
            return out if out else _ask_fallback(prompt)

        return _ask
