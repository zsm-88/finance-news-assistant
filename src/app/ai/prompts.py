import json
from dataclasses import dataclass
from typing import Any

from app.db.models import PromptVersion

from .context import AnalysisContext
from .schemas import AnalysisOutput


@dataclass(slots=True)
class BuiltPrompt:
    prompt_version_id: Any
    prompt_version: str
    system: str
    task: str
    output_schema: dict[str, Any]

    @property
    def cache_material(self) -> str:
        return json.dumps({"system": self.system, "task": self.task, "schema": self.output_schema}, ensure_ascii=True, sort_keys=True)


class PromptBuilder:
    def build(self, prompt_version: PromptVersion, context: AnalysisContext, few_shot: list[dict[str, Any]] | None = None) -> BuiltPrompt:
        system = prompt_version.prompt_content
        schema = AnalysisOutput.model_json_schema()
        task = json.dumps({"context": context.as_dict(), "few_shot_examples": few_shot or [], "output_schema": schema}, ensure_ascii=False)
        return BuiltPrompt(prompt_version.id, prompt_version.version, system, task, schema)
