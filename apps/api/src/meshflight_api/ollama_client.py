from __future__ import annotations

import json

import httpx


class OllamaClientError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, timeout_s: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def list_models(self) -> list[str]:
        payload = self._request("GET", "/api/tags")
        models = payload.get("models")
        if not isinstance(models, list):
            raise OllamaClientError("Ollama /api/tags returned an unexpected payload.")

        names: list[str] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            name = model.get("model") or model.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())

        return names

    def chat_json(self, *, model: str, system_prompt: str, user_prompt: str) -> dict[str, object]:
        payload = self._request(
            "POST",
            "/api/chat",
            json_body={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
        )

        message = payload.get("message")
        if not isinstance(message, dict):
            raise OllamaClientError("Ollama /api/chat did not return a message payload.")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaClientError("Ollama /api/chat returned an empty message content.")

        parsed = self._parse_json_object_content(content)

        if not isinstance(parsed, dict):
            raise OllamaClientError("Ollama returned JSON, but it was not a JSON object.")

        return parsed

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with httpx.Client(timeout=self.timeout_s) as client:
            try:
                response = client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json_body,
                )
            except httpx.ReadTimeout as error:
                raise OllamaClientError(
                    f"Ollama timed out after {self.timeout_s:.0f}s while handling {path}. "
                    "The local model is responding too slowly for the current timeout. "
                    "Increase OLLAMA_TIMEOUT_S or use a lighter model."
                ) from error
            except httpx.ConnectError as error:
                raise OllamaClientError(
                    f"Ollama is not reachable at {self.base_url}. Start Ollama and try again."
                ) from error
            except httpx.HTTPError as error:
                raise OllamaClientError(
                    f"Ollama request to {self.base_url}{path} failed."
                ) from error

        if response.status_code >= 400:
            raise OllamaClientError(
                f"Ollama request failed with status {response.status_code}: {response.text}"
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as error:
            raise OllamaClientError("Ollama returned a non-JSON response.") from error

        if not isinstance(payload, dict):
            raise OllamaClientError("Ollama returned a JSON payload that was not an object.")

        return payload

    def _parse_json_object_content(self, content: str) -> dict[str, object]:
        # First try strict parsing for the happy path.
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Handle common model patterns like ```json ... ``` wrappers.
        stripped = content.strip()
        if stripped.startswith("```"):
            fence_lines = stripped.splitlines()
            if len(fence_lines) >= 3 and fence_lines[-1].strip() == "```":
                inner = "\n".join(fence_lines[1:-1]).strip()
                try:
                    parsed = json.loads(inner)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass

        # Last resort: extract first balanced JSON object from mixed prose.
        obj_text = self._extract_first_json_object(content)
        if obj_text is not None:
            try:
                parsed = json.loads(obj_text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        raise OllamaClientError("Ollama returned content that was not valid JSON.")

    def _extract_first_json_object(self, text: str) -> str | None:
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]

        return None
