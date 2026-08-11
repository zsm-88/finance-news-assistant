from pydantic import ValidationError

from .schemas import AnalysisOutput


class ResponseValidator:
    def validate(self, value: dict[str, object]) -> AnalysisOutput:
        try:
            return AnalysisOutput.model_validate(value)
        except ValidationError as exc:
            raise ValueError(f"AI response validation failed: {exc}") from exc

