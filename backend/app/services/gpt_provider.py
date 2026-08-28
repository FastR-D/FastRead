from __future__ import annotations

from app.enmus.exception import ProviderErrorEnum
from app.exceptions.provider import ProviderError
from dataclasses import dataclass

from openai import OpenAI
from app.models.model_config import ModelConfig
from app.services.provider import ProviderService
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ChatModelClient:
    client: OpenAI
    model: str


class GPTProvider:
    """Build GPT clients from configured provider records."""

    @staticmethod
    def create(
        *,
        provider_id: str | int | None,
        model_name: str | None,
        required: bool = True,
    ) -> ChatModelClient | None:
        if not provider_id:
            if required:
                raise ProviderError(
                    message=ProviderErrorEnum.NOT_FOUND.message,
                    code=ProviderErrorEnum.NOT_FOUND,
                )
            return None

        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            if required:
                logger.error(f"[gpt_provider] 未找到模型供应商: provider_id={provider_id}")
                raise ProviderError(
                    message=ProviderErrorEnum.NOT_FOUND.message,
                    code=ProviderErrorEnum.NOT_FOUND,
                )
            return None

        config = GPTProvider.build_model_config(provider, model_name)
        logger.info(f"创建 GPT 实例 provider_id={provider_id}, model={model_name}")
        return ChatModelClient(
            client=OpenAI(api_key=config.api_key, base_url=config.base_url),
            model=config.model_name,
        )

    @staticmethod
    def build_model_config(provider: dict, model_name: str | None = None) -> ModelConfig:
        return ModelConfig(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
            model_name=model_name or "",
            provider=provider.get("type") or provider.get("name"),
            name=provider["name"],
        )
