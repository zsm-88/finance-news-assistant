import pytest

from app.ai.schemas import AnalysisOutput
from app.ai.validator import ResponseValidator


def valid_output() -> dict[str, object]:
    return {
        "category": "macro",
        "importance": 4,
        "summary": "Inflation data was released.",
        "confidence": 0.9,
        "market_impacts": [{"asset": "美元", "direction": "bullish", "confidence": 0.8, "reason": "Higher rates may support USD."}],
    }


def test_response_validator_returns_structured_output() -> None:
    result = ResponseValidator().validate(valid_output())
    assert isinstance(result, AnalysisOutput)
    assert result.market_impacts[0].asset == "美元"


def test_response_validator_rejects_invalid_impact() -> None:
    value = valid_output()
    value["market_impacts"] = [{"asset": "crypto", "direction": "bullish", "confidence": 0.8, "reason": "x"}]
    with pytest.raises(ValueError):
        ResponseValidator().validate(value)

