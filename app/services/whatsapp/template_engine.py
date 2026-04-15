import random
import re
from collections.abc import Mapping

ALLOWED_TEMPLATE_TOKENS = {
    "nombre",
    "negocio",
    "fecha",
    "hora",
    "servicio",
    "horas_disponibles_hoy",
    "hora_disponible",
}

_TOKEN_PATTERN = re.compile(r"\{([^{}]+)\}")


class TemplateEngineError(ValueError):
    pass


def select_variant(
    message_templates: Mapping[str, object],
    message_type: str,
    *,
    rng: random.Random | None = None,
) -> tuple[int, str]:
    template_config = message_templates.get(message_type)
    if not isinstance(template_config, Mapping):
        raise TemplateEngineError(f"Template type '{message_type}' is not configured")

    enabled = bool(template_config.get("enabled", False))
    variants = template_config.get("variants")

    if not enabled:
        raise TemplateEngineError(f"Template type '{message_type}' is disabled")
    if not isinstance(variants, list) or not variants:
        raise TemplateEngineError(f"Template type '{message_type}' has no variants")

    normalized = [variant.strip() for variant in variants if isinstance(variant, str) and variant.strip()]
    if not normalized:
        raise TemplateEngineError(f"Template type '{message_type}' has no valid variants")

    randomizer = rng or random
    selected_index = randomizer.randint(0, len(normalized) - 1)
    return selected_index, normalized[selected_index]


def resolve_variables(template_text: str, values: Mapping[str, object]) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in ALLOWED_TEMPLATE_TOKENS:
            return match.group(0)

        value = values.get(token)
        if value is None:
            return ""
        return str(value)

    return _TOKEN_PATTERN.sub(replace, template_text)
