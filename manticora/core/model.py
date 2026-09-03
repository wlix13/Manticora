from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict


class BaseModel(PydanticBaseModel):
    """Immutable data model, subclasses render themselves for console via rich."""

    model_config = ConfigDict(frozen=True)
